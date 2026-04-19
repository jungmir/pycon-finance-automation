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
