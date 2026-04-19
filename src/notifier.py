import logging
import requests

logger = logging.getLogger(__name__)


class Notifier:
    """Slack Incoming Webhook sender for automation status messages."""

    def __init__(self, webhook_url: str):
        self._url = webhook_url

    def _send(self, text: str) -> None:
        try:
            resp = requests.post(self._url, json={"text": text}, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(f"Slack notification failed: {exc}")

    def task_copied(self, pajunwi_task_id: str, subject: str) -> None:
        self._send(
            f"✅ [자동화] 업무 복사 완료\n"
            f"   파준위 #{pajunwi_task_id} → 파이콘 포털로 복사됨\n"
            f"   제목: {subject}"
        )

    def task_rejected(self, pycon_task_id: str) -> None:
        self._send(
            f"⚠️ [자동화] 파사모 반려 감지\n"
            f"   파이콘 포털 업무 #{pycon_task_id} 반려됨 — 수동 확인 필요"
        )

    def handler_error(self, handler_name: str, pajunwi_task_id: str, error: str) -> None:
        self._send(
            f"❌ [자동화] 핸들러 오류\n"
            f"   {handler_name} 실패 (업무 #{pajunwi_task_id}) — 다음 폴링에서 재시도 예정\n"
            f"   오류: {error}"
        )

    def heartbeat(self, active_tasks: int, transitions_today: int, last_poll: str) -> None:
        self._send(
            f"💚 [자동화] 일일 하트비트\n"
            f"   처리 중 업무: {active_tasks}건\n"
            f"   오늘 상태 전이: {transitions_today}건\n"
            f"   마지막 폴링: {last_poll}"
        )

    def sheets_failure(self, pajunwi_task_id: str, error: str) -> None:
        self._send(
            f"⚠️ [자동화] 구글 시트 갱신 실패\n"
            f"   업무 #{pajunwi_task_id} — 수동 시트 갱신 필요\n"
            f"   오류: {error}"
        )
