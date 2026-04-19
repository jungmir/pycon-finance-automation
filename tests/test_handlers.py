import pytest
from unittest.mock import MagicMock, patch
from src.handlers.base import BaseHandler


class ConcreteHandler(BaseHandler):
    name = "concrete"
    from_state = "NEW"
    to_state = "DONE"

    def __init__(self, store, notifier, execute_result=True):
        super().__init__(store, notifier)
        self._execute_result = execute_result

    def execute(self, task: dict):
        return self._execute_result


def test_run_success_transitions_state(store, notifier):
    store.upsert_task("task-1", "NEW")
    handler = ConcreteHandler(store, notifier, execute_result=True)
    result = handler.run(store.get_task("task-1"))
    assert result is True
    assert store.get_task("task-1")["state"] == "DONE"


def test_run_success_logs_transition(store, notifier):
    store.upsert_task("task-1", "NEW")
    handler = ConcreteHandler(store, notifier, execute_result=True)
    handler.run(store.get_task("task-1"))
    history = store._conn.execute(
        "SELECT * FROM state_history WHERE pajunwi_task_id = 'task-1'"
    ).fetchall()
    assert len(history) == 1
    assert history[0]["success"] == 1


def test_run_dict_result_merges_extra_fields(store, notifier):
    store.upsert_task("task-1", "NEW")
    handler = ConcreteHandler(store, notifier, execute_result={"pycon_task_id": "pycon-99"})
    handler.run(store.get_task("task-1"))
    task = store.get_task("task-1")
    assert task["state"] == "DONE"
    assert task["pycon_task_id"] == "pycon-99"


def test_run_none_result_skips_silently(store, notifier):
    store.upsert_task("task-1", "NEW")
    handler = ConcreteHandler(store, notifier, execute_result=None)
    result = handler.run(store.get_task("task-1"))
    assert result is False
    assert store.get_task("task-1")["state"] == "NEW"


def test_run_exception_calls_notifier(store, notifier):
    store.upsert_task("task-1", "NEW")

    class FailingHandler(BaseHandler):
        name = "failing"
        from_state = "NEW"
        to_state = "DONE"

        def execute(self, task):
            raise RuntimeError("boom")

    handler = FailingHandler(store, notifier)
    with patch("time.sleep"):
        result = handler.run(store.get_task("task-1"))
    assert result is False
    notifier.handler_error.assert_called_once_with("failing", "task-1", "boom")


def test_run_exception_logs_failed_transition(store, notifier):
    store.upsert_task("task-1", "NEW")

    class FailingHandler(BaseHandler):
        name = "failing"
        from_state = "NEW"
        to_state = "DONE"

        def execute(self, task):
            raise RuntimeError("boom")

    handler = FailingHandler(store, notifier)
    with patch("time.sleep"):
        handler.run(store.get_task("task-1"))
    history = store._conn.execute(
        "SELECT * FROM state_history WHERE pajunwi_task_id = 'task-1'"
    ).fetchall()
    assert len(history) == 1
    assert history[0]["success"] == 0
    assert "boom" in history[0]["error_msg"]


def test_execute_with_retry_retries_on_exception(store, notifier):
    call_count = 0

    class FlakyHandler(BaseHandler):
        name = "flaky"
        from_state = "NEW"
        to_state = "DONE"

        def execute(self, task):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return True

    handler = FlakyHandler(store, notifier)
    store.upsert_task("task-1", "NEW")
    with patch("time.sleep"):
        result = handler.run(store.get_task("task-1"))
    assert result is True
    assert call_count == 3


# Step 2 tests

import responses as resp_lib
from src.handlers.step2_review import Step2ReviewHandler
from src.clients.dooray import DOORAY_STATUS_REVIEWING

PAJUNWI_PROJECT = "pajunwi-proj"
BASE = "https://test.dooray.com/common/v1"


def make_dooray_client(domain="test.dooray.com", token="tok"):
    from src.clients.dooray import DoorayClient
    return DoorayClient(domain, token)


@resp_lib.activate
def test_step2_transitions_to_reviewing(store, notifier):
    """Step 2 calls Dooray to change status, stores REVIEWING + amount."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "workflowClass": "registered",  # current: NEW
            "body": {"content": "금액: 50,000원\n출장비 신청"},
        }},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {}},
    )

    store.upsert_task("t1", "NEW")
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(store, notifier, dooray, PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "REVIEWING"
    assert task["amount"] == 50000


@resp_lib.activate
def test_step2_idempotent_when_already_reviewing(store, notifier):
    """If Dooray already shows REVIEWING, skip the PUT and still return True."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "workflowClass": DOORAY_STATUS_REVIEWING,
            "body": {"content": "금액: 30,000원"},
        }},
    )

    store.upsert_task("t1", "NEW")
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(store, notifier, dooray, PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is True
    assert len([c for c in resp_lib.calls if c.request.method == "PUT"]) == 0


def test_step2_parse_amount_with_comma():
    from unittest.mock import MagicMock
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(MagicMock(), MagicMock(), dooray, "proj")
    assert handler._parse_amount("금액: 1,234,567원") == 1234567


def test_step2_parse_amount_no_match_returns_zero():
    from unittest.mock import MagicMock
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(MagicMock(), MagicMock(), dooray, "proj")
    assert handler._parse_amount("내용 없음") == 0


# Step 3 tests

from src.handlers.step3_copy import Step3CopyHandler

PYCON_PROJECT = "pycon-proj"


@resp_lib.activate
def test_step3_copies_task_to_pycon(store, notifier):
    """Step 3 creates a task in the pycon portal and stores pycon_task_id."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "subject": "출장비 신청",
            "body": {"content": "금액: 50,000원"},
        }},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {"id": "pycon-t1"}},
    )

    store.upsert_task("t1", "REVIEWING")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING"})

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "COPIED_TO_PYCON"
    assert task["pycon_task_id"] == "pycon-t1"


@resp_lib.activate
def test_step3_notifies_on_copy(store, notifier):
    """Step 3 sends a Slack success notification after copying."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t2",
        json={"result": {"id": "t2", "subject": "교통비", "body": {"content": ""}}},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {"id": "pycon-t2"}},
    )

    store.upsert_task("t2", "REVIEWING")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({"pajunwi_task_id": "t2", "state": "REVIEWING"})

    notifier.task_copied.assert_called_once_with("t2", "교통비")


