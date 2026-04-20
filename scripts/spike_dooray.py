"""
scripts/spike_dooray.py — Dooray API exploration script.
Run once with real credentials to discover API shape.

Usage:
  DOORAY_API_TOKEN=xxx DOORAY_DOMAIN=pycon.dooray.com \
  PAJUNWI_PROJECT_ID=yyy python scripts/spike_dooray.py
"""
import os
import json
import sys
import requests

TOKEN = os.environ.get("DOORAY_API_TOKEN")
DOMAIN = os.environ.get("DOORAY_DOMAIN")
PAJUNWI_ID = os.environ.get("PAJUNWI_PROJECT_ID")

if not all([TOKEN, DOMAIN, PAJUNWI_ID]):
    print(__doc__)
    print("Missing environment variables:")
    if not TOKEN:
        print("  - DOORAY_API_TOKEN")
    if not DOMAIN:
        print("  - DOORAY_DOMAIN")
    if not PAJUNWI_ID:
        print("  - PAJUNWI_PROJECT_ID")
    sys.exit(1)

# Token may be "memberId:apiKey" format — try both full token and key-only part
TOKEN_KEY = TOKEN.split(":")[-1] if ":" in TOKEN else TOKEN

CANDIDATES = [
    (f"https://{DOMAIN}/project/v1",       f"dooray-api {TOKEN}"),
    ("https://api.dooray.com/project/v1",  f"dooray-api {TOKEN}"),
    (f"https://{DOMAIN}/project/v1",       f"dooray-api {TOKEN_KEY}"),
    ("https://api.dooray.com/project/v1",  f"dooray-api {TOKEN_KEY}"),
]

WORKING_BASE = None
WORKING_AUTH = None


def try_request(label, method, path, **kwargs):
    url = f"{WORKING_BASE}{path}"
    hdrs = {"Authorization": WORKING_AUTH, "Content-Type": "application/json"}
    print(f"\n=== {label} ===")
    print(f"URL: {url}")
    r = requests.request(method, url, headers=hdrs, **kwargs)
    print(f"Status: {r.status_code}")
    try:
        body = r.json()
        print(json.dumps(body, indent=2, ensure_ascii=False)[:3000])
    except Exception:
        print(r.text[:300])
    return r


# 0. Find working (base_url, auth) combo
print("=== Probing base URL + auth combinations ===")
r = None
for base, auth in CANDIDATES:
    hdrs = {"Authorization": auth, "Content-Type": "application/json"}
    probe = requests.get(f"{base}/projects/{PAJUNWI_ID}/posts",
                         headers=hdrs, params={"size": 1})
    is_json = "application/json" in probe.headers.get("Content-Type", "")
    print(f"  {base} | {auth[:30]}... → {probe.status_code} {'(JSON)' if is_json else '(HTML)'}")
    if probe.status_code == 200 and is_json:
        WORKING_BASE, WORKING_AUTH = base, auth
        r = probe
        print(f"  ✓ Found working combo!")
        break

if not WORKING_BASE:
    print("\n  ✗ No working combo found. Showing best response:")
    best = None
    for base, auth in CANDIDATES:
        hdrs = {"Authorization": auth, "Content-Type": "application/json"}
        probe = requests.get(f"{base}/projects/{PAJUNWI_ID}/posts",
                             headers=hdrs, params={"size": 1})
        is_json = "application/json" in probe.headers.get("Content-Type", "")
        if is_json:
            best = (base, auth, probe)
            break
    if best:
        WORKING_BASE, WORKING_AUTH, r = best
    else:
        WORKING_BASE, WORKING_AUTH = CANDIDATES[0][0], CANDIDATES[0][1]
    print(f"  Using: {WORKING_BASE}")

# 1. List tasks in pajunwi project
r = try_request("List pajunwi tasks", "GET",
                f"/projects/{PAJUNWI_ID}/posts", params={"size": 5})

# 2. Get project info + workflow states
try_request("Get project info", "GET", f"/projects/{PAJUNWI_ID}")

# 3. Get project workflows (status strings)
try_request("Get project workflows", "GET", f"/projects/{PAJUNWI_ID}/workflows")

# 4. Get a single task and its comments
if r.status_code == 200:
    result = r.json().get("result", [])
    if result:
        task_id = result[0].get("id")
        if task_id:
            try_request(f"Get single task {task_id}", "GET",
                        f"/projects/{PAJUNWI_ID}/posts/{task_id}")
            try_request(f"Get task comments {task_id}", "GET",
                        f"/projects/{PAJUNWI_ID}/posts/{task_id}/logs")

print("\n\n=== ANSWERS TO RECORD IN docs/spike-dooray-api.md ===")
print("1. Auth header: 'dooray-api {token}'")
print("2. Task ID field: 'id'")
print("3. Status field: 'workflowClass' (registered|working|closed) + 'workflow.id'/'workflow.name' for custom statuses")
print("4. Check 'workflow.name' values from the tasks/workflows above for custom status strings")
print("5. Body field: body.content + body.mimeType")
print("6. Comment ID field: check 'id' vs 'logId' in logs response above")
