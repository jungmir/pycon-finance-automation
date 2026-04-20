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


# ── Step2TrackReviewingHandler tests ─────────────────────────────────

import responses as resp_lib
from src.handlers.step2_track_reviewing import Step2TrackReviewingHandler
from src.clients.dooray import DOORAY_WORKFLOW_NAME_REVIEWING, DOORAY_WORKFLOW_NAME_REJECTED

PAJUNWI_PROJECT = "pajunwi-proj"
BASE = "https://api.dooray.com/project/v1"


def make_dooray_client(token="tok"):
    from src.clients.dooray import DoorayClient
    return DoorayClient(token)


@resp_lib.activate
def test_step2_transitions_to_reviewing(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "workflow": {"name": DOORAY_WORKFLOW_NAME_REVIEWING},
            "body": {"content": "금액: 50,000원\n출장비 신청"},
        }},
    )

    store.upsert_task("t1", "NEW")
    handler = Step2TrackReviewingHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "REVIEWING"
    assert task["amount"] == 50000


@resp_lib.activate
def test_step2_returns_none_when_still_new(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": "검토 전"}}},
    )

    store.upsert_task("t1", "NEW")
    handler = Step2TrackReviewingHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is False
    assert store.get_task("t1")["state"] == "NEW"


@resp_lib.activate
def test_step2_sets_rejected_on_banjyo(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": DOORAY_WORKFLOW_NAME_REJECTED}}},
    )

    store.upsert_task("t1", "NEW")
    handler = Step2TrackReviewingHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is False
    assert store.get_task("t1")["state"] == "REJECTED"
    notifier.task_rejected.assert_called_once_with("t1")


def test_step2_parse_amount_with_comma():
    handler = Step2TrackReviewingHandler(MagicMock(), MagicMock(), make_dooray_client(), "proj")
    assert handler._parse_amount("금액: 1,234,567원") == 1234567


def test_step2_parse_amount_no_match_returns_zero():
    handler = Step2TrackReviewingHandler(MagicMock(), MagicMock(), make_dooray_client(), "proj")
    assert handler._parse_amount("내용 없음") == 0


def test_step2_parse_amount_jichul_template():
    handler = Step2TrackReviewingHandler(MagicMock(), MagicMock(), make_dooray_client(), "proj")
    assert handler._parse_amount("* 실제 지출: 5,200원") == 5200


def test_step2_parse_amount_yesang_jichul_template():
    handler = Step2TrackReviewingHandler(MagicMock(), MagicMock(), make_dooray_client(), "proj")
    assert handler._parse_amount("* 예상 지출액 : 10,000원") == 10000


# ── Step3TrackPaymentWaitingHandler tests ────────────────────────────

from src.handlers.step3_track_payment_waiting import Step3TrackPaymentWaitingHandler
from src.clients.dooray import DOORAY_WORKFLOW_NAME_PAYMENT_WAITING


@resp_lib.activate
def test_step3_transitions_to_payment_waiting(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": DOORAY_WORKFLOW_NAME_PAYMENT_WAITING}}},
    )

    store.upsert_task("t1", "REVIEWING")
    handler = Step3TrackPaymentWaitingHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING"})

    assert result is True
    assert store.get_task("t1")["state"] == "PAYMENT_WAITING"


@resp_lib.activate
def test_step3_returns_none_when_still_reviewing(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": "검토 중"}}},
    )

    store.upsert_task("t1", "REVIEWING")
    handler = Step3TrackPaymentWaitingHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING"})

    assert result is False
    assert store.get_task("t1")["state"] == "REVIEWING"


@resp_lib.activate
def test_step3_sets_rejected_on_banjyo(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": DOORAY_WORKFLOW_NAME_REJECTED}}},
    )

    store.upsert_task("t1", "REVIEWING")
    handler = Step3TrackPaymentWaitingHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING"})

    assert result is False
    assert store.get_task("t1")["state"] == "REJECTED"
    notifier.task_rejected.assert_called_once_with("t1")


# ── Step4CopyToPyconHandler tests ─────────────────────────────────────

from src.handlers.step4_copy_to_pycon import Step4CopyToPyconHandler

PYCON_PROJECT = "pycon-proj"


@resp_lib.activate
def test_step4_copies_task_to_pycon(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "subject": "출장비 신청", "body": {"content": "금액: 50,000원"}}},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {"id": "pycon-t1"}},
    )

    store.upsert_task("t1", "PAYMENT_WAITING")
    handler = Step4CopyToPyconHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "PAYMENT_WAITING"})

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "COPIED_TO_PYCON"
    assert task["pycon_task_id"] == "pycon-t1"


@resp_lib.activate
def test_step4_notifies_on_copy(store, notifier):
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

    store.upsert_task("t2", "PAYMENT_WAITING")
    handler = Step4CopyToPyconHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({"pajunwi_task_id": "t2", "state": "PAYMENT_WAITING"})

    notifier.task_copied.assert_called_once_with("t2", "교통비")


@resp_lib.activate
def test_step4_idempotent_when_pycon_task_already_exists(store, notifier):
    store.upsert_task("t1", "PAYMENT_WAITING", pycon_task_id="existing-pycon-t1")
    handler = Step4CopyToPyconHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "PAYMENT_WAITING",
                          "pycon_task_id": "existing-pycon-t1"})

    assert result is True
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_step4_raises_on_missing_id(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/task-1",
        json={"result": {"subject": "비품 구매", "body": {"content": ""}}},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {}},
    )

    store.upsert_task("task-1", "PAYMENT_WAITING")
    handler = Step4CopyToPyconHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    with pytest.raises(ValueError, match="missing both"):
        handler.execute(store.get_task("task-1"))


