import responses as resp_lib
import pytest
from src.clients.dooray import DoorayClient


BASE = "https://test.dooray.com/common/v1"


@pytest.fixture
def client():
    return DoorayClient("test.dooray.com", "token123")


@resp_lib.activate
def test_get_tasks_returns_result_list(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts",
        json={"result": [{"id": "t1", "subject": "Test task"}]},
        status=200,
    )
    tasks = client.get_tasks("proj1")
    assert tasks == [{"id": "t1", "subject": "Test task"}]


@resp_lib.activate
def test_get_tasks_passes_status_filter(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts",
        json={"result": []},
        status=200,
    )
    client.get_tasks("proj1", status="registered")
    assert "workflowClass" in resp_lib.calls[0].request.url


@resp_lib.activate
def test_get_task_returns_single(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts/t1",
        json={"result": {"id": "t1", "subject": "Buy coffee"}},
        status=200,
    )
    task = client.get_task("proj1", "t1")
    assert task["id"] == "t1"


@resp_lib.activate
def test_update_task_status(client):
    resp_lib.add(
        resp_lib.PUT,
        f"{BASE}/projects/proj1/posts/t1",
        json={"result": {}},
        status=200,
    )
    client.update_task_status("proj1", "t1", "working")
    payload = resp_lib.calls[0].request.body
    assert b"working" in payload or "working" in payload


@resp_lib.activate
def test_create_task(client):
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/proj1/posts",
        json={"result": {"id": "t2"}},
        status=200,
    )
    result = client.create_task("proj1", "New task", "body content")
    assert result["id"] == "t2"


@resp_lib.activate
def test_get_comments(client):
    resp_lib.add(
        resp_lib.GET,
        f"{BASE}/projects/proj1/posts/t1/logs",
        json={"result": [{"id": "c1", "body": {"content": "증빙 첨부"}}]},
        status=200,
    )
    comments = client.get_comments("proj1", "t1")
    assert len(comments) == 1
    assert comments[0]["id"] == "c1"


@resp_lib.activate
def test_create_comment(client):
    resp_lib.add(
        resp_lib.POST,
        f"{BASE}/projects/proj1/posts/t1/logs",
        json={"result": {"id": "c2"}},
        status=200,
    )
    result = client.create_comment("proj1", "t1", "영수증 첨부합니다")
    assert result["id"] == "c2"


@resp_lib.activate
def test_retries_on_server_error(client):
    """Client retries up to 3 times on 5xx before raising."""
    for _ in range(3):
        resp_lib.add(
            resp_lib.GET,
            f"{BASE}/projects/proj1/posts",
            json={"error": "server error"},
            status=500,
        )
    with pytest.raises(Exception):
        client.get_tasks("proj1")
    assert len(resp_lib.calls) == 3
