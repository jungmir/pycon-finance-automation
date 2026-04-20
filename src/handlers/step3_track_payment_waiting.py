from .base import BaseHandler
from ..clients.dooray import (
    DoorayClient,
    DOORAY_WORKFLOW_NAME_PAYMENT_WAITING,
    DOORAY_WORKFLOW_NAME_REJECTED,
)


class Step3TrackPaymentWaitingHandler(BaseHandler):
    """Watch pajunwi for 결제 대기 중. Accounting team changes state after approval."""

    name = "step3_track_payment_waiting"
    from_state = "REVIEWING"
    to_state = "PAYMENT_WAITING"

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
            self.store.log_transition(pajunwi_task_id, "REVIEWING", "REJECTED", self.name, True)
            self.notifier.task_rejected(pajunwi_task_id)
            return None

        if workflow_name != DOORAY_WORKFLOW_NAME_PAYMENT_WAITING:
            return None  # still in 검토 중, keep waiting

        return True
