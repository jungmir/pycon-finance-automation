import base64
import json
import gspread


class SheetsClient:
    def __init__(self, service_account_json_b64: str, spreadsheet_id: str):
        sa_json = json.loads(base64.b64decode(service_account_json_b64).decode())
        self._gc = gspread.service_account_from_dict(sa_json)
        self._spreadsheet_id = spreadsheet_id

    def append_row(self, values: list) -> None:
        # SPIKE_REQUIRED: confirm spreadsheet column order with 파사모 team.
        # Expected columns: [날짜, 항목, 신청팀, 금액, ...]
        sheet = self._gc.open_by_key(self._spreadsheet_id).sheet1
        sheet.append_row(values)
