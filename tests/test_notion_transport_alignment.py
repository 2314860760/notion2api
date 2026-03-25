import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi import Response

import app.api.chat as chat_api
from app.logger import setup_logger
from app.notion_client import NotionOpusAPI, NotionUpstreamError


class DummyResponse:
    def __init__(self, status_code=200, *, headers=None, text=""):
        self.status_code = status_code
        self.headers = headers or {"x-notion-request-id": "req-test"}
        self.text = text
        self.closed = False

    def close(self):
        self.closed = True


class DummyScraper:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.response


class ErrorClient:
    def __init__(self, exc):
        self.exc = exc
        self.user_id = "test-user"
        self.space_id = "test-space"

    def stream_response(self, transcript, thread_id=None):
        raise self.exc


class TrackingPool:
    def __init__(self, client):
        self.client = client
        self.clients = [client]
        self.mark_failed_calls = []

    def get_client(self):
        return self.client

    def mark_failed(self, client, *args, **kwargs):
        self.mark_failed_calls.append(
            {
                "client": client,
                "args": args,
                "kwargs": kwargs,
            }
        )


def _make_request(**state):
    return SimpleNamespace(
        headers={},
        app=SimpleNamespace(state=SimpleNamespace(**state)),
    )


def _make_client():
    return NotionOpusAPI(
        {
            "token_v2": "test-token",
            "space_id": "test-space",
            "user_id": "test-user",
            "user_email": "tester@example.com",
        }
    )


def _make_transcript(thread_type: str, model: str = "claude-opus4.6"):
    return [
        {
            "type": "config",
            "value": {
                "model": model,
                "type": thread_type,
            },
        },
        {
            "type": "context",
            "value": [["hello"]],
        },
        {
            "type": "user",
            "value": [["hello"]],
        },
    ]


def test_setup_logger_reads_log_level_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    test_logger = setup_logger("test_logger_level")
    assert test_logger.level == logging.DEBUG


def test_workflow_new_thread_request_matches_browser_truth(monkeypatch):
    response = DummyResponse()
    scraper = DummyScraper(response)
    monkeypatch.setattr("app.notion_client.cloudscraper.create_scraper", lambda: scraper)
    monkeypatch.setattr("app.notion_client.parse_stream", lambda resp: iter([{"type": "content", "text": "ok"}]))

    client = _make_client()
    chunks = list(client.stream_response(_make_transcript("workflow")))

    assert chunks == [{"type": "content", "text": "ok"}]
    request = scraper.calls[0]["kwargs"]
    payload = request["json"]
    headers = request["headers"]
    cookies = request["cookies"]

    assert payload["threadType"] == "workflow"
    assert payload["createThread"] is True
    assert payload["isPartialTranscript"] is False
    assert payload["generateTitle"] is True
    assert payload["setUnreadState"] is False
    assert "threadParentPointer" in payload
    assert headers["notion-client-version"] == "23.13.20260324.1803"
    assert headers["referer"] == "https://www.notion.so/ai"
    assert sorted(cookies.keys()) == ["notion_user_id", "token_v2"]
    assert response.closed is True


def test_workflow_reused_thread_request_matches_browser_truth(monkeypatch):
    response = DummyResponse()
    scraper = DummyScraper(response)
    monkeypatch.setattr("app.notion_client.cloudscraper.create_scraper", lambda: scraper)
    monkeypatch.setattr("app.notion_client.parse_stream", lambda resp: iter([{"type": "content", "text": "ok"}]))

    client = _make_client()
    list(client.stream_response(_make_transcript("workflow"), thread_id="thread-existing"))

    payload = scraper.calls[0]["kwargs"]["json"]
    headers = scraper.calls[0]["kwargs"]["headers"]

    assert payload["threadType"] == "workflow"
    assert payload["createThread"] is False
    assert payload["isPartialTranscript"] is True
    assert payload["generateTitle"] is False
    assert payload["setUnreadState"] is False
    assert "threadParentPointer" not in payload
    assert headers["referer"] == "https://www.notion.so/chat"


def test_markdown_chat_new_thread_uses_official_create_thread_semantics(monkeypatch):
    response = DummyResponse()
    scraper = DummyScraper(response)
    monkeypatch.setattr("app.notion_client.cloudscraper.create_scraper", lambda: scraper)
    monkeypatch.setattr("app.notion_client.parse_stream", lambda resp: iter([{"type": "content", "text": "ok"}]))
    monkeypatch.setattr(
        NotionOpusAPI,
        "_create_thread",
        lambda self, thread_id, thread_type: (_ for _ in ()).throw(AssertionError("should not precreate")),
    )

    client = _make_client()
    list(client.stream_response(_make_transcript("markdown-chat", model="gemini-3.1pro")))

    payload = scraper.calls[0]["kwargs"]["json"]
    assert payload["threadType"] == "markdown-chat"
    assert payload["createThread"] is True
    assert payload["isPartialTranscript"] is False
    assert payload["generateTitle"] is True
    assert payload["setUnreadState"] is False
    assert "threadParentPointer" in payload


def test_standard_request_does_not_cool_account_after_generic_upstream_502(monkeypatch):
    monkeypatch.setattr(chat_api, "is_supported_model", lambda _: True)

    pool = TrackingPool(
        ErrorClient(
            NotionUpstreamError(
                "boom",
                status_code=502,
                retriable=True,
                should_cooldown=False,
                error_kind="upstream_server_error",
            )
        )
    )
    request = _make_request(account_pool=pool)
    req_body = chat_api.ChatCompletionRequest(
        model="claude-opus4.6",
        messages=[chat_api.ChatMessage(role="user", content="你好")],
        stream=False,
    )

    with pytest.raises(chat_api.HTTPException) as exc_info:
        asyncio.run(chat_api._handle_standard_request(request, req_body, Response()))

    assert exc_info.value.status_code == 503
    assert pool.mark_failed_calls == []


def test_standard_request_cools_account_only_for_real_upstream_429(monkeypatch):
    monkeypatch.setattr(chat_api, "is_supported_model", lambda _: True)

    pool = TrackingPool(
        ErrorClient(
            NotionUpstreamError(
                "rate limited",
                status_code=429,
                retriable=False,
                should_cooldown=True,
                request_id="req-429",
                error_kind="upstream_rate_limited",
            )
        )
    )
    request = _make_request(account_pool=pool)
    req_body = chat_api.ChatCompletionRequest(
        model="claude-opus4.6",
        messages=[chat_api.ChatMessage(role="user", content="你好")],
        stream=False,
    )

    with pytest.raises(chat_api.HTTPException) as exc_info:
        asyncio.run(chat_api._handle_standard_request(request, req_body, Response()))

    assert exc_info.value.status_code == 429
    assert len(pool.mark_failed_calls) == 1
    assert pool.mark_failed_calls[0]["kwargs"]["reason"] == "upstream_rate_limited"
    assert pool.mark_failed_calls[0]["kwargs"]["upstream_status_code"] == 429
    assert pool.mark_failed_calls[0]["kwargs"]["upstream_request_id"] == "req-429"
