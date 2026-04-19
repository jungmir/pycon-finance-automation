from dataclasses import dataclass
import os


@dataclass
class Config:
    dooray_api_token: str
    dooray_domain: str
    pajunwi_project_id: str
    pycon_project_id: str
    google_service_account_json: str  # base64-encoded service account JSON
    spreadsheet_id: str
    slack_webhook_url: str
    poll_interval_seconds: int
    database_path: str

    @classmethod
    def from_env(cls) -> "Config":
        required = [
            "DOORAY_API_TOKEN",
            "DOORAY_DOMAIN",
            "PAJUNWI_PROJECT_ID",
            "PYCON_PROJECT_ID",
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "SPREADSHEET_ID",
            "SLACK_WEBHOOK_URL",
        ]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(
            dooray_api_token=os.environ["DOORAY_API_TOKEN"],
            dooray_domain=os.environ["DOORAY_DOMAIN"],
            pajunwi_project_id=os.environ["PAJUNWI_PROJECT_ID"],
            pycon_project_id=os.environ["PYCON_PROJECT_ID"],
            google_service_account_json=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            spreadsheet_id=os.environ["SPREADSHEET_ID"],
            slack_webhook_url=os.environ["SLACK_WEBHOOK_URL"],
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
            database_path=os.environ.get("DATABASE_PATH", "/data/state.db"),
        )
