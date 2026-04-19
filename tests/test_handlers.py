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
