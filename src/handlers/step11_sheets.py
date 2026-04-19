from datetime import datetime, UTC
from .base import BaseHandler
from ..clients.sheets import SheetsClient


class Step11SheetsHandler(BaseHandler):
    name = "step11_sheets"
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
        # Expected columns: [날짜, 항목, 신청팀, 금액, ...]
        row = [today, pajunwi_task_id, amount]
        # NOTE: not idempotent — a retry will append a duplicate row.
        # Deferred pending 파사모 team confirmation of column order and de-dup strategy.
        self.sheets.append_row(row)
        return True
