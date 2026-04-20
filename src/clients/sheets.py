import base64
import json
import gspread


class SheetsClient:
    def __init__(self, service_account_json_b64: str, spreadsheet_id: str):
        self._service_account_json_b64 = service_account_json_b64
        self._spreadsheet_id = spreadsheet_id
        self._gc = None

    def _ensure_connected(self) -> None:
        if self._gc is None:
            sa_json = json.loads(base64.b64decode(self._service_account_json_b64).decode())
            self._gc = gspread.service_account_from_dict(sa_json)

    def append_expense_row(self, values: list) -> None:
        self._ensure_connected()
        sheet = self._gc.open_by_key(self._spreadsheet_id).worksheet("지출")
        sheet.append_row(values)
