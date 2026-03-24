import asyncio
import json
import os
from types import SimpleNamespace

from fastapi import BackgroundTasks, Response
from fastapi.responses import JSONResponse, StreamingResponse

os.environ.setdefault(
    "NOTION_ACCOUNTS",
    '[{"token_v2":"test-token","space_id":"test-space","user_id":"test-user"}]',
)
os.environ.setdefault("APP_MODE", "standard")

import app.api.chat as chat_api  # noqa: E402
import app.config as app_config  # noqa: E402
import app.conversation as conversation_module  # noqa: E402


class FakeClient:
    def __init__(self, stream_items):
        self._stream_items = list(stream_items)
        self.user_id = "test-user"
        self.space_id = "test-space"
        self.current_thread_id = "thread-123"

    def stream_response(self, transcript, thread_id=None):
        self.last_transcript = transcript
        self.last_thread_id = thread_id
        for item in self._stream_items:
            yield item


class FakePool:
    def __init__(self, client):
        self.client = client
        self.clients = [client]
        self.failed_clients = []

    def get_client(self):
        return self.client

    def mark_failed(self, client):
        self.failed_clients.append(client)


class FakeManager:
    def __init__(self):
        self.thread_id = None
        self.persisted_rounds = []

    def new_conversation(self):
        return "conv-1"

    def conversation_exists(self, conversation_id):
        return conversation_id == "conv-1"

    def get_transcript_payload(self, **kwargs):
        return {
            "transcript": [{"role": "user", "content": kwargs["new_prompt"]}],
            "memory_degraded": False,
        }

    def get_conversation_thread_id(self, conversation_id):
        return None

    def set_conversation_thread_id(self, conversation_id, thread_id):
        self.thread_id = thread_id

    def persist_round(self, conversation_id, user_prompt, assistant_reply, assistant_thinking=""):
        self.persisted_rounds.append(
            {
                "conversation_id": conversation_id,
                "user_prompt": user_prompt,
                "assistant_reply": assistant_reply,
                "assistant_thinking": assistant_thinking,
            }
        )
        return 0


def _make_request(headers=None, **state):
    return SimpleNamespace(
        headers=headers or {},
        app=SimpleNamespace(state=SimpleNamespace(**state)),
    )


def _parse_sse_events(stream_text: str):
    events = []
    for block in stream_text.split("\n\n"):
        if not block.strip():
            continue
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                events.append(payload)
            else:
                events.append(json.loads(payload))
    return events


def _decode_json_response(response: JSONResponse):
    return json.loads(response.body.decode("utf-8"))


async def _collect_streaming_response(response: StreamingResponse) -> str:
    parts = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            parts.append(chunk.decode("utf-8"))
        else:
            parts.append(chunk)
    return "".join(parts)


