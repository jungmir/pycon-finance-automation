import pytest
from src.store import Store


def test_upsert_and_get_task(store):
    """upsert_task inserts a new row; get_task retrieves it."""
    store.upsert_task("pj-001", "NEW")
    task = store.get_task("pj-001")

    assert task is not None
    assert task["pajunwi_task_id"] == "pj-001"
    assert task["state"] == "NEW"
    assert task["pycon_task_id"] is None
    assert task["amount"] is None


def test_upsert_updates_existing(store):
    """Second upsert_task call updates state without duplicating the row."""
    store.upsert_task("pj-001", "NEW")
    store.upsert_task("pj-001", "REVIEWING", amount=50000)

    task = store.get_task("pj-001")
    assert task["state"] == "REVIEWING"
    assert task["amount"] == 50000


def test_upsert_partial_update_preserves_fields(store):
    """Updating state does not overwrite fields not included in the call."""
    store.upsert_task("pj-001", "NEW", amount=75000)
    store.upsert_task("pj-001", "REVIEWING")  # no amount arg

    task = store.get_task("pj-001")
    assert task["amount"] == 75000  # preserved


def test_get_tasks_in_state(store):
    """get_tasks_in_state returns only tasks with matching state."""
    store.upsert_task("pj-001", "NEW")
    store.upsert_task("pj-002", "NEW")
    store.upsert_task("pj-003", "REVIEWING")

    new_tasks = store.get_tasks_in_state("NEW")
    assert len(new_tasks) == 2
    assert all(t["state"] == "NEW" for t in new_tasks)


def test_log_transition_records_history(store):
    """log_transition writes a row to state_history."""
    store.upsert_task("pj-001", "NEW")
    store.log_transition("pj-001", "NEW", "REVIEWING", "step2_review", True)

    count = store._conn.execute(
        "SELECT COUNT(*) FROM state_history WHERE pajunwi_task_id = 'pj-001'"
    ).fetchone()[0]
    assert count == 1


def test_count_active_tasks(store):
    """count_active_tasks excludes SHEET_UPDATED and REJECTED."""
    store.upsert_task("pj-001", "NEW")
    store.upsert_task("pj-002", "REVIEWING")
    store.upsert_task("pj-003", "SHEET_UPDATED")
    store.upsert_task("pj-004", "REJECTED")

    assert store.count_active_tasks() == 2


def test_get_task_returns_none_for_unknown(store):
    assert store.get_task("nonexistent") is None
