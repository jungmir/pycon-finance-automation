from .base import BaseHandler
from ..clients.dooray import DoorayClient


class Step8EvidenceHandler(BaseHandler):
    name = "step8_evidence"
    from_state = "PAYMENT_PENDING"
    to_state = "EVIDENCE_COPIED"

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
        last_comment_id = task.get("last_comment_id")

        comments = self.dooray.get_comments(self.pajunwi_project_id, pajunwi_task_id)
        new_comments = self._filter_new(comments, last_comment_id)

        if not new_comments:
            return None  # not ready — no new evidence comments

        for comment in new_comments:
            content = comment.get("body", {}).get("content", "")
            self.dooray.create_comment(self.pycon_project_id, pycon_task_id, content)

        newest_id = new_comments[-1]["id"]
        return {"last_comment_id": newest_id}

    def _filter_new(self, comments: list[dict], last_id: str | None) -> list[dict]:
        if not last_id:
            return comments
        found = False
        result = []
        for comment in comments:
            if found:
                result.append(comment)
            if comment["id"] == last_id:
                found = True
        return result
