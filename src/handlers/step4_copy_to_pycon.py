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
        accounting_group_id: str,
        executive_member_ids: list[str],
    ):
        super().__init__(store, notifier)
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id
        self.pycon_project_id = pycon_project_id
        self.accounting_group_id = accounting_group_id
        self.executive_member_ids = executive_member_ids

    def execute(self, task: dict) -> dict:
        pajunwi_task_id = task["pajunwi_task_id"]

        # Cross-project idempotency: pycon portal has no external reference query — rely on SQLite.
        if task.get("pycon_task_id"):
            return {"pycon_task_id": task["pycon_task_id"]}

        source = self.dooray.get_task(self.pajunwi_project_id, pajunwi_task_id)
        subject = source.get("subject", "")
        body_content = source.get("body", {}).get("content", "")

        src_tag_ids = [t["id"] for t in source.get("tags", [])]
        tag_ids = _map_tag_ids(
            src_tag_ids,
            self.dooray.get_tags(self.pajunwi_project_id),
            self.dooray.get_tags(self.pycon_project_id),
        )

        extra = {
            "users": _build_users(self.accounting_group_id, self.executive_member_ids),
        }
        if tag_ids:
            extra["tagIds"] = tag_ids

        new_task = self.dooray.create_task(
            self.pycon_project_id,
            subject=subject,
            body=body_content,
            **extra,
        )
        pycon_task_id = new_task.get("id") or new_task.get("postId")
        if not pycon_task_id:
            raise ValueError("create_task response missing both 'id' and 'postId' fields")

        self.notifier.task_copied(pajunwi_task_id, subject)
        return {"pycon_task_id": pycon_task_id}


def _build_users(accounting_group_id: str, executive_member_ids: list[str]) -> dict:
    return {
        "to": [{"type": "group", "group": {"projectMemberGroupId": accounting_group_id}}],
        "cc": [{"type": "member", "member": {"organizationMemberId": mid}} for mid in executive_member_ids],
    }


def _map_tag_ids(src_ids: list[str], src_tags: dict[str, str], dst_tags: dict[str, str]) -> list[str]:
    """Map source tag IDs to destination tag IDs by name."""
    dst_name_to_id = {name: tid for tid, name in dst_tags.items()}
    result = []
    for sid in src_ids:
        name = src_tags.get(sid)
        if name and name in dst_name_to_id:
            result.append(dst_name_to_id[name])
    return result
