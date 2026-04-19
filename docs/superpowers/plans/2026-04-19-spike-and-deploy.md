# Dooray Spike, Team Alignment & Railway Deployment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all `SPIKE_REQUIRED` unknowns in the codebase, confirm team-agreed field mappings, and deploy the automation service to Railway PaaS.

**Architecture:** Three sequential phases — (1) run the Dooray API spike script to discover real field names and status strings, update code constants; (2) confirm Step 3 copy fields and Step 11 column order with 파사모 team, then finalize those handlers; (3) deploy to Railway with all env vars and a persistent Volume for SQLite.

**Tech Stack:** Python 3.12, Dooray REST API, Google Sheets via gspread, Railway PaaS (Dockerfile + railway.toml already in repo), SQLite (Railway Volume).

---

## File Map

| File | Change |
|------|--------|
| `docs/spike-dooray-api.md` | Fill in all `← verify` / `??? ← fill in` rows |
| `src/clients/dooray.py` | Update 7 constants, remove SPIKE_REQUIRED comments |
| `src/handlers/step2_review.py` | Fix idempotency field name, verify AMOUNT_RE regex |
| `src/handlers/step3_copy.py` | Add confirmed extra_fields to create_task call |
| `src/handlers/step11_sheets.py` | Fix column order, add idempotency check |
| `tests/test_handlers.py` | Update any tests that break due to field name changes |

---

## Task 1: Dooray API Spike — Discover Real Field Names

**Prerequisite:** Real credentials for `DOORAY_API_TOKEN`, `DOORAY_DOMAIN`, `PAJUNWI_PROJECT_ID`.

**Files:**
- Run: `scripts/spike_dooray.py`
- Update: `docs/spike-dooray-api.md`
- Modify: `src/clients/dooray.py`
- Modify: `src/handlers/step2_review.py`

- [ ] **Step 1: Run the spike script**

```bash
DOORAY_API_TOKEN=<real-token> \
DOORAY_DOMAIN=pycon.dooray.com \
PAJUNWI_PROJECT_ID=<real-project-id> \
python scripts/spike_dooray.py 2>&1 | tee /tmp/spike-output.txt
```

Expected: Several JSON blobs printed. Note HTTP 200 responses. If you see 401, the auth header format is wrong — try `Bearer` instead of `dooray-api`.

- [ ] **Step 2: Fill in docs/spike-dooray-api.md**

Open `/tmp/spike-output.txt` and answer each question in `docs/spike-dooray-api.md`:

1. Auth header — did `dooray-api <token>` work, or did `Bearer <token>` work?
2. Task status strings — what value appears in the task object for each state?
3. Task ID field — `id` or `postId`?
4. Status field name — `workflowClass` or `workflowId`?
5. Comment ID field — `id` or `logId`?
6. Filter query param name — what param filters tasks by status in GET /posts?
7. Amount format — paste a real task body, confirm or update the regex.

Update the markdown table in `docs/spike-dooray-api.md` with real values.

- [ ] **Step 3: Update src/clients/dooray.py constants**

Replace the SPIKE_REQUIRED block at the top of `src/clients/dooray.py` with confirmed values.
Example (replace values with actual findings from Step 2):

```python
# Verified against Dooray API on YYYY-MM-DD (see docs/spike-dooray-api.md)
DOORAY_STATUS_NEW = "registered"          # confirmed
DOORAY_STATUS_REVIEWING = "working"       # confirmed
DOORAY_STATUS_PAYMENT_PENDING = "???"     # ← replace with real value
DOORAY_STATUS_REJECTED = "???"            # ← replace with real value
DOORAY_STATUS_COMPLETED = "???"           # ← replace with real value

TASK_ID_FIELD = "???"          # "id" or "postId" — fill in
TASK_STATUS_FIELD = "???"      # "workflowClass" or "workflowId" — fill in
COMMENT_ID_FIELD = "???"       # "id" or "logId" — fill in
```

Also update auth header if `Bearer` was needed:
```python
self._session.headers.update({
    "Authorization": f"Bearer {token}",  # or "dooray-api {token}" — whichever worked
    "Content-Type": "application/json",
})
```

Also fix the filter param in `get_tasks()` to the confirmed query param name:
```python
def get_tasks(self, project_id: str, status: str = None) -> list[dict]:
    params = {"size": 100, "page": 0}
    if status:
        params["<confirmed-param-name>"] = status  # e.g. "workflowClass" or "workflowId"
    ...
```

Also fix the payload field in `update_task_status()`:
```python
def update_task_status(self, project_id: str, task_id: str, status: str) -> dict:
    payload = {"<confirmed-field-name>": status}  # e.g. "workflowClass" or "workflowId"
    ...
```

- [ ] **Step 4: Fix idempotency check in step2_review.py**

The idempotency check reads `current.get("workflowClass")`. Update to use the confirmed field name:

```python
# src/handlers/step2_review.py
if current.get("<TASK_STATUS_FIELD>") == DOORAY_STATUS_REVIEWING:
    return {"amount": amount}
```

