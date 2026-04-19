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
    DOORAY_STATUS_REVIEWING,
    DOORAY_STATUS_PAYMENT_PENDING,
    DOORAY_STATUS_COMPLETED,
)
from src.clients.sheets import SheetsClient
from src.state_engine import StateEngine
from src.handlers.step2_review import Step2ReviewHandler
from src.handlers.step3_copy import Step3CopyHandler
from src.handlers.step5_payment import Step5PaymentHandler
from src.handlers.step8_evidence import Step8EvidenceHandler
from src.handlers.step10_sync import Step10SyncHandler
from src.handlers.step11_sheets import Step11SheetsHandler

PAJUNWI = "pajunwi-proj"
PYCON = "pycon-proj"
BASE = "https://test.dooray.com/common/v1"
SPREADSHEET = "sheet-123"

PAJUNWI_TASK_ID = "task-001"
PYCON_TASK_ID = "pycon-task-001"
COMMENT_ID = "comment-001"


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def notifier():
    return MagicMock(spec=Notifier)


@pytest.fixture
def dooray():
    return DoorayClient("test.dooray.com", "tok")


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
        "NEW": Step2ReviewHandler(store, notifier, dooray, PAJUNWI),
        "REVIEWING": Step3CopyHandler(store, notifier, dooray, PAJUNWI, PYCON),
        "COPIED_TO_PYCON": Step5PaymentHandler(store, notifier, dooray, PAJUNWI, PYCON),
        "PAYMENT_PENDING": Step8EvidenceHandler(store, notifier, dooray, PAJUNWI, PYCON),
        "EVIDENCE_COPIED": Step10SyncHandler(store, notifier, dooray, PAJUNWI, PYCON),
        "COMPLETED": Step11SheetsHandler(store, notifier, sheets),
    }
    return StateEngine(handlers, store)


def test_full_flow_new_to_sheet_updated(store, notifier, dooray, mock_sheet):
    sheets, mock_ws = mock_sheet

    with resp_lib.RequestsMock() as rsps:
        # --- Step 2: NEW → REVIEWING ---
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "workflowClass": "registered",
                                  "subject": "출장비 신청",
                                  "body": {"content": "금액: 50,000원"}}})
        rsps.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {}})

        # --- Step 3: REVIEWING → COPIED_TO_PYCON ---
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "subject": "출장비 신청",
                                  "body": {"content": "금액: 50,000원"}}})
        rsps.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts",
                 json={"result": {"id": PYCON_TASK_ID}})

        # --- Step 5: COPIED_TO_PYCON → PAYMENT_PENDING ---
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID, "workflowClass": DOORAY_STATUS_PAYMENT_PENDING}})
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "workflowClass": DOORAY_STATUS_REVIEWING}})
        rsps.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {}})

        # --- Step 8: PAYMENT_PENDING → EVIDENCE_COPIED ---
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}/logs",
                 json={"result": [{"id": COMMENT_ID, "body": {"content": "영수증 첨부"}}]})
        rsps.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}/logs",
                 json={"result": {"id": "c-pycon-001"}})

        # --- Step 10: EVIDENCE_COPIED → COMPLETED ---
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID, "workflowClass": DOORAY_STATUS_COMPLETED}})
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "workflowClass": "working"}})
        rsps.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {}})

        # --- Set initial state ---
        store.upsert_task(PAJUNWI_TASK_ID, "NEW")
        engine = build_engine(store, notifier, dooray, sheets)

        # --- Run all steps in one process() call ---
        engine.process()

        # --- Verify final state and key data points ---
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "SHEET_UPDATED"
        assert store.get_task(PAJUNWI_TASK_ID)["amount"] == 50000
        assert store.get_task(PAJUNWI_TASK_ID)["pycon_task_id"] == PYCON_TASK_ID
        assert store.get_task(PAJUNWI_TASK_ID)["last_comment_id"] == COMMENT_ID

        # Verify Google Sheets was updated
        mock_ws.append_row.assert_called_once()
        row = mock_ws.append_row.call_args[0][0]
        assert 50000 in row  # amount in the ledger row


def test_rejected_flow_stops_at_step5(store, notifier, dooray, mock_sheet):
    sheets, _ = mock_sheet

    with resp_lib.RequestsMock() as rsps:
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "workflowClass": "registered",
                                  "subject": "출장비", "body": {"content": "금액: 10,000원"}}})
        rsps.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {}})
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{PAJUNWI_TASK_ID}",
                 json={"result": {"id": PAJUNWI_TASK_ID, "subject": "출장비", "body": {"content": ""}}})
        rsps.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts",
                 json={"result": {"id": PYCON_TASK_ID}})
        rsps.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID, "workflowClass": "closed"}})

        from src.clients.dooray import DOORAY_STATUS_REJECTED
        store.upsert_task(PAJUNWI_TASK_ID, "NEW")
        engine = build_engine(store, notifier, dooray, sheets)

        engine.process()  # NEW → REVIEWING → COPIED_TO_PYCON → REJECTED

        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "REJECTED"
        notifier.task_rejected.assert_called_once_with(PYCON_TASK_ID)

        # One more cycle — REJECTED tasks should not be processed
        engine.process()
        assert store.get_task(PAJUNWI_TASK_ID)["state"] == "REJECTED"  # unchanged