@resp_lib.activate
def test_step3_idempotent_when_pycon_task_already_exists(store, notifier):
    """If pycon_task_id is already set in store, skip POST and return True."""
    store.upsert_task("t1", "REVIEWING", pycon_task_id="existing-pycon-t1")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING",
                          "pycon_task_id": "existing-pycon-t1"})

    assert result is True
    assert len(resp_lib.calls) == 0  # no API calls made


@resp_lib.activate
def test_step3_copy_raises_on_missing_id(store, notifier):
    """Step 3 raises ValueError when create_task response has neither id nor postId."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/task-1",
        json={"result": {"subject": "비품 구매", "body": {"content": "금액: 50,000원"}}},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {}},  # no id or postId
    )

    store.upsert_task("task-1", "REVIEWING")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    task = store.get_task("task-1")

    with pytest.raises(ValueError, match="missing both"):
        handler.execute(task)


# ── Step5PaymentHandler tests ──────────────────────────────────────
from src.handlers.step5_payment import Step5PaymentHandler
from src.clients.dooray import DOORAY_STATUS_PAYMENT_PENDING, DOORAY_STATUS_REJECTED


@resp_lib.activate
def test_step5_transitions_to_payment_pending(store, notifier):
    """If pycon task shows 결제대기, sync pajunwi and set PAYMENT_PENDING."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": DOORAY_STATUS_PAYMENT_PENDING}},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflowClass": "working"}},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert result is True
    assert store.get_task("t1")["state"] == "PAYMENT_PENDING"


@resp_lib.activate
def test_step5_returns_none_when_still_reviewing(store, notifier):
    """If pycon task is still in review, return None (not ready yet)."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": "working"}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert result is False
    assert store.get_task("t1")["state"] == "COPIED_TO_PYCON"  # unchanged


@resp_lib.activate
def test_step5_sets_rejected_and_notifies(store, notifier):
    """If pycon task is rejected, set REJECTED state and send Slack alert."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": DOORAY_STATUS_REJECTED}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert store.get_task("t1")["state"] == "REJECTED"
    notifier.task_rejected.assert_called_once_with("pycon-t1")


@resp_lib.activate
def test_step5_idempotent_when_pajunwi_already_payment_pending(store, notifier):
    """If pajunwi is already PAYMENT_PENDING, skip the PUT and still return True."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": DOORAY_STATUS_PAYMENT_PENDING}},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflowClass": DOORAY_STATUS_PAYMENT_PENDING}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert result is True
    assert store.get_task("t1")["state"] == "PAYMENT_PENDING"
    put_calls = [c for c in resp_lib.calls if c.request.method == "PUT"]
    assert len(put_calls) == 0  # skipped because already PAYMENT_PENDING


# ── Step8EvidenceHandler tests ─────────────────────────────────────
from src.handlers.step8_evidence import Step8EvidenceHandler


@resp_lib.activate
def test_step8_copies_new_comment_to_pycon(store, notifier):
    """Step 8 copies comments added after last_comment_id."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [
            {"id": "c1", "body": {"content": "영수증 첨부"}},
            {"id": "c2", "body": {"content": "카드 내역 첨부"}},
        ]},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1/logs",
        json={"result": {"id": "c3"}},
    )

    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1",
                      last_comment_id=None)
    dooray = make_dooray_client()
    handler = Step8EvidenceHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_PENDING",
        "pycon_task_id": "pycon-t1", "last_comment_id": None,
    })

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "EVIDENCE_COPIED"
    assert task["last_comment_id"] == "c2"  # last copied comment


@resp_lib.activate
def test_step8_skips_already_copied_comments(store, notifier):
    """Comments with id <= last_comment_id are not re-copied."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [
            {"id": "c1", "body": {"content": "이전 코멘트"}},
            {"id": "c2", "body": {"content": "새 코멘트"}},
        ]},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1/logs",
        json={"result": {"id": "c3"}},
    )

    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1",
                      last_comment_id="c1")
    dooray = make_dooray_client()
    handler = Step8EvidenceHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_PENDING",
        "pycon_task_id": "pycon-t1", "last_comment_id": "c1",
    })

    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 1  # only c2 was copied


@resp_lib.activate
def test_step8_returns_none_when_no_new_comments(store, notifier):
    """No new comments → return None (not ready), no state change."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [{"id": "c1", "body": {"content": "old"}}]},
    )

    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1",
                      last_comment_id="c1")
    dooray = make_dooray_client()
    handler = Step8EvidenceHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_PENDING",
        "pycon_task_id": "pycon-t1", "last_comment_id": "c1",
    })

    assert result is False
    assert store.get_task("t1")["state"] == "PAYMENT_PENDING"


@resp_lib.activate
def test_step8_raises_when_last_comment_not_found(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [{"id": "c3", "body": {"content": "newer comment"}}]},
    )
    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1", last_comment_id="c1")
    handler = Step8EvidenceHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    with pytest.raises(ValueError, match="not found"):
        handler.execute(store.get_task("t1"))
