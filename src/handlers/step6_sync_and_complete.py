from .base import BaseHandler
from ..clients.dooray import (
    DoorayClient,
    DOORAY_WORKFLOW_NAME_COMPLETED,
    DOORAY_WORKFLOW_ID_COMPLETED,
)


class Step6SyncAndCompleteHandler(BaseHandler):
    """Every poll: sync pajunwi body to pycon. When pycon reaches 결제 완료, finalize."""

    name = "step6_sync_and_complete"
    from_state = "PAYMENT_IN_PROGRESS"
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
        pycon_task_id = task.get("pycon_task_id")
        if not pycon_task_id:
            raise ValueError(f"Task {pajunwi_task_id} missing pycon_task_id in PAYMENT_IN_PROGRESS state")

        source = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        body_content = source.get("body", {}).get("content", "")
        self.dooray.update_task_body(self.pycon_project_id, pycon_task_id, body_content)

        pycon = self.dooray.get_task(self.pycon_project_id, pycon_task_id)
        if pycon.get("workflow", {}).get("name") == DOORAY_WORKFLOW_NAME_COMPLETED:
            self.dooray.update_task_status(
                self.pajunwi_project_id, pajunwi_task_id, DOORAY_WORKFLOW_ID_COMPLETED
            )
            return True

        return None  # keep polling and syncing