def test_standard_stream_non_web_uses_reasoning_content_and_standard_chunks():
    stream_text = "".join(
        chat_api._create_standard_stream_generator(
            "chatcmpl-test",
            "test-model",
            {
                "type": "search",
                "data": {
                    "queries": ["reasoning"],
                    "sources": [{"title": "Doc", "url": "https://example.com"}],
                },
            },
            iter(
                [
                    {"type": "thinking", "text": "思考片段"},
                    {"type": "content", "text": "正式答案"},
                ]
            ),
            client_type="chatbox",
        )
    )

    events = _parse_sse_events(stream_text)
    assert events[-1] == "[DONE]"

    payloads = [event for event in events if isinstance(event, dict)]
    reasoning_chunks = [
        payload["choices"][0]["delta"].get("reasoning_content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("reasoning_content")
    ]
    content_chunks = [
        payload["choices"][0]["delta"].get("content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("content")
    ]

    assert payloads[0]["choices"][0]["delta"]["role"] == "assistant"
    assert any(chunk == "思考片段" for chunk in reasoning_chunks)
    assert any(chunk.startswith("> 🔍 **已搜索:** reasoning") for chunk in reasoning_chunks)
    assert any("> 🌐 **来源:**" in chunk for chunk in reasoning_chunks)
    assert "".join(content_chunks) == "正式答案"
    assert payloads[-1]["choices"][0]["finish_reason"] == "stop"
    assert all("type" not in payload for payload in payloads)


def test_standard_stream_web_keeps_custom_ui_events():
    stream_text = "".join(
        chat_api._create_standard_stream_generator(
            "chatcmpl-test",
            "test-model",
            {"type": "thinking", "text": "思考片段"},
            iter(
                [
                    {
                        "type": "search",
                        "data": {
                            "queries": ["reasoning"],
                            "sources": [{"title": "Doc", "url": "https://example.com"}],
                        },
                    },
                    {"type": "content", "text": "正式答案"},
                ]
            ),
            client_type="web",
        )
    )

    events = _parse_sse_events(stream_text)
    payloads = [event for event in events if isinstance(event, dict)]

    assert payloads[0]["type"] == "thinking_chunk"
    assert payloads[0]["text"] == "思考片段"
    assert payloads[1]["choices"][0]["delta"]["content"] == "正式答案"
    assert payloads[2]["type"] == "search_metadata"
    assert payloads[-1]["choices"][0]["finish_reason"] == "stop"


def test_standard_non_stream_response_hides_extensions_for_third_party(monkeypatch):
    monkeypatch.setattr(chat_api, "is_supported_model", lambda _: True)
    monkeypatch.setattr(
        conversation_module,
        "build_standard_transcript",
        lambda messages, model, account: messages,
    )

    client = FakeClient(
        [
            {"type": "thinking", "text": "思考片段"},
            {
                "type": "search",
                "data": {
                    "queries": ["reasoning"],
                    "sources": [{"title": "Doc", "url": "https://example.com"}],
                },
            },
            {"type": "content", "text": "正式答案"},
        ]
    )
    request = _make_request(account_pool=FakePool(client))
    req_body = chat_api.ChatCompletionRequest(
        model="test-model",
        messages=[chat_api.ChatMessage(role="user", content="你好")],
        stream=False,
    )

    result = asyncio.run(chat_api._handle_standard_request(request, req_body, Response()))

    assert isinstance(result, JSONResponse)
    payload = _decode_json_response(result)
    message = payload["choices"][0]["message"]
    assert message["content"] == "正式答案"
    assert "thinking" not in message
    assert "search_metadata" not in payload


def test_standard_non_stream_response_keeps_extensions_for_web(monkeypatch):
    monkeypatch.setattr(chat_api, "is_supported_model", lambda _: True)
    monkeypatch.setattr(
        conversation_module,
        "build_standard_transcript",
        lambda messages, model, account: messages,
    )

    client = FakeClient(
        [
            {"type": "thinking", "text": "思考片段"},
            {
                "type": "search",
                "data": {
                    "queries": ["reasoning"],
                    "sources": [{"title": "Doc", "url": "https://example.com"}],
                },
            },
            {"type": "content", "text": "正式答案"},
        ]
    )
    request = _make_request(headers={"X-Client-Type": "Web"}, account_pool=FakePool(client))
    req_body = chat_api.ChatCompletionRequest(
        model="test-model",
        messages=[chat_api.ChatMessage(role="user", content="你好")],
        stream=False,
    )

    result = asyncio.run(chat_api._handle_standard_request(request, req_body, Response()))

    assert isinstance(result, JSONResponse)
    payload = _decode_json_response(result)
    message = payload["choices"][0]["message"]
    assert message["content"] == "正式答案"
    assert message["thinking"] == "思考片段"
    assert payload["search_metadata"]["queries"] == ["reasoning"]


def test_heavy_stream_non_web_avoids_custom_events_and_keeps_reasoning(monkeypatch):
    monkeypatch.setattr(chat_api, "is_supported_model", lambda _: True)
    monkeypatch.setattr(app_config, "APP_MODE", "heavy", raising=False)

    client = FakeClient(
        [
            {
                "type": "search",
                "data": {
                    "queries": ["reasoning"],
                    "sources": [{"title": "Doc", "url": "https://example.com"}],
                },
            },
            {"type": "thinking", "text": "思考片段"},
            {"type": "content", "text": "正式答案"},
        ]
    )
    request = _make_request(
        account_pool=FakePool(client),
        conversation_manager=FakeManager(),
    )
    req_body = chat_api.ChatCompletionRequest(
        model="test-model",
        messages=[chat_api.ChatMessage(role="user", content="你好")],
        stream=True,
    )

    result = asyncio.run(
        chat_api.create_chat_completion(
            request,
            req_body,
            BackgroundTasks(),
            Response(),
        )
    )

    assert isinstance(result, StreamingResponse)
    stream_text = asyncio.run(_collect_streaming_response(result))
    events = _parse_sse_events(stream_text)
    payloads = [event for event in events if isinstance(event, dict)]
    reasoning_chunks = [
        payload["choices"][0]["delta"].get("reasoning_content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("reasoning_content")
    ]

    assert events[-1] == "[DONE]"
    assert any(chunk == "思考片段" for chunk in reasoning_chunks)
    assert any(chunk.startswith("> 🔍 **已搜索:** reasoning") for chunk in reasoning_chunks)
    assert any("> 🌐 **来源:**" in chunk for chunk in reasoning_chunks)
    assert not any(payload.get("type") in {"thinking_chunk", "search_metadata", "thinking_replace", "content_replace"} for payload in payloads)
    assert any("正式答案" in payload["choices"][0]["delta"].get("content", "") for payload in payloads)
    assert not any("> 🔍" in payload["choices"][0]["delta"].get("content", "") for payload in payloads)


def test_standard_stream_non_web_splits_leaked_reasoning_prefix():
    stream_text = "".join(
        chat_api._create_standard_stream_generator(
            "chatcmpl-test",
            "test-model",
            {"type": "thinking", "text": "The"},
            iter(
                [
                    {
                        "type": "content",
                        "text": (
                            "user is asking me to confirm the situation.\n\n"
                            "I should respond clearly and keep it concise."
                            "是的，完全同意你的观点。"
                        ),
                    }
                ]
            ),
            client_type="chatbox",
        )
    )

    events = _parse_sse_events(stream_text)
    payloads = [event for event in events if isinstance(event, dict)]
    reasoning_chunks = [
        payload["choices"][0]["delta"].get("reasoning_content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("reasoning_content")
    ]
    content_chunks = [
        payload["choices"][0]["delta"].get("content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("content")
    ]

    assert reasoning_chunks[0] == "The"
    assert any("user is asking me to confirm the situation." in chunk for chunk in reasoning_chunks)
    assert all("user is asking me to confirm the situation." not in chunk for chunk in content_chunks)
    assert "".join(content_chunks) == "是的，完全同意你的观点。"


def test_heavy_stream_non_web_splits_leaked_reasoning_prefix(monkeypatch):
    monkeypatch.setattr(chat_api, "is_supported_model", lambda _: True)
    monkeypatch.setattr(app_config, "APP_MODE", "heavy", raising=False)

    client = FakeClient(
        [
            {"type": "thinking", "text": "The"},
            {
                "type": "content",
                "text": (
                    "user is asking me to confirm the situation.\n\n"
                    "I should respond clearly and keep it concise."
                    "是的，完全同意你的观点。"
                ),
            },
        ]
    )
    request = _make_request(
        account_pool=FakePool(client),
        conversation_manager=FakeManager(),
    )
    req_body = chat_api.ChatCompletionRequest(
        model="test-model",
        messages=[chat_api.ChatMessage(role="user", content="你好")],
        stream=True,
    )

    result = asyncio.run(
        chat_api.create_chat_completion(
            request,
            req_body,
            BackgroundTasks(),
            Response(),
        )
    )

    assert isinstance(result, StreamingResponse)
    stream_text = asyncio.run(_collect_streaming_response(result))
    events = _parse_sse_events(stream_text)
    payloads = [event for event in events if isinstance(event, dict)]
    reasoning_chunks = [
        payload["choices"][0]["delta"].get("reasoning_content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("reasoning_content")
    ]
    content_chunks = [
        payload["choices"][0]["delta"].get("content", "")
        for payload in payloads
        if payload["choices"][0]["delta"].get("content")
    ]

    assert reasoning_chunks[0] == "The"
    assert any("user is asking me to confirm the situation." in chunk for chunk in reasoning_chunks)
    assert all("user is asking me to confirm the situation." not in chunk for chunk in content_chunks)
    assert "".join(content_chunks) == "是的，完全同意你的观点。"
