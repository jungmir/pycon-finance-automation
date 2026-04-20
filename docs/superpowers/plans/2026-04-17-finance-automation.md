# Finance Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polling-based automation service that manages a 6-step finance approval workflow across two Dooray portals and Google Sheets, deployed on Railway PaaS with SQLite state persistence.

**Architecture:** A Python 3.12 service polls Dooray API every 5 minutes. A state engine maps each SQLite task state to a handler that performs the next automation step (Dooray status change, cross-portal copy, or Sheets update). All handlers implement check-before-act idempotency and share retry/notification logic via BaseHandler. Amount is parsed from task body at Step 2.

**Tech Stack:** Python 3.12, requests, schedule, gspread, google-auth, sqlite3 (stdlib), pytest, responses (HTTP mock in tests)

---

## File Map

| File | Responsibility |
|------|----------------|
| `src/config.py` | Env vars → Config dataclass, fail-fast startup validation |
| `src/store.py` | SQLite: tasks + state_history CRUD |
| `src/notifier.py` | Slack Incoming Webhook |
| `src/clients/__init__.py` | empty |
| `src/clients/dooray.py` | Dooray REST API wrapper (retry built-in) |
| `src/clients/sheets.py` | Google Sheets append via gspread |
| `src/handlers/__init__.py` | empty |
| `src/handlers/base.py` | BaseHandler: retry, error logging, Slack on failure |
| `src/handlers/step2_review.py` | NEW → REVIEWING, parses amount from body |
| `src/handlers/step3_copy.py` | REVIEWING → COPIED_TO_PYCON, creates task in pycon portal |
| `src/handlers/step5_payment.py` | COPIED_TO_PYCON → PAYMENT_PENDING (or REJECTED) |
| `src/handlers/step8_evidence.py` | PAYMENT_PENDING → EVIDENCE_COPIED, copies new comments |
| `src/handlers/step10_sync.py` | EVIDENCE_COPIED → COMPLETED, waits for pycon portal completion |
| `src/handlers/step11_sheets.py` | COMPLETED → SHEET_UPDATED, appends row to ledger |
| `src/state_engine.py` | Declarative state→handler mapping, per-poll dispatch |
| `src/main.py` | Entry: polling loop + daily heartbeat |
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/test_config.py` | Config validation |
| `tests/test_store.py` | Store CRUD |
| `tests/test_notifier.py` | Slack webhook (mocked) |
| `tests/test_dooray_client.py` | HTTP calls (responses library) |
| `tests/test_sheets_client.py` | gspread mock |
| `tests/test_state_engine.py` | State machine dispatch |
| `tests/test_handlers.py` | Handler logic: success, idempotent, error |
| `tests/test_integration.py` | End-to-end: NEW → SHEET_UPDATED |
| `scripts/spike_dooray.py` | One-time API exploration script |
| `docs/spike-dooray-api.md` | Spike findings (engineer fills after running spike) |
| `.env.example` | Env var template |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image |
| `railway.toml` | Railway deployment config |

---

## Handler Interface Contract

`execute()` return values — applies to all handlers:
- `True` → success, base handler transitions state
- `dict` → success + extra fields to persist (e.g., `{"amount": 50000}`)
- `None` → not ready yet, skip silently (no error logged, no transition)
- raise `Exception` → failure (base handler logs, sends Slack alert, leaves state unchanged)

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `src/clients/__init__.py`
- Create: `src/handlers/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.env.example`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p src/clients src/handlers tests scripts docs/spike-dooray-api
touch src/__init__.py src/clients/__init__.py src/handlers/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
requests==2.31.0
schedule==1.2.1
gspread==6.1.4
google-auth==2.29.0
responses==0.25.3
pytest==8.2.0
pytest-cov==5.0.0
```

- [ ] **Step 3: Write .env.example**

```env
DOORAY_API_TOKEN=your_token_here
DOORAY_DOMAIN=pycon.dooray.com

PAJUNWI_PROJECT_ID=1234567890
PYCON_PROJECT_ID=0987654321

GOOGLE_SERVICE_ACCOUNT_JSON=base64_encoded_json_here
SPREADSHEET_ID=your_spreadsheet_id

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz

POLL_INTERVAL_SECONDS=300
DATABASE_PATH=/data/state.db
```

- [ ] **Step 4: Write tests/conftest.py**

```python
import pytest
from unittest.mock import MagicMock
from src.store import Store


@pytest.fixture
def store():
    """In-memory SQLite store — isolated per test."""
    return Store(":memory:")


@pytest.fixture
def notifier():
    """Mock notifier — tracks calls without sending Slack messages."""
    return MagicMock()
```

- [ ] **Step 5: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/__init__.py src/clients/__init__.py src/handlers/__init__.py \
        tests/__init__.py tests/conftest.py .env.example
git commit -m "chore: project scaffold — directories, requirements, conftest"
```

---

## Task 2: Dooray API Spike

**Goal:** Discover the actual Dooray API auth format, status strings, and field names before writing any handler code. This task is exploratory — no TDD.

**Files:**
- Create: `scripts/spike_dooray.py`
- Create: `docs/spike-dooray-api.md` (filled by engineer after running)

- [ ] **Step 1: Write spike script**

```python
"""
scripts/spike_dooray.py — Dooray API exploration script.
Run once with real credentials to discover API shape.

Usage:
  DOORAY_API_TOKEN=xxx DOORAY_DOMAIN=pycon.dooray.com \
  PAJUNWI_PROJECT_ID=yyy python scripts/spike_dooray.py
"""
import os
import json
import requests

TOKEN = os.environ["DOORAY_API_TOKEN"]
DOMAIN = os.environ["DOORAY_DOMAIN"]
PAJUNWI_ID = os.environ["PAJUNWI_PROJECT_ID"]
BASE_URL = f"https://{DOMAIN}/common/v1"

