from .base import BaseHandler
from ..clients.dooray import DoorayClient


class Step3CopyHandler(BaseHandler):
    name = "step3_copy"
    from_state = "REVIEWING"
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

        # Cross-project copy: we cannot query pycon portal by pajunwi task ID.
        # Idempotency relies on pycon_task_id being persisted in SQLite after first successful copy.
        # SPIKE_REQUIRED: verify if pycon portal supports querying tasks by external reference.
        if task.get("pycon_task_id"):
            return {"pycon_task_id": task["pycon_task_id"]}

        # Fetch current task data from pajunwi portal
        source = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        subject = source.get("subject", "")
        body_content = source.get("body", {}).get("content", "")

        # SPIKE_REQUIRED: confirm which extra fields to include (agreed with 파사모 team)
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
