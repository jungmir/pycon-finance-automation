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