# Try both common auth header formats
headers_v1 = {"Authorization": f"dooray-api {TOKEN}", "Content-Type": "application/json"}
headers_v2 = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def try_request(label, method, path, headers, **kwargs):
    url = f"{BASE_URL}{path}"
    print(f"\n=== {label} ===")
    print(f"URL: {url}")
    r = requests.request(method, url, headers=headers, **kwargs)
    print(f"Status: {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2, ensure_ascii=False)[:2000])
    except Exception:
        print(r.text[:500])
    return r


# 1. List tasks in pajunwi project (no filter)
r = try_request("List pajunwi tasks (dooray-api auth)", "GET",
                f"/projects/{PAJUNWI_ID}/posts", headers_v1,
                params={"size": 5})
if r.status_code != 200:
    print("\nRetrying with Bearer auth...")
    try_request("List pajunwi tasks (Bearer auth)", "GET",
                f"/projects/{PAJUNWI_ID}/posts", headers_v2,
                params={"size": 5})

# 2. Get project workflow states (to discover status strings)
try_request("Get project workflow", "GET",
            f"/projects/{PAJUNWI_ID}", headers_v1)

# 3. Get a single task if any exist
tasks = []
r2 = requests.get(f"{BASE_URL}/projects/{PAJUNWI_ID}/posts",
                  headers=headers_v1, params={"size": 1})
if r2.status_code == 200:
    result = r2.json().get("result", [])
    if result:
        task_id = result[0].get("id") or result[0].get("postId")
        if task_id:
            try_request(f"Get single task {task_id}", "GET",
                        f"/projects/{PAJUNWI_ID}/posts/{task_id}", headers_v1)
            try_request(f"Get task comments {task_id}", "GET",
                        f"/projects/{PAJUNWI_ID}/posts/{task_id}/logs", headers_v1)

print("\n\n=== RECORD THESE IN docs/spike-dooray-api.md ===")
print("1. Which auth header format worked?")
print("2. What is the field name for task status in the response?")
print("3. What are the status string values (new, reviewing, payment_pending, rejected, done)?")
print("4. What fields are present on a task (id, subject, body, workflowId, etc.)?")
print("5. What does the body field look like (content, mimeType)?")
print("6. What does a comment look like (id, body)?")
```

- [ ] **Step 2: Run the spike with real credentials**

```bash
DOORAY_API_TOKEN=<your_token> \
DOORAY_DOMAIN=pycon.dooray.com \
PAJUNWI_PROJECT_ID=<your_project_id> \
python scripts/spike_dooray.py 2>&1 | tee docs/spike-dooray-api-raw.txt
```

Expected: JSON responses printed. At minimum the task list endpoint returns 200.

- [ ] **Step 3: Fill in docs/spike-dooray-api.md**

Create `docs/spike-dooray-api.md` with this template filled in from the output:

```markdown
# Dooray API Spike Findings

**Date:** 2026-04-17

## Auth
- Header format: `Authorization: dooray-api <token>`  ← fill in actual
- Base URL: `https://pycon.dooray.com/common/v1`  ← confirm

## Task Status Strings (workflowClass or workflowId field name)
| Our state | Dooray API value |
|-----------|-----------------|
| NEW | `registered` ← verify |
| REVIEWING | `working` ← verify |
| PAYMENT_PENDING | `???` ← fill in |
| REJECTED | `???` ← fill in |
| COMPLETED | `done` ← verify |

## Task Object Fields
- Task ID field name: `id` or `postId`?  ← fill in
- Status field name: `workflowClass` or `workflowId`?  ← fill in
- Subject field: `subject`?
- Body field: `body.content`?

## Comment Object Fields
- Comment ID field: `id` or `logId`?  ← fill in
- Content field: `body.content`?  ← fill in

## Task Copy Fields (for Step 3 cross-portal copy)
Fields to include when creating a pycon portal task:
- [ ] subject
- [ ] body.content
- [ ] ... (add fields agreed with 파사모 team)

## Amount Format in Task Body
Example body text containing amount:
```
금액: 50,000원  ← paste actual example
```
Regex that matches: `금액[:\s]*([0-9,]+)\s*원`  ← confirm or update
```

- [ ] **Step 4: Update SPIKE_REQUIRED constants in src/clients/dooray.py**

After filling in the findings doc, open `src/clients/dooray.py` (created in Task 5) and replace the `# SPIKE_REQUIRED` placeholder values with actual values from the findings doc.

- [ ] **Step 5: Commit spike artifacts**

```bash
git add scripts/spike_dooray.py docs/spike-dooray-api.md
git commit -m "chore: Dooray API spike — findings documented"
```

---

## Task 3: Config Module

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import os
import pytest
from src.config import Config


def test_from_env_all_required(monkeypatch):
    """Config.from_env() returns a Config when all vars are set."""
    monkeypatch.setenv("DOORAY_API_TOKEN", "tok")
    monkeypatch.setenv("DOORAY_DOMAIN", "pycon.dooray.com")
    monkeypatch.setenv("PAJUNWI_PROJECT_ID", "111")
    monkeypatch.setenv("PYCON_PROJECT_ID", "222")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "eyJmb28iOiJiYXIifQ==")
    monkeypatch.setenv("SPREADSHEET_ID", "sheet1")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/x")

    cfg = Config.from_env()

    assert cfg.dooray_api_token == "tok"
    assert cfg.dooray_domain == "pycon.dooray.com"
    assert cfg.pajunwi_project_id == "111"
    assert cfg.pycon_project_id == "222"
    assert cfg.poll_interval_seconds == 300  # default
    assert cfg.database_path == "/data/state.db"  # default


def test_from_env_missing_required_raises(monkeypatch):
    """Config.from_env() raises EnvironmentError when vars are missing."""
    for key in ["DOORAY_API_TOKEN", "DOORAY_DOMAIN", "PAJUNWI_PROJECT_ID",
                "PYCON_PROJECT_ID", "GOOGLE_SERVICE_ACCOUNT_JSON",
                "SPREADSHEET_ID", "SLACK_WEBHOOK_URL"]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(EnvironmentError) as exc_info:
        Config.from_env()

    assert "DOORAY_API_TOKEN" in str(exc_info.value)


def test_from_env_custom_poll_interval(monkeypatch):
    """POLL_INTERVAL_SECONDS env var overrides the 300s default."""
    monkeypatch.setenv("DOORAY_API_TOKEN", "tok")
    monkeypatch.setenv("DOORAY_DOMAIN", "pycon.dooray.com")
    monkeypatch.setenv("PAJUNWI_PROJECT_ID", "111")
    monkeypatch.setenv("PYCON_PROJECT_ID", "222")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "e30=")
    monkeypatch.setenv("SPREADSHEET_ID", "sheet1")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/x")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")

    cfg = Config.from_env()
    assert cfg.poll_interval_seconds == 60
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Implement src/config.py**

```python
from dataclasses import dataclass
import os


@dataclass
class Config:
    dooray_api_token: str
    dooray_domain: str
    pajunwi_project_id: str
    pycon_project_id: str
    google_service_account_json: str  # base64-encoded service account JSON
    spreadsheet_id: str
    slack_webhook_url: str
    poll_interval_seconds: int
    database_path: str

    @classmethod
    def from_env(cls) -> "Config":
        required = [
            "DOORAY_API_TOKEN",
            "DOORAY_DOMAIN",
            "PAJUNWI_PROJECT_ID",
            "PYCON_PROJECT_ID",
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "SPREADSHEET_ID",
            "SLACK_WEBHOOK_URL",
        ]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(
            dooray_api_token=os.environ["DOORAY_API_TOKEN"],
            dooray_domain=os.environ["DOORAY_DOMAIN"],
            pajunwi_project_id=os.environ["PAJUNWI_PROJECT_ID"],
            pycon_project_id=os.environ["PYCON_PROJECT_ID"],
            google_service_account_json=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            spreadsheet_id=os.environ["SPREADSHEET_ID"],
            slack_webhook_url=os.environ["SLACK_WEBHOOK_URL"],
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
            database_path=os.environ.get("DATABASE_PATH", "/data/state.db"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: Config dataclass with startup env var validation"
```

---

## Task 4: Store Module

**Files:**
- Create: `src/store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_store.py
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_store.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.store'`

- [ ] **Step 3: Implement src/store.py**

```python
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
            self._conn.execute(
                "INSERT INTO tasks (pajunwi_task_id, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (pajunwi_task_id, state, now, now),
            )
        else:
            fields = {"state": state, "updated_at": now, **kwargs}
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_store.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/store.py tests/test_store.py
git commit -m "feat: Store — SQLite tasks and state_history"
```

---

## Task 5: Dooray Client

