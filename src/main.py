import logging
import schedule
import time
from datetime import datetime, UTC

from .config import Config
from .store import Store
from .notifier import Notifier
from .clients.dooray import DoorayClient, DOORAY_STATUS_NEW
from .clients.sheets import SheetsClient
from .state_engine import StateEngine
from .handlers.step2_track_reviewing import Step2TrackReviewingHandler
from .handlers.step3_track_payment_waiting import Step3TrackPaymentWaitingHandler
from .handlers.step4_copy_to_pycon import Step4CopyToPyconHandler
from .handlers.step5_track_payment_in_progress import Step5TrackPaymentInProgressHandler
from .handlers.step6_sync_and_complete import Step6SyncAndCompleteHandler
from .handlers.step8_update_sheets import Step8UpdateSheetsHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_last_poll_time: str = "never"


def build_engine(cfg: Config, store: Store, notifier: Notifier) -> StateEngine:
    dooray = DoorayClient(cfg.dooray_api_token)
    sheets = SheetsClient(cfg.google_service_account_json, cfg.spreadsheet_id)

    handlers = {
        "NEW": Step2TrackReviewingHandler(store, notifier, dooray, cfg.pajunwi_project_id),
        "REVIEWING": Step3TrackPaymentWaitingHandler(store, notifier, dooray, cfg.pajunwi_project_id),
        "PAYMENT_WAITING": Step4CopyToPyconHandler(
            store, notifier, dooray, cfg.pajunwi_project_id, cfg.pycon_project_id
        ),
        "COPIED_TO_PYCON": Step5TrackPaymentInProgressHandler(
            store, notifier, dooray, cfg.pajunwi_project_id
        ),
        "PAYMENT_IN_PROGRESS": Step6SyncAndCompleteHandler(
            store, notifier, dooray, cfg.pajunwi_project_id, cfg.pycon_project_id
        ),
        "COMPLETED": Step8UpdateSheetsHandler(store, notifier, sheets, dooray, cfg.pajunwi_project_id),
    }
    return StateEngine(handlers, store)


def discover_new_tasks(cfg: Config, store: Store, dooray: DoorayClient) -> int:
    """Pull tasks in NEW state from Dooray that aren't yet tracked in SQLite."""
    discovered = 0
    try:
        tasks = dooray.get_tasks(cfg.pajunwi_project_id, status=DOORAY_STATUS_NEW)
        for task in tasks:
            task_id = task.get("id") or task.get("postId")
            if task_id and store.get_task(task_id) is None:
                store.upsert_task(task_id, "NEW")
                logger.info(f"Discovered new task: {task_id}")
                discovered += 1
    except Exception as exc:
        logger.error(f"Failed to discover new tasks: {exc}")
    return discovered


def run_poll(cfg: Config, store: Store, notifier: Notifier, engine: StateEngine,
             dooray: DoorayClient) -> None:
    global _last_poll_time
    _last_poll_time = datetime.now(UTC).isoformat()
    logger.info("Poll cycle started")

    discovered = discover_new_tasks(cfg, store, dooray)
    if discovered:
        logger.info(f"Discovered {discovered} new task(s)")

    transitions = engine.process()
    logger.info(f"Poll cycle complete: {transitions} transition(s)")


def send_heartbeat(store: Store, notifier: Notifier) -> None:
    active = store.count_active_tasks()
    transitions = store.count_transitions_today()
    notifier.heartbeat(active, transitions, _last_poll_time)


def main() -> None:
    cfg = Config.from_env()  # fail-fast if env vars missing
    store = Store(cfg.database_path)
    notifier = Notifier(cfg.slack_webhook_url)
    dooray = DoorayClient(cfg.dooray_api_token)
    engine = build_engine(cfg, store, notifier)

    logger.info("Finance automation started")

    schedule.every(cfg.poll_interval_seconds).seconds.do(
        run_poll, cfg, store, notifier, engine, dooray
    )
    schedule.every().day.at("09:00").do(send_heartbeat, store, notifier)

    run_poll(cfg, store, notifier, engine, dooray)

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
