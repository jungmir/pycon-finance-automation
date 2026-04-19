import sqlite3
from datetime import datetime
from typing import Optional


class Store:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pajunwi_task_id TEXT UNIQUE NOT NULL,
                pycon_task_id   TEXT,
                state           TEXT NOT NULL,
                last_comment_id TEXT,
                amount          INTEGER,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS state_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pajunwi_task_id TEXT NOT NULL,
                from_state      TEXT NOT NULL,
                to_state        TEXT NOT NULL,
                handler         TEXT NOT NULL,
                success         INTEGER NOT NULL,
                error_msg       TEXT,
                executed_at     TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def upsert_task(self, pajunwi_task_id: str, state: str, **kwargs) -> None:
        now = datetime.utcnow().isoformat()
        existing = self.get_task(pajunwi_task_id)
        if existing is None:
            # Insert with state and any provided kwargs
            fields = {"pajunwi_task_id": pajunwi_task_id, "state": state, "created_at": now, "updated_at": now}
            fields.update(kwargs)
            columns = ", ".join(fields.keys())
            placeholders = ", ".join("?" * len(fields))
            self._conn.execute(
                f"INSERT INTO tasks ({columns}) VALUES ({placeholders})",
                list(fields.values()),
            )
        else:
            # Only update state, updated_at, and explicitly provided kwargs
            fields = {"state": state, "updated_at": now}
            fields.update(kwargs)
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            self._conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE pajunwi_task_id = ?",
                [*fields.values(), pajunwi_task_id],
            )
        self._conn.commit()

    def get_task(self, pajunwi_task_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE pajunwi_task_id = ?", (pajunwi_task_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_tasks_in_state(self, state: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE state = ?", (state,)
        ).fetchall()
        return [dict(r) for r in rows]

    def log_transition(
        self,
        pajunwi_task_id: str,
        from_state: str,
        to_state: str,
        handler: str,
        success: bool,
        error_msg: str = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        self._conn.execute(
            "INSERT INTO state_history "
            "(pajunwi_task_id, from_state, to_state, handler, success, error_msg, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pajunwi_task_id, from_state, to_state, handler, int(success), error_msg, now),
        )
        self._conn.commit()

    def count_transitions_today(self) -> int:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) FROM state_history WHERE executed_at LIKE ? AND success = 1",
            (f"{today}%",),
        ).fetchone()
        return row[0]

    def count_active_tasks(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE state NOT IN ('SHEET_UPDATED', 'REJECTED')"
        ).fetchone()
        return row[0]