**Files:**
- Create: `src/clients/dooray.py`
- Create: `tests/test_dooray_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dooray_client.py
import responses as resp_lib
import pytest
from src.clients.dooray import DoorayClient


BASE = "https://test.dooray.com/common/v1"


@pytest.fixture
def client():
    return DoorayClient("test.dooray.com", "token123")


@resp_lib.activate
def test_get_tasks_returns_result_list(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts",
        json={"result": [{"id": "t1", "subject": "Test task"}]},
        status=200,
    )
    tasks = client.get_tasks("proj1")
    assert tasks == [{"id": "t1", "subject": "Test task"}]


@resp_lib.activate
def test_get_tasks_passes_status_filter(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts",
        json={"result": []},
        status=200,
    )
    client.get_tasks("proj1", status="registered")
    assert "workflowClass" in resp_lib.calls[0].request.url


@resp_lib.activate
def test_get_task_returns_single(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts/t1",
        json={"result": {"id": "t1", "subject": "Buy coffee"}},
        status=200,
    )
    task = client.get_task("proj1", "t1")
    assert task["id"] == "t1"


@resp_lib.activate
def test_update_task_status(client):
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/proj1/posts/t1",
        json={"result": {}},
        status=200,
    )
    client.update_task_status("proj1", "t1", "working")
    payload = resp_lib.calls[0].request.body
    assert "working" in payload


@resp_lib.activate
def test_create_task(client):
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/proj1/posts",
        json={"result": {"id": "t2"}},
        status=200,
    )
    result = client.create_task("proj1", "New task", "body content")
    assert result["id"] == "t2"


@resp_lib.activate
def test_get_comments(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts/t1/logs",
        json={"result": [{"id": "c1", "body": {"content": "증빙 첨부"}}]},
        status=200,
    )
    comments = client.get_comments("proj1", "t1")
    assert len(comments) == 1
    assert comments[0]["id"] == "c1"


@resp_lib.activate
def test_create_comment(client):
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/proj1/posts/t1/logs",
        json={"result": {"id": "c2"}},
        status=200,
    )
    result = client.create_comment("proj1", "t1", "영수증 첨부합니다")
    assert result["id"] == "c2"


@resp_lib.activate
def test_retries_on_server_error(client):
    """Client retries up to 3 times on 5xx before raising."""
    for _ in range(3):
        resp_lib.add(
            resp_lib.GET,
            f"{BASE}/projects/proj1/posts",
            json={"error": "server error"},
            status=500,
        )
    with pytest.raises(Exception):
        client.get_tasks("proj1")
    assert len(resp_lib.calls) == 3
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_dooray_client.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.clients.dooray'`

- [ ] **Step 3: Implement src/clients/dooray.py**

```python
import time
import requests
import logging

logger = logging.getLogger(__name__)

# SPIKE_REQUIRED: verify these values against docs/spike-dooray-api.md
DOORAY_STATUS_NEW = "registered"
DOORAY_STATUS_REVIEWING = "working"
DOORAY_STATUS_PAYMENT_PENDING = "paymentPending"  # SPIKE_REQUIRED
DOORAY_STATUS_REJECTED = "closed"                 # SPIKE_REQUIRED
DOORAY_STATUS_COMPLETED = "done"                  # SPIKE_REQUIRED

# SPIKE_REQUIRED: verify field names for task objects
TASK_ID_FIELD = "id"          # SPIKE_REQUIRED: "id" or "postId"?
TASK_STATUS_FIELD = "workflowClass"  # SPIKE_REQUIRED: "workflowClass" or "workflowId"?
COMMENT_ID_FIELD = "id"       # SPIKE_REQUIRED: "id" or "logId"?


class DoorayClient:
    def __init__(self, domain: str, token: str):
        self._base_url = f"https://{domain}/common/v1"
        self._session = requests.Session()
        # SPIKE_REQUIRED: verify auth header format
        self._session.headers.update({
            "Authorization": f"dooray-api {token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._base_url}{path}"
        last_exc = None
        for attempt in range(3):
            try:
                resp = self._session.request(method, url, timeout=30, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(f"Dooray request attempt {attempt+1}/3 failed: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise last_exc

    def get_tasks(self, project_id: str, status: str = None) -> list[dict]:
        params = {"size": 100, "page": 0}
        if status:
            params["workflowClass"] = status  # SPIKE_REQUIRED: verify param name
        data = self._request("GET", f"/projects/{project_id}/posts", params=params)
        return data.get("result", [])

    def get_task(self, project_id: str, task_id: str) -> dict:
        data = self._request("GET", f"/projects/{project_id}/posts/{task_id}")
        return data.get("result", {})

    def update_task_status(self, project_id: str, task_id: str, status: str) -> dict:
        # SPIKE_REQUIRED: verify payload field name and value format
        payload = {TASK_STATUS_FIELD: status}
        data = self._request("PUT", f"/projects/{project_id}/posts/{task_id}", json=payload)
        return data.get("result", {})

    def create_task(self, project_id: str, subject: str, body: str, **extra_fields) -> dict:
        payload = {
            "subject": subject,
            "body": {"mimeType": "text/x-markdown", "content": body},
            **extra_fields,
        }
        data = self._request("POST", f"/projects/{project_id}/posts", json=payload)
        return data.get("result", {})

    def get_comments(self, project_id: str, task_id: str) -> list[dict]:
        data = self._request("GET", f"/projects/{project_id}/posts/{task_id}/logs")
        return data.get("result", [])

    def create_comment(self, project_id: str, task_id: str, content: str) -> dict:
        payload = {"body": {"mimeType": "text/x-markdown", "content": content}}
        data = self._request("POST", f"/projects/{project_id}/posts/{task_id}/logs", json=payload)
        return data.get("result", {})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dooray_client.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/clients/dooray.py tests/test_dooray_client.py
git commit -m "feat: DoorayClient — REST wrapper with retry"
```

---

## Task 6: Notifier

**Files:**
- Create: `src/notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_notifier.py
import responses as resp_lib
import pytest
from src.notifier import Notifier

WEBHOOK = "https://hooks.slack.com/test"


@pytest.fixture
def notifier():
    return Notifier(WEBHOOK)


@resp_lib.activate
def test_task_copied_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.task_copied("pj-001", "2026 파이콘 장소 답사 활동비")
    assert len(resp_lib.calls) == 1
    body = resp_lib.calls[0].request.body
    assert "pj-001" in body
    assert "복사 완료" in body


@resp_lib.activate
def test_task_rejected_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.task_rejected("pycon-999")
    assert "반려" in resp_lib.calls[0].request.body


@resp_lib.activate
def test_handler_error_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.handler_error("step3_copy", "pj-001", "ConnectionError")
    body = resp_lib.calls[0].request.body
    assert "step3_copy" in body
    assert "ConnectionError" in body


@resp_lib.activate
def test_heartbeat_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.heartbeat(3, 12, "2026-04-17T05:00:00")
    body = resp_lib.calls[0].request.body
    assert "3" in body   # active tasks
    assert "12" in body  # transitions


@resp_lib.activate
def test_webhook_failure_does_not_raise(notifier):
    """A Slack failure should log but not propagate — automation must continue."""
    resp_lib.add(resp_lib.POST, WEBHOOK, body="error", status=500)
    notifier.task_copied("pj-001", "test")  # should not raise


@resp_lib.activate
def test_sheets_failure_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.sheets_failure("pj-001", "Quota exceeded")
    assert "시트" in resp_lib.calls[0].request.body
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_notifier.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.notifier'`

- [ ] **Step 3: Implement src/notifier.py**

```python
import json
import logging
import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook_url: str):
        self._url = webhook_url

    def _send(self, text: str) -> None:
        try:
            resp = requests.post(self._url, json={"text": text}, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(f"Slack notification failed: {exc}")

    def task_copied(self, pajunwi_task_id: str, subject: str) -> None:
        self._send(
            f"✅ [자동화] 업무 복사 완료\n"
            f"   파준위 #{pajunwi_task_id} → 파이콘 포털로 복사됨\n"
            f"   제목: {subject}"
        )

    def task_rejected(self, pycon_task_id: str) -> None:
        self._send(
            f"⚠️ [자동화] 파사모 반려 감지\n"
            f"   파이콘 포털 업무 #{pycon_task_id} 반려됨 — 수동 확인 필요"
        )

    def handler_error(self, handler_name: str, pajunwi_task_id: str, error: str) -> None:
        self._send(
            f"❌ [자동화] 핸들러 오류\n"
            f"   {handler_name} 실패 (업무 #{pajunwi_task_id}) — 다음 폴링에서 재시도 예정\n"
            f"   오류: {error}"
        )

    def heartbeat(self, active_tasks: int, transitions_today: int, last_poll: str) -> None:
        self._send(
            f"💚 [자동화] 일일 하트비트\n"
            f"   처리 중 업무: {active_tasks}건\n"
            f"   오늘 상태 전이: {transitions_today}건\n"
            f"   마지막 폴링: {last_poll}"
        )

    def sheets_failure(self, pajunwi_task_id: str, error: str) -> None:
        self._send(
            f"⚠️ [자동화] 구글 시트 갱신 실패\n"
            f"   업무 #{pajunwi_task_id} — 수동 시트 갱신 필요\n"
            f"   오류: {error}"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_notifier.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/notifier.py tests/test_notifier.py
git commit -m "feat: Notifier — Slack webhook with typed message methods"
```

