from .base import BaseHandler
from ..clients.dooray import DoorayClient, DOORAY_STATUS_COMPLETED


class Step10SyncHandler(BaseHandler):
    name = "step10_sync"
    from_state = "EVIDENCE_COPIED"
    to_state = "COMPLETED"

    def __init__(
        self,
        store,
        notifier,
        dooray: DoorayClient,
        pajunwi_project_id: str,
        pycon_project_id: str,
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        pycon_task_id = task["pycon_task_id"]

        pycon_task = self.dooray.get_task(self.pycon_project_id, pycon_task_id)
        if pycon_task.get("workflowClass") != DOORAY_STATUS_COMPLETED:
            return None  # not done yet

        # Check-before-act on pajunwi side
        pajunwi_task = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        if pajunwi_task.get("workflowClass") != DOORAY_STATUS_COMPLETED:
            self.dooray.update_task_status(
                self.pajunwi_project_id, pajunwi_task_id, DOORAY_STATUS_COMPLETED
            )

        return True
