import logging

logger = logging.getLogger(__name__)


class StateEngine:
    def __init__(self, handlers: dict, store):
        """
        handlers: maps state string → handler instance
        e.g., {"NEW": step2_handler, "REVIEWING": step3_handler, ...}
        Each handler must have:
          - .name (str): identifier for logging
          - .run(task: dict) -> bool: True if transition succeeded, False/None to skip
        """
        self.handlers = handlers
        self.store = store

    def process(self) -> int:
        """Run one polling cycle. Returns count of successful state transitions."""
        successful = 0
        # Snapshot tasks per state at the START of the cycle to prevent cascade
        # Tasks that just transitioned in this cycle won't be picked up by later handlers
        state_snapshot = {state: self.store.get_tasks_in_state(state) for state in self.handlers}
        for state, handler in self.handlers.items():
            tasks = state_snapshot[state]
            for task in tasks:
                try:
                    if handler.run(task):
                        successful += 1
                except Exception as exc:
                    logger.error(
                        f"[StateEngine] unexpected error in {handler.name} "
                        f"(state: {state}) for task {task.get('pajunwi_task_id')}: {exc}"
                    )
        return successful