---

## Task 7: BaseHandler

**Files:**
- Create: `src/handlers/base.py`
- Modify: `tests/test_handlers.py` (create with BaseHandler tests)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_handlers.py
import pytest
from unittest.mock import MagicMock, patch
from src.handlers.base import BaseHandler


class ConcreteHandler(BaseHandler):
    name = "test_handler"
    from_state = "STATE_A"
    to_state = "STATE_B"

    def __init__(self, store, notifier, return_value=True):
        super().__init__(store, notifier)
        self._return_value = return_value

    def execute(self, task):
        return self._return_value


class FailingHandler(BaseHandler):
    name = "failing_handler"
    from_state = "STATE_A"
    to_state = "STATE_B"

    def execute(self, task):
        raise RuntimeError("API timeout")


def make_task(pajunwi_task_id="pj-001", state="STATE_A"):
    return {"pajunwi_task_id": pajunwi_task_id, "state": state}


def test_run_success_transitions_state(store, notifier):
    store.upsert_task("pj-001", "STATE_A")
    handler = ConcreteHandler(store, notifier, return_value=True)

    result = handler.run(make_task())

    assert result is True
    assert store.get_task("pj-001")["state"] == "STATE_B"


def test_run_success_logs_transition(store, notifier):
    store.upsert_task("pj-001", "STATE_A")
    handler = ConcreteHandler(store, notifier, return_value=True)
    handler.run(make_task())

    history = store._conn.execute(
        "SELECT * FROM state_history WHERE pajunwi_task_id = 'pj-001'"
    ).fetchone()
    assert history["success"] == 1
    assert history["handler"] == "test_handler"


def test_run_returns_dict_merges_extra_fields(store, notifier):
    store.upsert_task("pj-001", "STATE_A")
    handler = ConcreteHandler(store, notifier, return_value={"pycon_task_id": "pyc-555"})
    handler.run(make_task())

    task = store.get_task("pj-001")
    assert task["pycon_task_id"] == "pyc-555"
    assert task["state"] == "STATE_B"


def test_run_none_skips_silently(store, notifier):
    """execute() returning None means 'not ready' — no state change, no error."""
    store.upsert_task("pj-001", "STATE_A")
    handler = ConcreteHandler(store, notifier, return_value=None)
    result = handler.run(make_task())

    assert result is False
    assert store.get_task("pj-001")["state"] == "STATE_A"  # unchanged
    notifier.handler_error.assert_not_called()


def test_run_exception_logs_error_and_notifies(store, notifier):
    store.upsert_task("pj-001", "STATE_A")
    handler = FailingHandler(store, notifier)
    result = handler.run(make_task())

    assert result is False
    assert store.get_task("pj-001")["state"] == "STATE_A"  # unchanged
    notifier.handler_error.assert_called_once()
    call_args = notifier.handler_error.call_args
    assert "failing_handler" in call_args[0]
    assert "pj-001" in call_args[0]


def test_run_exception_logs_failed_transition(store, notifier):
    store.upsert_task("pj-001", "STATE_A")
    handler = FailingHandler(store, notifier)
    handler.run(make_task())

    history = store._conn.execute(
        "SELECT * FROM state_history WHERE pajunwi_task_id = 'pj-001'"
    ).fetchone()
    assert history["success"] == 0
    assert "API timeout" in history["error_msg"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_handlers.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.handlers.base'`

- [ ] **Step 3: Implement src/handlers/base.py**

```python
import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseHandler(ABC):
    name: str       # must be set on subclass
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
            # "Not ready" — skip silently, no transition
            return False

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
                    return None  # Not ready — don't retry
                return result
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"[{self.name}] attempt {attempt+1}/3 failed: {exc}"
                )
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise last_exc

    @abstractmethod
    def execute(self, task: dict):
        """
        Perform the automation step.

        Returns:
            True       — success, no extra fields to persist
            dict       — success, dict is merged into the task row
            None       — not ready yet, skip silently
            (raises)   — failure, base handler catches and notifies
        """
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_handlers.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/handlers/base.py tests/test_handlers.py
git commit -m "feat: BaseHandler — retry, idempotency, Slack on failure"
```

---

## Task 8: Step 2 Handler — NEW → REVIEWING

**Files:**
- Create: `src/handlers/step2_review.py`
- Modify: `tests/test_handlers.py` (append Step 2 tests)

- [ ] **Step 1: Append failing tests to tests/test_handlers.py**

```python
# Append to tests/test_handlers.py

import responses as resp_lib
from src.handlers.step2_review import Step2ReviewHandler
from src.clients.dooray import DOORAY_STATUS_REVIEWING

PAJUNWI_PROJECT = "pajunwi-proj"
BASE = "https://test.dooray.com/common/v1"


def make_dooray_client(domain="test.dooray.com", token="tok"):
    from src.clients.dooray import DoorayClient
    return DoorayClient(domain, token)


@resp_lib.activate
def test_step2_transitions_to_reviewing(store, notifier):
    """Step 2 calls Dooray to change status, stores REVIEWING + amount."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "workflowClass": "registered",  # current: NEW
            "body": {"content": "금액: 50,000원\n출장비 신청"},
        }},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {}},
    )

    store.upsert_task("t1", "NEW")
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(store, notifier, dooray, PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "REVIEWING"
    assert task["amount"] == 50000


@resp_lib.activate
def test_step2_idempotent_when_already_reviewing(store, notifier):
    """If Dooray already shows REVIEWING, skip the PUT and still return True."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "workflowClass": DOORAY_STATUS_REVIEWING,
            "body": {"content": "금액: 30,000원"},
        }},
    )

    store.upsert_task("t1", "NEW")
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(store, notifier, dooray, PAJUNWI_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "NEW"})

    assert result is True
    assert len([c for c in resp_lib.calls if c.request.method == "PUT"]) == 0


def test_step2_parse_amount_with_comma():
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(MagicMock(), MagicMock(), dooray, "proj")
    assert handler._parse_amount("금액: 1,234,567원") == 1234567


def test_step2_parse_amount_no_match_returns_zero():
    dooray = make_dooray_client()
    handler = Step2ReviewHandler(MagicMock(), MagicMock(), dooray, "proj")
    assert handler._parse_amount("내용 없음") == 0
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_handlers.py -k "step2" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.handlers.step2_review'`

- [ ] **Step 3: Implement src/handlers/step2_review.py**

```python
import re
from .base import BaseHandler
from ..clients.dooray import DoorayClient, DOORAY_STATUS_REVIEWING

# SPIKE_REQUIRED: verify this regex against actual task body format
# Example body: "금액: 50,000원"
AMOUNT_RE = re.compile(r"금액[:\s]*([0-9,]+)\s*원")


class Step2ReviewHandler(BaseHandler):
    name = "step2_review"
    from_state = "NEW"
    to_state = "REVIEWING"

    def __init__(self, store, notifier, dooray: DoorayClient, pajunwi_project_id: str):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.project_id = pajunwi_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]

        # Check-before-act: read current Dooray state
        current = self.dooray.get_task(self.project_id, pajunwi_task_id)
        body_content = current.get("body", {}).get("content", "")
        amount = self._parse_amount(body_content)

        if current.get("workflowClass") == DOORAY_STATUS_REVIEWING:
            # Already in target state — just sync amount to SQLite
            return {"amount": amount}

        self.dooray.update_task_status(self.project_id, pajunwi_task_id, DOORAY_STATUS_REVIEWING)
        return {"amount": amount}

    def _parse_amount(self, body: str) -> int:
        match = AMOUNT_RE.search(body)
        if match:
            return int(match.group(1).replace(",", ""))
        return 0
```

- [ ] **Step 4: Run all handler tests**

```bash
pytest tests/test_handlers.py -v
```

Expected: all pass (7 base + 4 step2 = `11 passed`)

- [ ] **Step 5: Commit**

```bash
git add src/handlers/step2_review.py tests/test_handlers.py
git commit -m "feat: Step2ReviewHandler — detect NEW, set REVIEWING, parse amount"
```

---

## Task 9: Step 3 Handler — REVIEWING → COPIED_TO_PYCON

**Files:**
- Create: `src/handlers/step3_copy.py`
- Modify: `tests/test_handlers.py` (append Step 3 tests)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_handlers.py

import responses as resp_lib
from src.handlers.step3_copy import Step3CopyHandler

PYCON_PROJECT = "pycon-proj"


@resp_lib.activate
def test_step3_copies_task_to_pycon(store, notifier):
    """Step 3 creates a task in the pycon portal and stores pycon_task_id."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {
            "id": "t1",
            "subject": "출장비 신청",
            "body": {"content": "금액: 50,000원"},
        }},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {"id": "pycon-t1"}},
    )

    store.upsert_task("t1", "REVIEWING")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING"})

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "COPIED_TO_PYCON"
    assert task["pycon_task_id"] == "pycon-t1"


@resp_lib.activate
def test_step3_notifies_on_copy(store, notifier):
    """Step 3 sends a Slack success notification after copying."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t2",
        json={"result": {"id": "t2", "subject": "교통비", "body": {"content": ""}}},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts",
        json={"result": {"id": "pycon-t2"}},
    )

    store.upsert_task("t2", "REVIEWING")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({"pajunwi_task_id": "t2", "state": "REVIEWING"})

    notifier.task_copied.assert_called_once_with("t2", "교통비")


