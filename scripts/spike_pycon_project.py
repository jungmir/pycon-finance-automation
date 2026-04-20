"""
scripts/spike_pycon_project.py — PYCON project workflow and task structure spike.

Resolves Phase 2 SPIKE_REQUIRED items:
  1. PYCON project (2365812689445903608) workflows
  2. Amount regex validation against real pajunwi task bodies
  3. Task copy fields (what's available to copy to PYCON portal)

Usage:
  uv run --env-file .env python scripts/spike_pycon_project.py
"""
import os
import re
import json
import sys
import requests

TOKEN = os.environ.get("DOORAY_API_TOKEN")
PAJUNWI_ID = os.environ.get("PAJUNWI_PROJECT_ID")
PYCON_ID = os.environ.get("PYCON_PROJECT_ID")
BASE = "https://api.dooray.com/project/v1"

if not all([TOKEN, PAJUNWI_ID, PYCON_ID]):
    print(__doc__)
    sys.exit(1)

HEADERS = {"Authorization": f"dooray-api {TOKEN}", "Content-Type": "application/json"}

AMOUNT_RE = re.compile(r"금액[:\s]*([0-9,]+)\s*원")


def get(path, **params):
    url = f"{BASE}{path}"
    print(f"\n=== GET {path} ===")
    r = requests.get(url, headers=HEADERS, params=params or None, timeout=30)
    print(f"Status: {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2, ensure_ascii=False)[:3000])
        return body
    except Exception:
        print(r.text[:300])
        return {}


# 1. PYCON project info
get(f"/projects/{PYCON_ID}")

# 2. PYCON project workflows — main goal
get(f"/projects/{PYCON_ID}/workflows")

# 3. Recent PYCON tasks (to see workflow states in use)
pycon_tasks = get(f"/projects/{PYCON_ID}/posts", size=3)

# 4. Recent pajunwi tasks — validate amount regex
print("\n\n=== Amount regex validation against real pajunwi task bodies ===")
pajunwi_tasks = requests.get(
    f"{BASE}/projects/{PAJUNWI_ID}/posts",
    headers=HEADERS, params={"size": 10, "postWorkflowClasses": "closed"}, timeout=30
).json().get("result", [])

matched = 0
missed = 0
for t in pajunwi_tasks:
    task_id = t.get("id")
    detail = requests.get(
        f"{BASE}/projects/{PAJUNWI_ID}/posts/{task_id}",
        headers=HEADERS, timeout=30
    ).json().get("result", {})
    body = detail.get("body", {}).get("content", "")
    m = AMOUNT_RE.search(body)
    amount = int(m.group(1).replace(",", "")) if m else None
    subject = t.get("subject", "")[:50]
    print(f"  {'✓' if m else '✗'} [{t['id']}] {subject!r} → amount={amount}")
    if m:
        matched += 1
    else:
        missed += 1
    if not m and body:
        # print first 200 chars of body to diagnose
        print(f"    body excerpt: {body[:200]!r}")

print(f"\nRegex match rate: {matched}/{matched+missed} tasks")

# 5. Check what fields a pajunwi task body contains (for copy)
if pajunwi_tasks:
    sample_id = pajunwi_tasks[0]["id"]
    sample = requests.get(
        f"{BASE}/projects/{PAJUNWI_ID}/posts/{sample_id}",
        headers=HEADERS, timeout=30
    ).json().get("result", {})
    print("\n\n=== Pajunwi task top-level keys (for copy field selection) ===")
    print(json.dumps(list(sample.keys()), indent=2, ensure_ascii=False))
    print("\nusers.from (requester):")
    print(json.dumps(sample.get("users", {}).get("from", {}), indent=2, ensure_ascii=False))
