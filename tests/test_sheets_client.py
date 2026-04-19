import base64
import json
import pytest
from unittest.mock import patch, MagicMock
from src.clients.sheets import SheetsClient


FAKE_SA = base64.b64encode(json.dumps({
    "type": "service_account",
    "project_id": "test",
    "private_key_id": "key1",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "test@test.iam.gserviceaccount.com",
    "client_id": "123",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}).encode()).decode()


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_append_row_calls_gspread(mock_sa):
    mock_worksheet = MagicMock()
    mock_sa.return_value.open_by_key.return_value.sheet1 = mock_worksheet

    client = SheetsClient(FAKE_SA, "sheet-id-123")
    client.append_row(["2026-04-17", "출장비", "파준위", 50000])

    mock_sa.assert_called_once()
    mock_sa.return_value.open_by_key.assert_called_once_with("sheet-id-123")
    mock_worksheet.append_row.assert_called_once_with(["2026-04-17", "출장비", "파준위", 50000])


@patch("src.clients.sheets.gspread.service_account_from_dict")
def test_sheets_client_decodes_base64_json(mock_sa):
    mock_sa.return_value.open_by_key.return_value.sheet1 = MagicMock()
    SheetsClient(FAKE_SA, "sheet-id")
    call_kwargs = mock_sa.call_args[0][0]
    assert call_kwargs["type"] == "service_account"
    assert call_kwargs["client_email"] == "test@test.iam.gserviceaccount.com"