Also verify the AMOUNT_RE regex against a real task body from the spike output. If the format differs from `금액: 50,000원`, update the regex:

```python
AMOUNT_RE = re.compile(r"금액[:\s]*([0-9,]+)\s*원")  # update if actual format differs
```

Remove the `# SPIKE_REQUIRED` comment line above it once confirmed.

- [ ] **Step 5: Run tests to verify nothing broke**

```bash
venv/bin/pytest tests/test_dooray_client.py tests/test_handlers.py -v
```

Expected: All tests pass. If any test uses the old field name (e.g. `"workflowClass"` in a mock response), update the mock to use the real field name.

- [ ] **Step 6: Commit**

```bash
git add docs/spike-dooray-api.md src/clients/dooray.py src/handlers/step2_review.py tests/
git commit -m "feat: update Dooray constants from API spike findings"
```

---

## Task 2: Confirm Step 3 Copy Fields with 파사모 Team

**Prerequisite:** Human discussion with 파사모 team — which fields should be included when copying a pajunwi task to the pycon portal.

**Files:**
- Modify: `src/handlers/step3_copy.py`
- Update: `docs/spike-dooray-api.md` (Task Copy Fields section)

- [ ] **Step 1: Confirm field list with 파사모 team**

Ask 파사모 team: when we copy a task from pajunwi portal to pycon portal, which fields should be included beyond `subject` and `body`? Options typically include:
- `milestone` — link to a milestone
- `tags` — labels/categories
- `assignees` — responsible members
- `dueDate` — deadline

Record the agreed fields in `docs/spike-dooray-api.md` under "Task Copy Fields".

- [ ] **Step 2: Update step3_copy.py**

Add the agreed extra_fields to the `create_task` call. Consult the Dooray API docs or spike output for the exact payload key names.

Example — if team wants subject + body only (no extras):
```python
# src/handlers/step3_copy.py
def execute(self, task: dict) -> dict:
    pajunwi_task_id = task["pajunwi_task_id"]
    if task.get("pycon_task_id"):
        return {"pycon_task_id": task["pycon_task_id"]}

    source = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
    subject = source.get("subject", "")
    body_content = source.get("body", {}).get("content", "")

    # No extra fields required per 파사모 agreement on YYYY-MM-DD
    new_task = self.dooray.create_task(
        self.pycon_project_id,
        subject=subject,
        body=body_content,
    )
    pycon_task_id = new_task.get(TASK_ID_FIELD)
    if not pycon_task_id:
        raise ValueError(f"create_task response missing '{TASK_ID_FIELD}' field")

    self.notifier.task_copied(pajunwi_task_id, subject)
    return {"pycon_task_id": pycon_task_id}
```

If extra fields are required (e.g. milestone):
```python
new_task = self.dooray.create_task(
    self.pycon_project_id,
    subject=subject,
    body=body_content,
    milestone=source.get("milestone"),  # example extra field
)
```

- [ ] **Step 3: Run tests**

```bash
venv/bin/pytest tests/test_handlers.py -v -k "step3"
```

Expected: All step3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/handlers/step3_copy.py docs/spike-dooray-api.md
git commit -m "feat: Step3 — use confirmed copy fields per 파사모 agreement"
```

---

## Task 3: Step 11 — Fix Column Order and Add Idempotency

**Prerequisite:** Human discussion with 파사모 team — column order for Google Sheets ledger row, and whether duplicate rows are acceptable or need prevention.

**Files:**
- Modify: `src/handlers/step11_sheets.py`
- Modify: `src/clients/sheets.py` (if idempotency requires reading rows)
- Modify: `tests/test_handlers.py`

- [ ] **Step 1: Confirm column order with 파사모 team**

Ask: what are the column headers in the Google Sheet, in order? Example:
```
A: 날짜 | B: 업무ID | C: 신청팀 | D: 금액 | E: 비고
```

Also confirm: what is the idempotency strategy?
- Option A: Skip append if a row with the same `pajunwi_task_id` already exists (requires reading the sheet first)
- Option B: Rely on SHEET_UPDATED state preventing re-entry (current behavior — safe if state is reliable)

If Option B is accepted (recommended): no code change needed for idempotency — the state machine already prevents double-write. Just fix column order.

If Option A is required: need to add `find_row_by_task_id()` to SheetsClient.

- [ ] **Step 2: Update step11_sheets.py with confirmed column order**

Replace the placeholder row with the agreed columns. Example (assuming columns: 날짜, 업무ID, 금액):
```python
# src/handlers/step11_sheets.py
def execute(self, task: dict):
    pajunwi_task_id = task["pajunwi_task_id"]
    amount = task.get("amount", 0)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Column order confirmed with 파사모 team on YYYY-MM-DD
    # A: 날짜, B: 업무ID, C: 금액
    row = [today, pajunwi_task_id, amount]
    self.sheets.append_row(row)
    return True
