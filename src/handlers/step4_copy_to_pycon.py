from .base import BaseHandler
from ..clients.dooray import DoorayClient


class Step4CopyToPyconHandler(BaseHandler):
    """Copy pajunwi task to pycon project when pajunwi reaches 결제 대기 중."""

    name = "step4_copy_to_pycon"
    from_state = "PAYMENT_WAITING"
    to_state = "COPIED_TO_PYCON"

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

    def execute(self, task: dict) -> dict:
        pajunwi_task_id = task["pajunwi_task_id"]

        # Cross-project idempotency: pycon portal has no external reference query — rely on SQLite.
        if task.get("pycon_task_id"):
            return {"pycon_task_id": task["pycon_task_id"]}

        source = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        subject = source.get("subject", "")
        body_content = source.get("body", {}).get("content", "")

        new_task = self.dooray.create_task(
            self.pycon_project_id,
            subject=subject,
            body=body_content,
        )
        pycon_task_id = new_task.get("id") or new_task.get("postId")
        if not pycon_task_id:
            raise ValueError("create_task response missing both 'id' and 'postId' fields")

        self.notifier.task_copied(pajunwi_task_id, subject)
        return {"pycon_task_id": pycon_task_id}
