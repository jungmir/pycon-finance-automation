import os
import pytest
from src.config import Config


def _set_required(monkeypatch):
    monkeypatch.setenv("DOORAY_API_TOKEN", "tok")
    monkeypatch.setenv("PAJUNWI_PROJECT_ID", "111")
    monkeypatch.setenv("PYCON_PROJECT_ID", "222")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "eyJmb28iOiJiYXIifQ==")
    monkeypatch.setenv("SPREADSHEET_ID", "sheet1")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/x")


def test_from_env_all_required(monkeypatch):
    """Config.from_env() returns a Config when all vars are set."""
    _set_required(monkeypatch)

    cfg = Config.from_env()

    assert cfg.dooray_api_token == "tok"
    assert cfg.pajunwi_project_id == "111"
    assert cfg.pycon_project_id == "222"
    assert cfg.poll_interval_seconds == 300  # default
    assert cfg.database_path == "/data/state.db"  # default


def test_from_env_missing_required_raises(monkeypatch):
    """Config.from_env() raises EnvironmentError when vars are missing."""
    for key in ["DOORAY_API_TOKEN", "PAJUNWI_PROJECT_ID",
                "PYCON_PROJECT_ID", "GOOGLE_SERVICE_ACCOUNT_JSON",
                "SPREADSHEET_ID", "SLACK_WEBHOOK_URL"]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(EnvironmentError) as exc_info:
        Config.from_env()

    assert "DOORAY_API_TOKEN" in str(exc_info.value)


def test_from_env_custom_poll_interval(monkeypatch):
    """POLL_INTERVAL_SECONDS env var overrides the 300s default."""
    _set_required(monkeypatch)
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "60")

    cfg = Config.from_env()
    assert cfg.poll_interval_seconds == 60
