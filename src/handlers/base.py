import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    """Abstract base for state transition handlers with automatic retry.

    Subclasses set class attributes name, from_state, to_state and implement
    execute(task) which must return:
      - True or dict: success (dict fields are merged into the task record)
      - None: not ready, skip silently
      - raise Exception: failure, logged and Slack-notified

    run() retries execute() up to 3 times with exponential backoff (1s, 2s).
    """
    name: str
    from_state: str
    to_state: str

    def __init__(self, store, notifier):
        self.store = store
        self.notifier = notifier

    def run(self, task: dict) -> bool:
        pajunwi_task_id = task["pajunwi_task_id"]
        try:
            result = self._execute_with_retry(task)
        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"[{self.name}] task {pajunwi_task_id} failed: {error_msg}")
            self.store.log_transition(
                pajunwi_task_id, self.from_state, self.to_state,
                self.name, False, error_msg,
            )
            self.notifier.handler_error(self.name, pajunwi_task_id, error_msg)
            return False
        if result is None:
            return False
        if result is not True and not isinstance(result, dict):
            raise ValueError(f"[{self.name}] execute() returned invalid value: {result!r}")
        extra = result if isinstance(result, dict) else {}
        self.store.upsert_task(pajunwi_task_id, self.to_state, **extra)
        self.store.log_transition(
            pajunwi_task_id, self.from_state, self.to_state, self.name, True
        )
        return True

    def _execute_with_retry(self, task: dict):
        last_exc = None
        for attempt in range(3):
            try:
                result = self.execute(task)
                if result is None:
                    return None
                return result
            except Exception as exc:
                last_exc = exc
                logger.warning(f"[{self.name}] attempt {attempt+1}/3 failed: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise last_exc

    @abstractmethod
    def execute(self, task: dict):
        """Returns True, dict, None, or raises."""
