# tests/test_integration.py
"""
End-to-end test: a task entering as NEW flows all the way to SHEET_UPDATED
with all HTTP calls mocked.
"""
import base64
import json
import responses as resp_lib
import pytest
from unittest.mock import patch, MagicMock

from src.store import Store
from src.notifier import Notifier
from src.clients.dooray import (
    DoorayClient,
    DOORAY_WORKFLOW_NAME_REVIEWING,
    DOORAY_WORKFLOW_NAME_PAYMENT_WAITING,
    DOORAY_WORKFLOW_NAME_PAYMENT_IN_PROGRESS,
    DOORAY_WORKFLOW_NAME_COMPLETED,
    DOORAY_WORKFLOW_NAME_REJECTED,
    DOORAY_WORKFLOW_ID_COMPLETED,
)
from src.clients.sheets import SheetsClient
from src.state_engine import StateEngine
from src.handlers.step2_track_reviewing import Step2TrackReviewingHandler
from src.handlers.step3_track_payment_waiting import Step3TrackPaymentWaitingHandler
from src.handlers.step4_copy_to_pycon import Step4CopyToPyconHandler
from src.handlers.step5_track_payment_in_progress import Step5TrackPaymentInProgressHandler
from src.handlers.step6_sync_and_complete import Step6SyncAndCompleteHandler
from src.handlers.step8_update_sheets import Step8UpdateSheetsHandler

PAJUNWI = "pajunwi-proj"
PYCON = "pycon-proj"
BASE = "https://api.dooray.com/project/v1"
SPREADSHEET = "sheet-123"

PAJUNWI_TASK_ID = "task-001"
PYCON_TASK_ID = "pycon-task-001"


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def notifier():
    return MagicMock(spec=Notifier)


@pytest.fixture
def dooray():
    return DoorayClient("tok")


@pytest.fixture
def mock_sheet():
    mock_ws = MagicMock()
    with patch("src.clients.sheets.gspread.service_account_from_dict") as mock_sa:
        mock_sa.return_value.open_by_key.return_value.sheet1 = mock_ws
        sa_b64 = base64.b64encode(json.dumps({"type": "service_account"}).encode()).decode()
        sheets = SheetsClient(sa_b64, SPREADSHEET)
        yield sheets, mock_ws


def build_engine(store, notifier, dooray, sheets):
    handlers = {
        "NEW": Step2TrackReviewingHandler(store, notifier, dooray, PAJUNWI),
        "REVIEWING": Step3TrackPaymentWaitingHandler(store, notifier, dooray, PAJUNWI),
        "PAYMENT_WAITING": Step4CopyToPyconHandler(store, notifier, dooray, PAJUNWI, PYCON),
        "COPIED_TO_PYCON": Step5TrackPaymentInProgressHandler(store, notifier, dooray, PAJUNWI),
        "PAYMENT_IN_PROGRESS": Step6SyncAndCompleteHandler(store, notifier, dooray, PAJUNWI, PYCON),
        "COMPLETED": Step8UpdateSheetsHandler(store, notifier, sheets),
    }
    return StateEngine(handlers, store)


def test_full_flow_new_to_sheet_updated(store, notifier, dooray, mock_sheet):
    sheets, mock_ws = mock_sheet

    with resp_lib.RequestsMock() as rsps:
        # Step 2: NEW → REVIEWING (pajunwi now shows 검토 중)
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_REVIEWING},
                                  "body": {"content": "금액: 50,000원"}}})

        # Step 3: REVIEWING → PAYMENT_WAITING (pajunwi now shows 결제 대기 중)
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_PAYMENT_WAITING}}})

        # Step 4: PAYMENT_WAITING → COPIED_TO_PYCON (create PYCON task)
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "subject": "출장비 신청",
                                  "body": {"content": "금액: 50,000원"}}})
        rsps.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts",
                 json={"result": {"id": PYCON_TASK_ID}})

        # Step 5: COPIED_TO_PYCON → PAYMENT_IN_PROGRESS (pajunwi now shows 결제 중)
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_PAYMENT_IN_PROGRESS}}})

        # Step 6: PAYMENT_IN_PROGRESS → COMPLETED (sync body + PYCON shows 결제 완료)
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "body": {"content": "금액: 50,000원\n영수증 첨부"}}})
        rsps.add(resp_lib.PUT, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {}})
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_COMPLETED}}})
        rsps.add(resp_lib.POST, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}/set-workflow",
                 json={"result": None})

        store.upsert_task(PAJUNWI_TASK_ID, "NEW")
        engine = build_engine(store, notifier, dooray, sheets)

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "REVIEWING"
        assert store.get_task(PAJUNWI_TASK_ID)["amount"] == 50000

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "PAYMENT_WAITING"

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "COPIED_TO_PYCON"
        assert store.get_task(PAJUNWI_TASK_ID)["pycon_task_id"] == PYCON_TASK_ID

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "PAYMENT_IN_PROGRESS"

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "COMPLETED"

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "SHEET_UPDATED"

        mock_ws.append_row.assert_called_once()
        row = mock_ws.append_row.call_args[0][0]
        assert 50000 in row


def test_rejected_at_reviewing_stops_flow(store, notifier, dooray, mock_sheet):
    sheets, _ = mock_sheet

    with resp_lib.RequestsMock() as rsps:
        # Step 2: pajunwi shows 반려 → straight to REJECTED
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_REJECTED}}})

        store.upsert_task(PAJUNWI_TASK_ID, "NEW")
        engine = build_engine(store, notifier, dooray, sheets)

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "REJECTED"
        notifier.task_rejected.assert_called_once_with(PAJUNWI_TASK_ID)

        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "REJECTED"


def test_rejected_at_copied_to_pycon_stops_flow(store, notifier, dooray, mock_sheet):
    sheets, _ = mock_sheet

    with resp_lib.RequestsMock() as rsps:
        # Step 2: 검토 중
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_REVIEWING},
                                  "body": {"content": "금액: 10,000원"}}})
        # Step 3: 결제 대기 중
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_PAYMENT_WAITING}}})
        # Step 4: create PYCON task
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "subject": "출장비",
                                  "body": {"content": ""}}})
        rsps.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts",
                 json={"result": {"id": PYCON_TASK_ID}})
        # Step 5: pajunwi shows 반려
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID,
                                  "workflow": {"name": DOORAY_WORKFLOW_NAME_REJECTED}}})

        store.upsert_task(PAJUNWI_TASK_ID, "NEW")
        engine = build_engine(store, notifier, dooray, sheets)

        engine.process()  # NEW → REVIEWING
        engine.process()  # REVIEWING → PAYMENT_WAITING
        engine.process()  # PAYMENT_WAITING → COPIED_TO_PYCON
        engine.process()  # COPIED_TO_PYCON → REJECTED

        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "REJECTED"
        notifier.task_rejected.assert_called_once_with(PAJUNWI_TASK_ID)