# ── Step5TrackPaymentInProgressHandler tests ─────────────────────────

from src.handlers.step5_track_payment_in_progress import Step5TrackPaymentInProgressHandler
from src.clients.dooray import DOORAY_WORKFLOW_NAME_PAYMENT_IN_PROGRESS


@resp_lib.activate
def test_step5_transitions_to_payment_in_progress(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": DOORAY_WORKFLOW_NAME_PAYMENT_IN_PROGRESS}}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    handler = Step5TrackPaymentInProgressHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"})

    assert result is True
    assert store.get_task("t1")["state"] == "PAYMENT_IN_PROGRESS"


@resp_lib.activate
def test_step5_returns_none_when_still_waiting(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": "결제 대기 중"}}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    handler = Step5TrackPaymentInProgressHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"})

    assert result is False
    assert store.get_task("t1")["state"] == "COPIED_TO_PYCON"


@resp_lib.activate
def test_step5_sets_rejected_on_banjyo(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflow": {"name": DOORAY_WORKFLOW_NAME_REJECTED}}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    handler = Step5TrackPaymentInProgressHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"})

    assert result is False
    assert store.get_task("t1")["state"] == "REJECTED"
    notifier.task_rejected.assert_called_once_with("t1")


# ── Step6SyncAndCompleteHandler tests ────────────────────────────────

import json as _json
from src.handlers.step6_sync_and_complete import Step6SyncAndCompleteHandler
from src.clients.dooray import DOORAY_WORKFLOW_NAME_COMPLETED, DOORAY_WORKFLOW_ID_COMPLETED


@resp_lib.activate
def test_step6_syncs_body_and_completes_when_pycon_done(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "body": {"content": "금액: 50,000원\n영수증 첨부"}}},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {}},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflow": {"name": DOORAY_WORKFLOW_NAME_COMPLETED}}},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/set-workflow",
        json={"result": None},
    )

    store.upsert_task("t1", "PAYMENT_IN_PROGRESS", pycon_task_id="pycon-t1")
    handler = Step6SyncAndCompleteHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_IN_PROGRESS", "pycon_task_id": "pycon-t1"
    })

    assert result is True
    assert store.get_task("t1")["state"] == "COMPLETED"
    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 1
    body = _json.loads(post_calls[0].request.body)
    assert body.get("workflowId") == DOORAY_WORKFLOW_ID_COMPLETED


@resp_lib.activate
def test_step6_keeps_polling_when_pycon_not_done(store, notifier):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "body": {"content": "금액: 50,000원"}}},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {}},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflow": {"name": "결제 중"}}},
    )

    store.upsert_task("t1", "PAYMENT_IN_PROGRESS", pycon_task_id="pycon-t1")
    handler = Step6SyncAndCompleteHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_IN_PROGRESS", "pycon_task_id": "pycon-t1"
    })

    assert result is False
    assert store.get_task("t1")["state"] == "PAYMENT_IN_PROGRESS"


def test_step6_raises_when_no_pycon_task_id(store, notifier):
    store.upsert_task("t1", "PAYMENT_IN_PROGRESS")
    handler = Step6SyncAndCompleteHandler(store, notifier, make_dooray_client(), PAJUNWI_PROJECT, PYCON_PROJECT)
    with pytest.raises(ValueError, match="pycon_task_id"):
        handler.execute({"pajunwi_task_id": "t1", "state": "PAYMENT_IN_PROGRESS"})


# ── Step8UpdateSheetsHandler tests ────────────────────────────────────

from src.handlers.step8_update_sheets import Step8UpdateSheetsHandler


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_step8_appends_row_to_sheet(mock_sa, store, notifier):
    mock_worksheet = MagicMock()
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    from src.clients.sheets import SheetsClient
    import base64, json as _json
    sa_b64 = base64.b64encode(_json.dumps({"type": "service_account"}).encode()).decode()
    sheets = SheetsClient(sa_b64, "sheet1")

    store.upsert_task("t1", "COMPLETED", amount=75000)
    handler = Step8UpdateSheetsHandler(store, notifier, sheets)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COMPLETED", "amount": 75000})

    assert result is True
    assert store.get_task("t1")["state"] == "SHEET_UPDATED"
    mock_worksheet.append_row.assert_called_once()
    row = mock_worksheet.append_row.call_args[0][0]
    assert 75000 in row


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_step8_sheets_failure_notifies_but_does_not_crash(mock_sa, store, notifier):
    mock_worksheet = MagicMock()
    mock_worksheet.append_row.side_effect = Exception("Quota exceeded")
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    from src.clients.sheets import SheetsClient
    import base64, json as _json
    sa_b64 = base64.b64encode(_json.dumps({"type": "service_account"}).encode()).decode()
    sheets = SheetsClient(sa_b64, "sheet1")

    store.upsert_task("t1", "COMPLETED", amount=50000)
    handler = Step8UpdateSheetsHandler(store, notifier, sheets)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COMPLETED", "amount": 50000})

    assert result is False
    assert store.get_task("t1")["state"] == "COMPLETED"
    notifier.handler_error.assert_called_once()


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_step8_uses_zero_when_amount_missing(mock_sa, store, notifier):
    mock_worksheet = MagicMock()
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    from src.clients.sheets import SheetsClient
    import base64, json as _json
    sa_b64 = base64.b64encode(_json.dumps({"type": "service_account"}).encode()).decode()
    sheets = SheetsClient(sa_b64, "sheet1")

    store.upsert_task("t1", "COMPLETED")
    handler = Step8UpdateSheetsHandler(store, notifier, sheets)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COMPLETED"})

    assert result is True
    row = mock_worksheet.append_row.call_args[0][0]
    assert 0 in row