```

Adjust the column list to match the real spreadsheet.

- [ ] **Step 3: (If Option A) Add idempotency via sheet lookup**

Only do this step if the team requires explicit de-dup. Skip if Option B was chosen.

Add to `src/clients/sheets.py`:
```python
def find_row_by_value(self, col_index: int, value: str) -> bool:
    """Return True if any row has `value` in column `col_index` (0-based)."""
    all_rows = self._ws.get_all_values()
    return any(row[col_index] == value for row in all_rows if len(row) > col_index)
```

Update `step11_sheets.py`:
```python
def execute(self, task: dict):
    pajunwi_task_id = task["pajunwi_task_id"]
    # Column B (index 1) holds the task ID
    if self.sheets.find_row_by_value(1, pajunwi_task_id):
        return True  # already written — idempotent skip

    amount = task.get("amount", 0)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    row = [today, pajunwi_task_id, amount]
    self.sheets.append_row(row)
    return True
```

- [ ] **Step 4: Update test for step11 column order**

In `tests/test_handlers.py`, find the step11 test and update the expected row:

```python
def test_step11_appends_correct_row(store, notifier, mock_sheets):
    store.upsert_task("task-001", "COMPLETED", pycon_task_id="pycon-001", amount=75000)
    task = store.get_task("task-001")
    handler = Step11SheetsHandler(store, notifier, mock_sheets)

    with patch("src.handlers.step11_sheets.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-04-19"
        handler.run(task)

    mock_sheets.append_row.assert_called_once()
    row = mock_sheets.append_row.call_args[0][0]
    assert row[0] == "2026-04-19"
    assert row[1] == "task-001"
    assert row[2] == 75000
```

- [ ] **Step 5: Run tests**

```bash
venv/bin/pytest tests/test_handlers.py -v -k "step11"
```

Expected: All step11 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/handlers/step11_sheets.py src/clients/sheets.py tests/test_handlers.py
git commit -m "feat: Step11 — confirmed column order, idempotency via state machine"
```

---

## Task 4: Railway Deployment

**Prerequisite:** All `SPIKE_REQUIRED` items resolved (Task 1 complete). Railway account with access to the pycon-finance-automation project.

**Files:**
- No code changes — Dockerfile and railway.toml already exist.
- Create: Railway project via Railway dashboard or CLI.

- [ ] **Step 1: Install Railway CLI**

```bash
brew install railway
railway login
```

Expected: Browser opens for OAuth. After login, `railway whoami` prints your email.

- [ ] **Step 2: Create Railway project and link repo**

```bash
cd /Users/jungmir/Projects/pycon/pycon-finance-automation
railway init
```

Choose: "Create new project". Name it `pycon-finance-automation`.

Or via dashboard: railway.app → New Project → Deploy from GitHub → select this repo → choose `master` branch.

- [ ] **Step 3: Add Railway Volume for SQLite persistence**

In Railway dashboard:
1. Go to project → Service → "Add Volume"
2. Mount path: `/data`
3. This gives the SQLite database a persistent disk that survives redeploys.

Alternatively via CLI:
```bash
railway volume create --mount-path /data
```

- [ ] **Step 4: Set all required environment variables**

```bash
railway variables set \
  DOORAY_API_TOKEN="<real-token>" \
  DOORAY_DOMAIN="pycon.dooray.com" \
  PAJUNWI_PROJECT_ID="<real-id>" \
  PYCON_PROJECT_ID="<real-id>" \
  GOOGLE_SERVICE_ACCOUNT_JSON="<base64-encoded-json>" \
  SPREADSHEET_ID="<real-spreadsheet-id>" \
  SLACK_WEBHOOK_URL="<real-webhook-url>" \
  DATABASE_PATH="/data/state.db" \
  POLL_INTERVAL_SECONDS="300"
```

Encode the Google service account JSON to base64:
```bash
base64 -i service-account.json | tr -d '\n'
```

- [ ] **Step 5: Deploy**

```bash
railway up
```

Or push to master — Railway auto-deploys on push if GitHub integration is set up.

- [ ] **Step 6: Verify deployment**

```bash
railway logs --tail 50
```

Expected log lines (from `src/main.py`):
```
Finance automation started. Polling every 300s.
[Heartbeat] Active tasks: 0, transitions today: 0
```

If you see an error like `Missing required environment variables`, check Step 4.

If you see `EnvironmentError` about Google service account, the base64 encoding may have newlines — re-encode with `tr -d '\n'`.

- [ ] **Step 7: Smoke test with a real task**

1. Create a new task in the pajunwi Dooray portal (or use an existing one).
2. Wait up to 5 minutes (one poll cycle).
3. Check the pajunwi portal — the task should move to `working` (REVIEWING) state.
4. Check Slack — you should see a notification.
5. Check Railway logs for transition log lines.

- [ ] **Step 8: Record deployment details**

Add a section to `docs/spike-dooray-api.md` (or a new `docs/deployment.md`) recording:
- Railway project URL
- Which Volume is attached
- Date of first successful deployment

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — |

**VERDICT:** NO REVIEWS YET
