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
