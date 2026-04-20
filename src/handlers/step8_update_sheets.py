from datetime import datetime, UTC
from .base import BaseHandler
from ..clients.dooray import DoorayClient
from ..clients.sheets import SheetsClient


class Step8UpdateSheetsHandler(BaseHandler):
    name = "step8_update_sheets"
    from_state = "COMPLETED"
    to_state = "SHEET_UPDATED"

    def __init__(self, store, notifier, sheets: SheetsClient, dooray: DoorayClient, pajunwi_project_id: str):
        super().__init__(store, notifier)
        self.sheets = sheets
        self.dooray = dooray
        self.pajunwi_project_id = pajunwi_project_id

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        task_url = self.dooray.task_web_url(self.pajunwi_project_id, pajunwi_task_id)

        # 지출 시트 컬럼 순서: 대분류, 소분류, 내용, 날짜, 담당자, 금액, 비고
        row = [
            task.get("tag", ""),
            "",
            task.get("subject", ""),
            today,
            task.get("creator", ""),
            task.get("amount", 0),
            task_url,
        ]
        self.sheets.append_expense_row(row)
        return True