@resp_lib.activate
def test_step3_idempotent_when_pycon_task_already_exists(store, notifier):
    """If pycon_task_id is already set in store, skip POST and return True."""
    store.upsert_task("t1", "REVIEWING", pycon_task_id="existing-pycon-t1")
    dooray = make_dooray_client()
    handler = Step3CopyHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({"pajunwi_task_id": "t1", "state": "REVIEWING",
                          "pycon_task_id": "existing-pycon-t1"})

    assert result is True
    assert len(resp_lib.calls) == 0  # no API calls made
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_handlers.py -k "step3" -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/handlers/step3_copy.py**

```python
from .base import BaseHandler
from ..clients.dooray import DoorayClient


class Step3CopyHandler(BaseHandler):
    name = "step3_copy"
    from_state = "REVIEWING"
    to_state = "COPIED_TO_PYCON"

    def __init__(
        self,
        store,
        notifier,
        dooray: DoorayClient,
        pajunwi_project_id: str,
        pycon_project_id: str,
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]

        # Idempotency: if already copied, skip API call
        if task.get("pycon_task_id"):
            return {"pycon_task_id": task["pycon_task_id"]}

        # Fetch current task data from pajunwi portal
        source = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        subject = source.get("subject", "")
        body_content = source.get("body", {}).get("content", "")

        # SPIKE_REQUIRED: confirm which extra fields to include (agreed with 파사모 team)
        new_task = self.dooray.create_task(
            self.pycon_project_id,
            subject=subject,
            body=body_content,
        )
        pycon_task_id = new_task.get("id") or new_task.get("postId")

        self.notifier.task_copied(pajunwi_task_id, subject)
        return {"pycon_task_id": pycon_task_id}
```

- [ ] **Step 4: Run all handler tests**

```bash
pytest tests/test_handlers.py -v
```

Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add src/handlers/step3_copy.py tests/test_handlers.py
git commit -m "feat: Step3CopyHandler — copy pajunwi task to pycon portal"
```

---

## Task 10: Step 5 Handler — COPIED_TO_PYCON → PAYMENT_PENDING (or REJECTED)

**Files:**
- Create: `src/handlers/step5_payment.py`
- Modify: `tests/test_handlers.py` (append Step 5 tests)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_handlers.py

import responses as resp_lib
from src.handlers.step5_payment import Step5PaymentHandler
from src.clients.dooray import DOORAY_STATUS_PAYMENT_PENDING, DOORAY_STATUS_REJECTED


@resp_lib.activate
def test_step5_transitions_to_payment_pending(store, notifier):
    """If pycon task shows 결제대기, sync pajunwi and set PAYMENT_PENDING."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": DOORAY_STATUS_PAYMENT_PENDING}},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflowClass": "working"}},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert result is True
    assert store.get_task("t1")["state"] == "PAYMENT_PENDING"


@resp_lib.activate
def test_step5_returns_none_when_still_reviewing(store, notifier):
    """If pycon task is still in review, return None (not ready yet)."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": "working"}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert result is False
    assert store.get_task("t1")["state"] == "COPIED_TO_PYCON"  # unchanged


@resp_lib.activate
def test_step5_sets_rejected_and_notifies(store, notifier):
    """If pycon task is rejected, set REJECTED state and send Slack alert."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": DOORAY_STATUS_REJECTED}},
    )

    store.upsert_task("t1", "COPIED_TO_PYCON", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step5PaymentHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({
        "pajunwi_task_id": "t1", "state": "COPIED_TO_PYCON", "pycon_task_id": "pycon-t1"
    })

    assert store.get_task("t1")["state"] == "REJECTED"
    notifier.task_rejected.assert_called_once_with("pycon-t1")
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_handlers.py -k "step5" -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/handlers/step5_payment.py**

```python
from .base import BaseHandler
from ..clients.dooray import (
    DoorayClient,
    DOORAY_STATUS_PAYMENT_PENDING,
    DOORAY_STATUS_REJECTED,
)


