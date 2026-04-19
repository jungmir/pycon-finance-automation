import json
import responses as resp_lib
import pytest
from src.notifier import Notifier

WEBHOOK = "https://hooks.slack.com/test"


@pytest.fixture
def notifier():
    return Notifier(WEBHOOK)


@resp_lib.activate
def test_task_copied_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.task_copied("pj-001", "2026 파이콘 장소 답사 활동비")
    assert len(resp_lib.calls) == 1
    body = resp_lib.calls[0].request.body.decode("utf-8")
    data = json.loads(body)
    text = data["text"]
    assert "pj-001" in text
    assert "복사 완료" in text


@resp_lib.activate
def test_task_rejected_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.task_rejected("pycon-999")
    body = resp_lib.calls[0].request.body.decode("utf-8")
    data = json.loads(body)
    assert "반려" in data["text"]


@resp_lib.activate
def test_handler_error_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.handler_error("step3_copy", "pj-001", "ConnectionError")
    body = resp_lib.calls[0].request.body.decode("utf-8")
    data = json.loads(body)
    text = data["text"]
    assert "step3_copy" in text
    assert "ConnectionError" in text


@resp_lib.activate
def test_heartbeat_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.heartbeat(3, 12, "2026-04-17T05:00:00")
    body = resp_lib.calls[0].request.body.decode("utf-8")
    data = json.loads(body)
    text = data["text"]
    assert "3" in text   # active tasks
    assert "12" in text  # transitions


@resp_lib.activate
def test_webhook_failure_does_not_raise(notifier):
    """A Slack failure should log but not propagate — automation must continue."""
    resp_lib.add(resp_lib.POST, WEBHOOK, body="error", status=500)
    notifier.task_copied("pj-001", "test")  # should not raise


@resp_lib.activate
def test_sheets_failure_sends_webhook(notifier):
    resp_lib.add(resp_lib.POST, WEBHOOK, body="ok", status=200)
    notifier.sheets_failure("pj-001", "Quota exceeded")
    body = resp_lib.calls[0].request.body.decode("utf-8")
    data = json.loads(body)
    assert "시트" in data["text"]
