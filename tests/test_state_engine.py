import pytest
from unittest.mock import MagicMock
from src.state_engine import StateEngine


def make_handler(name, from_state, to_state, run_return=True):
    h = MagicMock()
    h.name = name
    h.from_state = from_state
    h.to_state = to_state
    h.run.return_value = run_return
    return h


def test_process_tasks_dispatches_to_correct_handler(store, notifier):
    """StateEngine calls the handler for each task in a handled state."""
    store.upsert_task("pj-001", "NEW")
    store.upsert_task("pj-002", "REVIEWING")

    step2 = make_handler("step2_review", "NEW", "REVIEWING")
    step3 = make_handler("step3_copy", "REVIEWING", "COPIED_TO_PYCON")

    engine = StateEngine({"NEW": step2, "REVIEWING": step3}, store)
    count = engine.process()

    assert count == 2
    step2.run.assert_called_once()
    step3.run.assert_called_once()


def test_process_tasks_ignores_unhandled_states(store, notifier):
    """Tasks in SHEET_UPDATED or REJECTED are not dispatched."""
    store.upsert_task("pj-001", "SHEET_UPDATED")
    store.upsert_task("pj-002", "REJECTED")

    step2 = make_handler("step2_review", "NEW", "REVIEWING")
    engine = StateEngine({"NEW": step2}, store)
    count = engine.process()

    assert count == 0
    step2.run.assert_not_called()


def test_process_tasks_counts_only_successful_transitions(store, notifier):
    """process() returns count of tasks that successfully transitioned."""
    store.upsert_task("pj-001", "NEW")
    store.upsert_task("pj-002", "NEW")

    step2_success = make_handler("step2_review", "NEW", "REVIEWING", run_return=True)
    step2_success.run.side_effect = [True, False]  # first succeeds, second fails

    engine = StateEngine({"NEW": step2_success}, store)
    count = engine.process()

    assert count == 1


def test_process_tasks_handler_exception_does_not_stop_others(store, notifier):
    """An exception in one task's handler doesn't skip other tasks."""
    store.upsert_task("pj-001", "NEW")
    store.upsert_task("pj-002", "NEW")

    step2 = make_handler("step2_review", "NEW", "REVIEWING")
    step2.run.side_effect = [RuntimeError("oops"), True]

    engine = StateEngine({"NEW": step2}, store)
    count = engine.process()

    assert count == 1  # second task still processed
