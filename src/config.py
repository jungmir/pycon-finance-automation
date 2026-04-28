from dataclasses import dataclass
import os


@dataclass
class Config:
    dooray_api_token: str
    pajunwi_project_id: str
    pycon_project_id: str
    google_service_account_json: str  # base64-encoded service account JSON
    spreadsheet_id: str
    slack_webhook_url: str
    poll_interval_seconds: int
    database_path: str
    pycon_accounting_group_id: str           # 파이콘 프로젝트 담당자 그룹 (파사모-회계팀)
    pycon_executive_member_ids: list[str]    # 파이콘 프로젝트 참조 (파사모 임원진)

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables.

        Required: DOORAY_API_TOKEN, PAJUNWI_PROJECT_ID, PYCON_PROJECT_ID,
                  GOOGLE_SERVICE_ACCOUNT_JSON (base64), SPREADSHEET_ID, SLACK_WEBHOOK_URL
        Optional: POLL_INTERVAL_SECONDS (default 300), DATABASE_PATH (default /data/state.db)

        Raises EnvironmentError listing all missing required variables.
        """
        required = [
            "DOORAY_API_TOKEN",
            "PAJUNWI_PROJECT_ID",
            "PYCON_PROJECT_ID",
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "SPREADSHEET_ID",
            "SLACK_WEBHOOK_URL",
            "PYCON_ACCOUNTING_GROUP_ID",
            "PYCON_EXECUTIVE_MEMBER_IDS",
        ]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        def _parse_ids(val: str) -> list[str]:
            return [v.strip() for v in val.split(",") if v.strip()]

        return cls(
            dooray_api_token=os.environ["DOORAY_API_TOKEN"],
            pajunwi_project_id=os.environ["PAJUNWI_PROJECT_ID"],
            pycon_project_id=os.environ["PYCON_PROJECT_ID"],
            google_service_account_json=os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"],
            spreadsheet_id=os.environ["SPREADSHEET_ID"],
            slack_webhook_url=os.environ["SLACK_WEBHOOK_URL"],
            poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "300")),
            database_path=os.environ.get("DATABASE_PATH", "/data/state.db"),
            pycon_accounting_group_id=os.environ["PYCON_ACCOUNTING_GROUP_ID"],
            pycon_executive_member_ids=_parse_ids(os.environ["PYCON_EXECUTIVE_MEMBER_IDS"]),
        )
