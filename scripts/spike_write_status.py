"""
scripts/spike_write_status.py — Verify update_task_status PUT payload against real Dooray API.

Resolves Phase 3 SPIKE_REQUIRED: confirm {"workflowId": id} is the correct payload
format for the Dooray task status update endpoint.

WARNING: This writes to a REAL Dooray task. Point at a test/scratch task.

Usage:
  uv run --env-file .env python scripts/spike_write_status.py <pajunwi_task_id> <workflow_id>

Example (set back to 검토 전):
  uv run --env-file .env python scripts/spike_write_status.py <task_id> 4247406254190369622
"""
import os
import sys
import json
import requests

TOKEN = os.environ.get("DOORAY_API_TOKEN")
PAJUNWI_ID = os.environ.get("PAJUNWI_PROJECT_ID")
BASE = "https://api.dooray.com/project/v1"

if not all([TOKEN, PAJUNWI_ID]):
    print(__doc__)
    sys.exit(1)

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <task_id> <workflow_id>")
    sys.exit(1)

task_id, workflow_id = sys.argv[1], sys.argv[2]
HEADERS = {"Authorization": f"dooray-api {TOKEN}", "Content-Type": "application/json"}


def show(label, r):
    print(f"\n=== {label} ===")
    print(f"Status: {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:2000])
    except Exception:
        print(r.text[:500])


# Before state
r = requests.get(f"{BASE}/projects/{PAJUNWI_ID}/posts/{task_id}", headers=HEADERS, timeout=30)
show("BEFORE — current task state", r)
before_name = r.json().get("result", {}).get("workflow", {}).get("name")

# Attempt the PUT with {"workflowId": ...}
payload = {"workflowId": workflow_id}
print(f"\nPUT payload: {json.dumps(payload)}")
r2 = requests.put(
    f"{BASE}/projects/{PAJUNWI_ID}/posts/{task_id}",
    headers=HEADERS, json=payload, timeout=30,
)
show("PUT response", r2)

# After state
r3 = requests.get(f"{BASE}/projects/{PAJUNWI_ID}/posts/{task_id}", headers=HEADERS, timeout=30)
show("AFTER — task state", r3)
after_name = r3.json().get("result", {}).get("workflow", {}).get("name")

print(f"\n=== RESULT ===")
print(f"Before: {before_name!r}")
print(f"After:  {after_name!r}")
print(f"PUT success: {r2.status_code == 200}")
if r2.status_code != 200:
    print("FAILED — check payload format. Try alternative: {'workflow': {'id': workflow_id}}")
