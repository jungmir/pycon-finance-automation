from datetime import datetime, UTC
from .base import BaseHandler
from ..clients.sheets import SheetsClient


class Step8UpdateSheetsHandler(BaseHandler):
    name = "step8_update_sheets"
    from_state = "COMPLETED"
    to_state = "SHEET_UPDATED"

    def __init__(self, store, notifier, sheets: SheetsClient):
        super().__init__(store, notifier)
        self.sheets = sheets

    def execute(self, task: dict):
        pajunwi_task_id = task["pajunwi_task_id"]
        amount = task.get("amount", 0)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # SPIKE_REQUIRED: confirm column order with 파사모 team
        row = [today, pajunwi_task_id, amount]
        self.sheets.append_row(row)
        return True
