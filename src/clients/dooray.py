import time
import requests
import logging

logger = logging.getLogger(__name__)

# workflowClass: 3 fixed values system-wide — registered / working / closed
# Multiple named workflows share the same class; use workflow.name for fine-grained detection.

# workflowClass values (for broad filtering)
DOORAY_STATUS_NEW = "registered"
DOORAY_STATUS_WORKING = "working"
DOORAY_STATUS_CLOSED = "closed"

# workflow.name values — shared across pajunwi and pycon projects
DOORAY_WORKFLOW_NAME_NEW = "검토 전"
DOORAY_WORKFLOW_NAME_REVIEWING = "검토 중"
DOORAY_WORKFLOW_NAME_PAYMENT_WAITING = "결제 대기 중"
DOORAY_WORKFLOW_NAME_PAYMENT_IN_PROGRESS = "결제 중"
DOORAY_WORKFLOW_NAME_COMPLETED = "결제 완료"
DOORAY_WORKFLOW_NAME_REJECTED = "반려"
DOORAY_WORKFLOW_NAME_APPROVED = "요청 승인"

# Pajunwi workflow IDs — only needed for the one write we make (결제 완료 final sync)
DOORAY_WORKFLOW_ID_COMPLETED = "4266443407649875626"

TASK_ID_FIELD = "id"
COMMENT_ID_FIELD = "id"

_BASE_URL = "https://api.dooray.com/project/v1"


class DoorayClient:
    """REST client for Dooray task management API with automatic retry."""

    def __init__(self, token: str):
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"dooray-api {token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{_BASE_URL}{path}"
        last_exc = None
        for attempt in range(3):
            try:
                resp = self._session.request(method, url, timeout=30, **kwargs)
                resp.raise_for_status()
                try:
                    return resp.json()
                except ValueError as e:
                    raise requests.RequestException(f"Failed to parse JSON: {e}") from e
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(f"Dooray request attempt {attempt+1}/3 failed: {exc}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise last_exc

    def get_tasks(self, project_id: str, status: str = None) -> list[dict]:
        params = {"size": 100, "page": 0}
        if status:
            params["postWorkflowClasses"] = status
        data = self._request("GET", f"/projects/{project_id}/posts", params=params)
        return data.get("result", [])

    def get_task(self, project_id: str, task_id: str) -> dict:
        data = self._request("GET", f"/projects/{project_id}/posts/{task_id}")
        return data.get("result", {})

    def update_task_status(self, project_id: str, task_id: str, workflow_id: str) -> dict:
        payload = {"workflowId": workflow_id}
        data = self._request("POST", f"/projects/{project_id}/posts/{task_id}/set-workflow", json=payload)
        return data.get("result") or {}

    def update_task_body(self, project_id: str, task_id: str, body_content: str) -> dict:
        payload = {"body": {"mimeType": "text/x-markdown", "content": body_content}}
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
