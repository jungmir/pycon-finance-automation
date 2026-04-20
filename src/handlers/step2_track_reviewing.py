import re
from .base import BaseHandler
from ..clients.dooray import (
    DoorayClient,
    DOORAY_WORKFLOW_NAME_REVIEWING,
    DOORAY_WORKFLOW_NAME_REJECTED,
)

# 결제 요청 template:   "## 결제 금액\n\n78,800원"
# 활동비 증빙 template: "* 예상 지출액 : 10,000원" (before) / "* 실제 지출: 5,200원" (after)
AMOUNT_RE = re.compile(r"(?:결제\s*금액|실제\s*지출|예상\s*지출액|금액)[:\s]*([0-9,]+)\s*원")


class Step2TrackReviewingHandler(BaseHandler):
    """Watch pajunwi for 검토 중. Accounting team changes state manually; we just track it."""

    name = "step2_track_reviewing"
    from_state = "NEW"
    to_state = "REVIEWING"

    def __init__(self, store, notifier, dooray: DoorayClient, pajunwi_project_id: str):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.project_id = pajunwi_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        current = self.dooray.get_task(self.project_id, pajunwi_task_id)
        workflow_name = current.get("workflow", {}).get("name")

        if workflow_name == DOORAY_WORKFLOW_NAME_REJECTED:
            self.store.upsert_task(pajunwi_task_id, "REJECTED")
            self.store.log_transition(pajunwi_task_id, "NEW", "REJECTED", self.name, True)
            self.notifier.task_rejected(pajunwi_task_id)
            return None

        if workflow_name != DOORAY_WORKFLOW_NAME_REVIEWING:
            return None  # still 검토 전, keep waiting

        body_content = current.get("body", {}).get("content", "")
        amount = self._parse_amount(body_content)

        subject = current.get("subject", "")
        creator = current.get("users", {}).get("from", {}).get("member", {}).get("name", "")

        tag_ids = [t["id"] for t in current.get("tags", [])]
        tag_map = self.dooray.get_tags(self.project_id) if tag_ids else {}
        tag = tag_map.get(tag_ids[0], "") if tag_ids else ""

        return {"amount": amount, "subject": subject, "creator": creator, "tag": tag}

    def _parse_amount(self, body: str) -> int:
        match = AMOUNT_RE.search(body)
        if match:
            return int(match.group(1).replace(",", ""))
        return 0