class Step5PaymentHandler(BaseHandler):
    name = "step5_payment"
    from_state = "COPIED_TO_PYCON"
    to_state = "PAYMENT_PENDING"

    def __init__(
        self,
        store,
        notifier,
        dooray: DoorayClient,
        pajunwi_project_id: str,
        pycon_project_id: str,
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        pycon_task_id = task["pycon_task_id"]

        pycon_task = self.dooray.get_task(self.pycon_project_id, pycon_task_id)
        dooray_status = pycon_task.get("workflowClass")

        if dooray_status == DOORAY_STATUS_REJECTED:
            # Special path: set REJECTED directly, bypass normal transition
            self.store.upsert_task(pajunwi_task_id, "REJECTED")
            self.store.log_transition(
                pajunwi_task_id, "COPIED_TO_PYCON", "REJECTED", self.name, True
            )
            self.notifier.task_rejected(pycon_task_id)
            return None  # prevents base handler from applying another transition

        if dooray_status != DOORAY_STATUS_PAYMENT_PENDING:
            return None  # still in review, not ready

        # Check-before-act on pajunwi side
        pajunwi_task = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        if pajunwi_task.get("workflowClass") != DOORAY_STATUS_PAYMENT_PENDING:
            self.dooray.update_task_status(
                self.pajunwi_project_id, pajunwi_task_id, DOORAY_STATUS_PAYMENT_PENDING
            )

        return True
```

- [ ] **Step 4: Run all handler tests**

```bash
pytest tests/test_handlers.py -v
```

Expected: `17 passed`

- [ ] **Step 5: Commit**

```bash
git add src/handlers/step5_payment.py tests/test_handlers.py
git commit -m "feat: Step5PaymentHandler — sync PAYMENT_PENDING, handle REJECTED"
```

---

## Task 11: Step 8 Handler — PAYMENT_PENDING → EVIDENCE_COPIED

**Files:**
- Create: `src/handlers/step8_evidence.py`
- Modify: `tests/test_handlers.py` (append Step 8 tests)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_handlers.py

import responses as resp_lib
from src.handlers.step8_evidence import Step8EvidenceHandler


@resp_lib.activate
def test_step8_copies_new_comment_to_pycon(store, notifier):
    """Step 8 copies comments added after last_comment_id."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [
            {"id": "c1", "body": {"content": "영수증 첨부"}},
            {"id": "c2", "body": {"content": "카드 내역 첨부"}},
        ]},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1/logs",
        json={"result": {"id": "c3"}},
    )

    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1",
                      last_comment_id=None)
    dooray = make_dooray_client()
    handler = Step8EvidenceHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_PENDING",
        "pycon_task_id": "pycon-t1", "last_comment_id": None,
    })

    assert result is True
    task = store.get_task("t1")
    assert task["state"] == "EVIDENCE_COPIED"
    assert task["last_comment_id"] == "c2"  # last copied comment


@resp_lib.activate
def test_step8_skips_already_copied_comments(store, notifier):
    """Comments with id <= last_comment_id are not re-copied."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [
            {"id": "c1", "body": {"content": "이전 코멘트"}},
            {"id": "c2", "body": {"content": "새 코멘트"}},
        ]},
    )
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1/logs",
        json={"result": {"id": "c3"}},
    )

    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1",
                      last_comment_id="c1")
    dooray = make_dooray_client()
    handler = Step8EvidenceHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_PENDING",
        "pycon_task_id": "pycon-t1", "last_comment_id": "c1",
    })

    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 1  # only c2 was copied


@resp_lib.activate
def test_step8_returns_none_when_no_new_comments(store, notifier):
    """No new comments → return None (not ready), no state change."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1/logs",
        json={"result": [{"id": "c1", "body": {"content": "old"}}]},
    )

    store.upsert_task("t1", "PAYMENT_PENDING", pycon_task_id="pycon-t1",
                      last_comment_id="c1")
    dooray = make_dooray_client()
    handler = Step8EvidenceHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "PAYMENT_PENDING",
        "pycon_task_id": "pycon-t1", "last_comment_id": "c1",
    })

    assert result is False
    assert store.get_task("t1")["state"] == "PAYMENT_PENDING"
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_handlers.py -k "step8" -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/handlers/step8_evidence.py**

```python
from .base import BaseHandler
from ..clients.dooray import DoorayClient


class Step8EvidenceHandler(BaseHandler):
    name = "step8_evidence"
    from_state = "PAYMENT_PENDING"
    to_state = "EVIDENCE_COPIED"

    def __init__(
        self,
        store,
        notifier,
        dooray: DoorayClient,
        pajunwi_project_id: str,
        pycon_project_id: str,
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        pycon_task_id = task["pycon_task_id"]
        last_comment_id = task.get("last_comment_id")

        comments = self.dooray.get_comments(self.pajunwi_project_id, pajunwi_task_id)
        new_comments = self._filter_new(comments, last_comment_id)

        if not new_comments:
            return None  # not ready — no new evidence comments

        for comment in new_comments:
            content = comment.get("body", {}).get("content", "")
            self.dooray.create_comment(self.pycon_project_id, pycon_task_id, content)

        newest_id = new_comments[-1]["id"]
        return {"last_comment_id": newest_id}

    def _filter_new(self, comments: list[dict], last_id: str | None) -> list[dict]:
        if not last_id:
            return comments
        found = False
        result = []
        for comment in comments:
            if found:
                result.append(comment)
            if comment["id"] == last_id:
                found = True
        return result
```

- [ ] **Step 4: Run all handler tests**

```bash
pytest tests/test_handlers.py -v
```

Expected: `20 passed`

- [ ] **Step 5: Commit**

```bash
git add src/handlers/step8_evidence.py tests/test_handlers.py
git commit -m "feat: Step8EvidenceHandler — copy new evidence comments to pycon portal"
```

---

## Task 12: Sheets Client

**Files:**
- Create: `src/clients/sheets.py`
- Create: `tests/test_sheets_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sheets_client.py
import base64
import json
import pytest
from unittest.mock import patch, MagicMock
from src.clients.sheets import SheetsClient


FAKE_SA = base64.b64encode(json.dumps({
    "type": "service_account",
    "project_id": "test",
    "private_key_id": "key1",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test.iam.gserviceaccount.com",
    "client_id": "123",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}).encode()).decode()


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_append_row_calls_gspread(mock_sa):
    mock_worksheet = MagicMock()
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    client = SheetsClient(FAKE_SA, "sheet-id-123")
    client.append_row(["2026-04-17", "출장비", "파준위", 50000])

    mock_sa.assert_called_once()
    mock_sa.return_value.open_by_key.assert_called_once_with("sheet-id-123")
    mock_worksheet.append_row.assert_called_once_with(["2026-04-17", "출장비", "파준위", 50000])


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_sheets_client_decodes_base64_json(mock_sa):
    mock_sa.return_value.open_by_key.return_value.sheet1 = MagicMock()
    SheetsClient(FAKE_SA, "sheet-id")
    call_kwargs = mock_sa.call_args[0][0]
    assert call_kwargs["type"] == "service_account"
    assert call_kwargs["client_email"] == "test@test.iam.gserviceaccount.com"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_sheets_client.py -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/clients/sheets.py**

```python
import base64
import json
import gspread


class SheetsClient:
    def __init__(self, service_account_json_b64: str, spreadsheet_id: str):
        sa_json = json.loads(base64.b64decode(service_account_json_b64).decode())
        self._gc = gspread.service_account_from_dict(sa_json)
        self._spreadsheet_id = spreadsheet_id

    def append_row(self, values: list) -> None:
        """Append a row to the first sheet (sheet1) of the spreadsheet.

        SPIKE_REQUIRED: confirm spreadsheet column order with 파사모 team.
        Expected columns: [날짜, 항목, 신청팀, 금액, ...]
        """
        sheet = self._gc.open_by_key(self._spreadsheet_id).sheet1
        sheet.append_row(values)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sheets_client.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/clients/sheets.py tests/test_sheets_client.py
git commit -m "feat: SheetsClient — append row via gspread service account"
```

---

## Task 13: Step 10 Handler — EVIDENCE_COPIED → COMPLETED

**Files:**
- Create: `src/handlers/step10_sync.py`
- Modify: `tests/test_handlers.py` (append Step 10 tests)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_handlers.py

import responses as resp_lib
from src.handlers.step10_sync import Step10SyncHandler
from src.clients.dooray import DOORAY_STATUS_COMPLETED


@resp_lib.activate
def test_step10_transitions_when_pycon_completed(store, notifier):
    """If pycon task is COMPLETED, update pajunwi and set COMPLETED."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": DOORAY_STATUS_COMPLETED}},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {"id": "t1", "workflowClass": "working"}},
    )
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/{PAJUNWI_PROJECT}/posts/t1",
        json={"result": {}},
    )

    store.upsert_task("t1", "EVIDENCE_COPIED", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step10SyncHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "EVIDENCE_COPIED", "pycon_task_id": "pycon-t1"
    })

    assert result is True
    assert store.get_task("t1")["state"] == "COMPLETED"


@resp_lib.activate
def test_step10_returns_none_when_not_yet_approved(store, notifier):
    """If pycon task is not yet COMPLETED, return None."""
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/{PYCON_PROJECT}/posts/pycon-t1",
        json={"result": {"id": "pycon-t1", "workflowClass": "working"}},
    )

    store.upsert_task("t1", "EVIDENCE_COPIED", pycon_task_id="pycon-t1")
    dooray = make_dooray_client()
    handler = Step10SyncHandler(store, notifier, dooray, PAJUNWI_PROJECT, PYCON_PROJECT)
    result = handler.run({
        "pajunwi_task_id": "t1", "state": "EVIDENCE_COPIED", "pycon_task_id": "pycon-t1"
    })

    assert result is False
    assert store.get_task("t1")["state"] == "EVIDENCE_COPIED"
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_handlers.py -k "step10" -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/handlers/step10_sync.py**

```python
from .base import BaseHandler
from ..clients.dooray import DoorayClient, DOORAY_STATUS_COMPLETED


class Step10SyncHandler(BaseHandler):
    name = "step10_sync"
    from_state = "EVIDENCE_COPIED"
    to_state = "COMPLETED"

    def __init__(
        self,
        store,
        notifier,
        dooray: DoorayClient,
        pajunwi_project_id: str,
        pycon_project_id: str,
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        pycon_task_id = task["pycon_task_id"]

        pycon_task = self.dooray.get_task(self.pycon_project_id, pycon_task_id)
        if pycon_task.get("workflowClass") != DOORAY_STATUS_COMPLETED:
            return None  # not done yet

        # Check-before-act on pajunwi side
        pajunwi_task = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        if pajunwi_task.get("workflowClass") != DOORAY_STATUS_COMPLETED:
            self.dooray.update_task_status(
                self.pajunwi_project_id, pajunwi_task_id, DOORAY_STATUS_COMPLETED
            )

        return True
```

- [ ] **Step 4: Run all handler tests**

```bash
pytest tests/test_handlers.py -v
```

Expected: `24 passed`

- [ ] **Step 5: Commit**

```bash
git add src/handlers/step10_sync.py tests/test_handlers.py
git commit -m "feat: Step10SyncHandler — detect pycon completion, sync pajunwi"
```

---

## Task 14: Step 11 Handler — COMPLETED → SHEET_UPDATED

**Files:**
- Create: `src/handlers/step11_sheets.py`
- Modify: `tests/test_handlers.py` (append Step 11 tests)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_handlers.py

import responses as resp_lib
from unittest.mock import MagicMock, patch
from src.handlers.step11_sheets import Step11SheetsHandler


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_step11_appends_row_to_sheet(mock_sa, store, notifier):
    """Step 11 appends a ledger row and transitions to SHEET_UPDATED."""
    mock_worksheet = MagicMock()
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    from src.clients.sheets import SheetsClient
    import base64, json as _json
    sa_b64 = base64.b64encode(_json.dumps({"type": "service_account"}).encode()).decode()
    sheets = SheetsClient(sa_b64, "sheet1")

    store.upsert_task("t1", "COMPLETED", amount=75000)
    handler = Step11SheetsHandler(store, notifier, sheets)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COMPLETED", "amount": 75000})

    assert result is True
    assert store.get_task("t1")["state"] == "SHEET_UPDATED"
    mock_worksheet.append_row.assert_called_once()
    row = mock_worksheet.append_row.call_args[0][0]
    assert 75000 in row


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_step11_sheets_failure_notifies_but_does_not_crash(mock_sa, store, notifier):
    """Google Sheets error → Slack alert, state remains COMPLETED for retry."""
    mock_worksheet = MagicMock()
    mock_worksheet.append_row.side_effect = Exception("Quota exceeded")
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    from src.clients.sheets import SheetsClient
    import base64, json as _json
    sa_b64 = base64.b64encode(_json.dumps({"type": "service_account"}).encode()).decode()
    sheets = SheetsClient(sa_b64, "sheet1")

    store.upsert_task("t1", "COMPLETED", amount=50000)
    handler = Step11SheetsHandler(store, notifier, sheets)
    result = handler.run({"pajunwi_task_id": "t1", "state": "COMPLETED", "amount": 50000})

    assert result is False
    assert store.get_task("t1")["state"] == "COMPLETED"  # not changed
    notifier.handler_error.assert_called_once()
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
pytest tests/test_handlers.py -k "step11" -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/handlers/step11_sheets.py**

```python
from datetime import datetime
from .base import BaseHandler
from ..clients.sheets import SheetsClient


class Step11SheetsHandler(BaseHandler):
    name = "step11_sheets"
    from_state = "COMPLETED"
    to_state = "SHEET_UPDATED"

    def __init__(self, store, notifier, sheets: SheetsClient):
        super().__init__(store, notifier)
        self.sheets = sheets

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        amount = task.get("amount", 0)
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # SPIKE_REQUIRED: confirm column order with 파사모 team
        # Expected: [날짜, 파준위_업무_ID, 금액, ...]
        row = [today, pajunwi_task_id, amount]
        self.sheets.append_row(row)
        return True
```

- [ ] **Step 4: Run all handler tests**

```bash
pytest tests/test_handlers.py -v
```

Expected: `26 passed`

- [ ] **Step 5: Commit**

```bash
git add src/handlers/step11_sheets.py tests/test_handlers.py
git commit -m "feat: Step11SheetsHandler — append ledger row to Google Sheets"
```

---

## Task 15: State Engine

**Files:**
- Create: `src/state_engine.py`
- Create: `tests/test_state_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_state_engine.py
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_state_engine.py -v
```

Expected: `FAILED`

- [ ] **Step 3: Implement src/state_engine.py**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_state_engine.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/state_engine.py tests/test_state_engine.py
git commit -m "feat: StateEngine — declarative state→handler dispatch"
```

---

## Task 16: Main Entry Point

**Files:**
- Create: `src/main.py`

No unit tests for main.py — integration test covers this path end-to-end.

- [ ] **Step 1: Write src/main.py**

```python
import logging
import schedule
import time
from datetime import datetime

from .config import Config
from .store import Store
from .notifier import Notifier
from .clients.dooray import DoorayClient, DOORAY_STATUS_NEW
from .clients.sheets import SheetsClient
from .state_engine import StateEngine
from .handlers.step2_review import Step2ReviewHandler
from .handlers.step3_copy import Step3CopyHandler
from .handlers.step5_payment import Step5PaymentHandler
from .handlers.step8_evidence import Step8EvidenceHandler
from .handlers.step10_sync import Step10SyncHandler
from .handlers.step11_sheets import Step11SheetsHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_last_poll_time: str = "never"


def build_engine(cfg: Config, store: Store, notifier: Notifier) -> StateEngine:
    dooray = DoorayClient(cfg.dooray_domain, cfg.dooray_api_token)
    sheets = SheetsClient(cfg.google_service_account_json, cfg.spreadsheet_id)

    handlers = {
        "NEW": Step2ReviewHandler(store, notifier, dooray, cfg.pajunwi_project_id),
        "REVIEWING": Step3CopyHandler(
            store, notifier, dooray, cfg.pajunwi_project_id, cfg.pycon_project_id
        ),
        "COPIED_TO_PYCON": Step5PaymentHandler(
            store, notifier, dooray, cfg.pajunwi_project_id, cfg.pycon_project_id
        ),
        "PAYMENT_PENDING": Step8EvidenceHandler(
            store, notifier, dooray, cfg.pajunwi_project_id, cfg.pycon_project_id
        ),
        "EVIDENCE_COPIED": Step10SyncHandler(
            store, notifier, dooray, cfg.pajunwi_project_id, cfg.pycon_project_id
        ),
        "COMPLETED": Step11SheetsHandler(store, notifier, sheets),
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
    _last_poll_time = datetime.utcnow().isoformat()
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
    dooray = DoorayClient(cfg.dooray_domain, cfg.dooray_api_token)
    engine = build_engine(cfg, store, notifier)

    logger.info("Finance automation started")

    schedule.every(cfg.poll_interval_seconds).seconds.do(
        run_poll, cfg, store, notifier, engine, dooray
    )
    schedule.every().day.at("09:00").do(send_heartbeat, store, notifier)

    # Run once immediately on startup
    run_poll(cfg, store, notifier, engine, dooray)

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify imports resolve (no runtime errors on import)**

```bash
python -c "from src.main import build_engine; print('imports OK')"
```

Expected: `imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: main.py — polling loop, task discovery, daily heartbeat"
```

---

## Task 17: Integration Test — NEW → SHEET_UPDATED

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
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

TASK_ID = "task-001"
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


@resp_lib.activate
def test_full_flow_new_to_sheet_updated(store, notifier, dooray, mock_sheet):
    sheets, mock_ws = mock_sheet

    # --- Step 2: NEW → REVIEWING ---
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {"id": TASK_ID, "workflowClass": "registered",
                                  "subject": "출장비 신청",
                                  "body": {"content": "금액: 50,000원"}}})
    resp_lib.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {}})

    # --- Step 3: REVIEWING → COPIED_TO_PYCON ---
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {"id": TASK_ID, "subject": "출장비 신청",
                                  "body": {"content": "금액: 50,000원"}}})
    resp_lib.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts",
                 json={"result": {"id": PYCON_TASK_ID}})

    # --- Step 5: COPIED_TO_PYCON → PAYMENT_PENDING ---
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID, "workflowClass": DOORAY_STATUS_PAYMENT_PENDING}})
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {"id": TASK_ID, "workflowClass": DOORAY_STATUS_REVIEWING}})
    resp_lib.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {}})

    # --- Step 8: PAYMENT_PENDING → EVIDENCE_COPIED ---
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}/logs",
                 json={"result": [{"id": COMMENT_ID, "body": {"content": "영수증 첨부"}}]})
    resp_lib.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}/logs",
                 json={"result": {"id": "c-pycon-001"}})

    # --- Step 10: EVIDENCE_COPIED → COMPLETED ---
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID, "workflowClass": DOORAY_STATUS_COMPLETED}})
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {"id": TASK_ID, "workflowClass": "working"}})
    resp_lib.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {}})

    # --- Set initial state ---
    store.upsert_task(TASK_ID, "NEW")
    engine = build_engine(store, notifier, dooray, sheets)

    # --- Run each step ---
    # Step 2
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "REVIEWING"
    assert store.get_task(TASK_ID)["amount"] == 50000

    # Step 3
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "COPIED_TO_PYCON"
    assert store.get_task(TASK_ID)["pycon_task_id"] == PYCON_TASK_ID

    # Step 5
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "PAYMENT_PENDING"

    # Step 8
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "EVIDENCE_COPIED"
    assert store.get_task(TASK_ID)["last_comment_id"] == COMMENT_ID

    # Step 10
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "COMPLETED"

    # Step 11
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "SHEET_UPDATED"
    mock_ws.append_row.assert_called_once()
    row = mock_ws.append_row.call_args[0][0]
    assert 50000 in row  # amount in the ledger row


@resp_lib.activate
def test_rejected_flow_stops_at_step5(store, notifier, dooray, mock_sheet):
    sheets, _ = mock_sheet

    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {"id": TASK_ID, "workflowClass": "registered",
                                  "subject": "출장비", "body": {"content": "금액: 10,000원"}}})
    resp_lib.add(resp_lib.PUT, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {}})
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PAJUNWI}/posts/{TASK_ID}",
                 json={"result": {"id": TASK_ID, "subject": "출장비", "body": {"content": ""}}})
    resp_lib.add(resp_lib.POST, f"{BASE}/projects/{PYCON}/posts",
                 json={"result": {"id": PYCON_TASK_ID}})
    resp_lib.add(resp_lib.GET, f"{BASE}/projects/{PYCON}/posts/{PYCON_TASK_ID}",
                 json={"result": {"id": PYCON_TASK_ID, "workflowClass": "closed"}})

    from src.clients.dooray import DOORAY_STATUS_REJECTED
    store.upsert_task(TASK_ID, "NEW")
    engine = build_engine(store, notifier, dooray, sheets)

    engine.process()  # NEW → REVIEWING
    engine.process()  # REVIEWING → COPIED_TO_PYCON
    engine.process()  # COPIED_TO_PYCON → REJECTED

    assert store.get_task(TASK_ID)["state"] == "REJECTED"
    notifier.task_rejected.assert_called_once_with(PYCON_TASK_ID)

    # One more cycle — REJECTED tasks should not be processed
    engine.process()
    assert store.get_task(TASK_ID)["state"] == "REJECTED"  # unchanged
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_integration.py -v
```

Expected: `FAILED` (modules exist but test fixtures need wiring)

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Check coverage**

```bash
pytest tests/ --cov=src --cov-report=term-missing
```

Expected: `>= 85%` line coverage across all `src/` modules.

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration — full NEW→SHEET_UPDATED and REJECTED flows"
```

---

## Task 18: Docker + Railway Config

**Files:**
- Create: `Dockerfile`
- Create: `railway.toml`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# /data is mounted as Railway Volume for SQLite persistence
RUN mkdir -p /data

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 2: Write railway.toml**

```toml
[build]
  builder = "dockerfile"

[deploy]
  startCommand = "python -m src.main"
  restartPolicyType = "always"
```

- [ ] **Step 3: Build and smoke-test the image locally**

```bash
docker build -t pycon-finance-automation .
docker run --rm \
  -e DOORAY_API_TOKEN=fake \
  -e DOORAY_DOMAIN=pycon.dooray.com \
  -e PAJUNWI_PROJECT_ID=111 \
  -e PYCON_PROJECT_ID=222 \
  -e GOOGLE_SERVICE_ACCOUNT_JSON=eyJ0eXBlIjoic2VydmljZV9hY2NvdW50In0= \
  -e SPREADSHEET_ID=sheet1 \
  -e SLACK_WEBHOOK_URL=https://hooks.slack.com/fake \
  -e DATABASE_PATH=/tmp/state.db \
  pycon-finance-automation
```

Expected: Container starts, logs "Finance automation started", then attempts first poll (which will fail due to fake creds — that's expected for this smoke test; verify no crash on import or config init).

- [ ] **Step 4: Final full test run**

```bash
pytest tests/ -v --cov=src
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile railway.toml
git commit -m "feat: Dockerfile and railway.toml for Railway PaaS deployment"
```

---

## Post-Spike Checklist

After running Task 2 (Dooray API spike) and filling in `docs/spike-dooray-api.md`, update these values:

- [ ] `src/clients/dooray.py`: Replace all `SPIKE_REQUIRED` constants (status strings, field names, auth format)
- [ ] `src/handlers/step2_review.py`: Verify `AMOUNT_RE` regex against actual body format
- [ ] `src/handlers/step3_copy.py`: Add any extra fields required by 파사모 team to `create_task()` call
- [ ] `src/clients/sheets.py`: Confirm column order with 파사모 team and update `append_row()` call in step11
- [ ] Re-run full test suite after updates: `pytest tests/ -v`

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/gstack-plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/gstack-plan-eng-review` | Architecture & tests (required) | 1 | ✅ PASS | P1: config, BaseHandler, test coverage, heartbeat — all resolved |
| Design Review | `/gstack-plan-design-review` | UI/UX gaps | 1 | — | N/A (no UI) |
| DX Review | `/gstack-plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT:** Eng Review PASSED. Ready to implement. Run Task 2 (spike) first to resolve SPIKE_REQUIRED constants before writing handlers.
