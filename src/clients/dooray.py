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
