import logging

logger = logging.getLogger(__name__)


class StateEngine:
    def __init__(self, handlers: dict, store):
        """
        handlers: maps state string → handler instance
        e.g., {"NEW": step2_handler, "REVIEWING": step3_handler, ...}
        """
        self.handlers = handlers
        self.store = store

    def process(self) -> int:
        """Run one polling cycle. Returns count of successful state transitions."""
        successful = 0
        for state, handler in self.handlers.items():
            tasks = self.store.get_tasks_in_state(state)
            for task in tasks:
                try:
                    if handler.run(task):
                        successful += 1
                except Exception as exc:
                    logger.error(
                        f"[StateEngine] unexpected error in {handler.name} "
                        f"for task {task.get('pajunwi_task_id')}: {exc}"
                    )
        return successful
