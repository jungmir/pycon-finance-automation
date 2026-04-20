"""
E2E test script: runs one poll cycle against real Dooray API with a temp SQLite DB.
Seeds the test task at PAYMENT_WAITING (current real state) and runs the engine.
"""
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Use test env values
os.environ.setdefault("DOORAY_API_TOKEN", "hy4iu238wiz3:Ai7Q-A67TFOY2myP3pppdw")
os.environ.setdefault("PAJUNWI_PROJECT_ID", "4247406253338896459")
os.environ.setdefault("PYCON_PROJECT_ID", "3745968899654628260")
os.environ.setdefault("DATABASE_PATH", "/tmp/e2e_test.db")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "e2e_placeholder")
os.environ.setdefault("SPREADSHEET_ID", "e2e_placeholder")
os.environ.setdefault("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/test")
os.environ.setdefault("POLL_INTERVAL_SECONDS", "60")

from unittest.mock import MagicMock
from src.store import Store
from src.notifier import Notifier
from src.clients.dooray import DoorayClient
from src.clients.sheets import SheetsClient
from src.state_engine import StateEngine
from src.handlers.step2_track_reviewing import Step2TrackReviewingHandler
from src.handlers.step3_track_payment_waiting import Step3TrackPaymentWaitingHandler
from src.handlers.step4_copy_to_pycon import Step4CopyToPyconHandler
from src.handlers.step5_track_payment_in_progress import Step5TrackPaymentInProgressHandler
from src.handlers.step6_sync_body import Step6SyncBodyHandler
from src.handlers.step7_detect_completion import Step7DetectCompletionHandler
from src.handlers.step8_update_sheets import Step8UpdateSheetsHandler

PAJUNWI = "4247406253338896459"
PYCON = "3745968899654628260"
TEST_TASK_ID = "4315010603439611752"

store = Store("/tmp/e2e_test.db")
notifier = MagicMock(spec=Notifier)
dooray = DoorayClient("hy4iu238wiz3:Ai7Q-A67TFOY2myP3pppdw")
sheets = MagicMock(spec=SheetsClient)

handlers = {
    "NEW": Step2TrackReviewingHandler(store, notifier, dooray, PAJUNWI),
    "REVIEWING": Step3TrackPaymentWaitingHandler(store, notifier, dooray, PAJUNWI),
    "PAYMENT_WAITING": Step4CopyToPyconHandler(store, notifier, dooray, PAJUNWI, PYCON),
    "COPIED_TO_PYCON": Step5TrackPaymentInProgressHandler(store, notifier, dooray, PAJUNWI),
    "PAYMENT_IN_PROGRESS": Step6SyncBodyHandler(store, notifier, dooray, PAJUNWI, PYCON),
    "BODY_SYNCED": Step7DetectCompletionHandler(store, notifier, dooray, PAJUNWI, PYCON),
    "COMPLETED": Step8UpdateSheetsHandler(store, notifier, sheets),
}
engine = StateEngine(handlers, store)

# Check current state in DB
existing = store.get_task(TEST_TASK_ID)
print(f"\n=== Current DB state: {existing} ===\n")

if existing is None:
    # Seed at PAYMENT_WAITING (matching current real pajunwi state)
    store.upsert_task(TEST_TASK_ID, "PAYMENT_WAITING")
    print(f"Seeded task {TEST_TASK_ID} at PAYMENT_WAITING")
else:
    print(f"Task already in DB at state: {existing['state']}")

print("\n=== Running engine poll ===\n")
transitions = engine.process()
print(f"\n=== Done: {transitions} transition(s) ===")

task = store.get_task(TEST_TASK_ID)
print(f"Task state after poll: {task}")
