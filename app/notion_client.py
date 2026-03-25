import hashlib
import time
import uuid
from typing import Any, Generator, Optional

import cloudscraper
import requests
import urllib3

from app.logger import logger
from app.model_registry import get_notion_model
from app.stream_parser import parse_stream

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NOTION_BASE_URL = "https://www.notion.so"
NOTION_RUN_INFERENCE_URL = f"{NOTION_BASE_URL}/api/v3/runInferenceTranscript"
NOTION_SAVE_TRANSACTIONS_URL = f"{NOTION_BASE_URL}/api/v3/saveTransactions"
NOTION_AI_REFERER = f"{NOTION_BASE_URL}/ai"
NOTION_CHAT_REFERER = f"{NOTION_BASE_URL}/chat"
NOTION_CLIENT_VERSION = "23.13.20260324.1803"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


class NotionUpstreamError(RuntimeError):
    """Notion 上游请求失败或返回异常内容。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retriable: bool = True,
        response_excerpt: str = "",
        request_id: str = "",
        should_cooldown: bool = False,
        error_kind: str = "upstream_http",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
        self.response_excerpt = response_excerpt
        self.request_id = request_id
        self.should_cooldown = should_cooldown
        self.error_kind = error_kind


class NotionOpusAPI:
    def __init__(self, account_config: dict):
        self.token_v2 = account_config.get("token_v2", "")
        self.space_id = account_config.get("space_id", "")
        self.user_id = account_config.get("user_id", "")
        self.space_view_id = account_config.get("space_view_id", "")
        self.user_name = account_config.get("user_name", "user")
        self.user_email = account_config.get("user_email", "")
        self.url = NOTION_RUN_INFERENCE_URL
        self.delete_url = NOTION_SAVE_TRANSACTIONS_URL
        self.account_key = self.user_email or self.user_id or "unknown-account"

    @staticmethod
    def _extract_request_id(response: requests.Response | None) -> str:
        if response is None:
            return ""
        return str(response.headers.get("x-notion-request-id", "") or "").strip()

    def _token_fingerprint(self) -> str:
        token = str(self.token_v2 or "").strip()
        if not token:
            return ""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    def _build_cookies(self) -> dict[str, str]:
        return {
            "token_v2": self.token_v2,
            "notion_user_id": self.user_id,
        }

    def _build_thread_headers(self) -> dict[str, str]:
        cookie_header = "; ".join(
            f"{key}={value}" for key, value in self._build_cookies().items() if value
        )
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
            "x-notion-active-user-header": self.user_id,
            "x-notion-space-id": self.space_id,
            "notion-audit-log-platform": "web",
            "notion-client-version": NOTION_CLIENT_VERSION,
            "origin": NOTION_BASE_URL,
            "referer": NOTION_AI_REFERER,
            "cookie": cookie_header,
        }

    def _build_request_headers(self, *, referer: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
            "User-Agent": DEFAULT_USER_AGENT,
            "x-notion-space-id": self.space_id,
            "x-notion-active-user-header": self.user_id,
            "notion-audit-log-platform": "web",
            "notion-client-version": NOTION_CLIENT_VERSION,
            "origin": NOTION_BASE_URL,
            "referer": referer,
        }

    def _to_notion_transcript(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for block in transcript:
            if block.get("type") != "config":
                converted.append(block)
                continue

            value = block.get("value")
            if not isinstance(value, dict):
                converted.append(block)
                continue

            notion_block = dict(block)
            notion_value = dict(value)
            notion_value["model"] = get_notion_model(str(value.get("model", "") or ""))
            notion_block["value"] = notion_value
            converted.append(notion_block)
        return converted

    def _resolve_thread_type(self, notion_transcript: list[dict[str, Any]]) -> str:
        for block in notion_transcript:
            if block.get("type") != "config":
                continue
            value = block.get("value")
            if isinstance(value, dict):
                thread_type = str(value.get("type", "") or "").strip()
                if thread_type:
                    return thread_type
        return "workflow"

    def _resolve_request_profile(
        self,
        thread_type: str,
        *,
        should_create_thread: bool,
    ) -> dict[str, Any]:
        return {
            "thread_type": thread_type,
            "create_thread": should_create_thread,
            "is_partial_transcript": not should_create_thread,
            "precreate_thread": False,
            "include_debug_overrides": True,
            "generate_title": should_create_thread,
            "set_unread_state": False,
            "include_thread_parent_pointer": should_create_thread,
            "referer": NOTION_AI_REFERER if should_create_thread else NOTION_CHAT_REFERER,
        }

    def _build_payload(
        self,
        *,
        notion_transcript: list[dict[str, Any]],
        thread_id: str,
        trace_id: str,
        thread_type: str,
        request_profile: dict[str, Any],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "traceId": trace_id,
            "spaceId": self.space_id,
            "threadId": thread_id,
            "threadType": thread_type,
            "createThread": request_profile["create_thread"],
            "generateTitle": request_profile["generate_title"],
            "saveAllThreadOperations": True,
            "setUnreadState": request_profile["set_unread_state"],
            "isPartialTranscript": request_profile["is_partial_transcript"],
            "asPatchResponse": True,
            "isUserInAnySalesAssistedSpace": False,
            "isSpaceSalesAssisted": False,
            "transcript": notion_transcript,
        }
        if request_profile["include_thread_parent_pointer"]:
            payload["threadParentPointer"] = {
                "table": "space",
                "id": self.space_id,
                "spaceId": self.space_id,
            }
        if request_profile["include_debug_overrides"]:
            payload["debugOverrides"] = {
                "emitAgentSearchExtractedResults": True,
                "cachedInferences": {},
                "annotationInferences": {},
                "emitInferences": False,
            }
        return payload

    def _build_log_context(
        self,
        *,
        trace_id: str,
        thread_id: str,
        notion_transcript: list[dict[str, Any]],
        request_profile: dict[str, Any],
        headers: dict[str, str],
        cookies: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "thread_id": thread_id,
            "thread_type": request_profile["thread_type"],
            "create_thread": bool(request_profile["create_thread"]),
            "is_partial_transcript": bool(request_profile["is_partial_transcript"]),
            "generate_title": bool(request_profile["generate_title"]),
            "set_unread_state": bool(request_profile["set_unread_state"]),
            "include_thread_parent_pointer": bool(
                request_profile["include_thread_parent_pointer"]
            ),
            "precreate_thread": bool(request_profile["precreate_thread"]),
            "include_debug_overrides": bool(request_profile["include_debug_overrides"]),
            "account": self.account_key,
            "space_id": self.space_id,
            "cookie_keys": sorted(cookies.keys()),
            "token_fingerprint": self._token_fingerprint(),
            "notion_client_version": headers.get("notion-client-version", ""),
            "referer": headers.get("referer", ""),
            "transcript_length": len(notion_transcript),
            "transcript_block_types": [str(block.get("type", "")) for block in notion_transcript],
        }

    def _is_cooldown_worthy_status(self, status_code: int | None) -> bool:
        return status_code == 429

    def _classify_http_error(self, status_code: int | None) -> str:
        if status_code == 429:
            return "upstream_rate_limited"
        if status_code in {401, 403}:
            return "upstream_auth_failed"
        if status_code is not None and status_code >= 500:
            return "upstream_server_error"
        return "upstream_http_error"

    def _create_thread(self, thread_id: str, thread_type: str) -> bool:
        payload = {
            "requestId": str(uuid.uuid4()),
            "transactions": [
                {
                    "id": str(uuid.uuid4()),
                    "spaceId": self.space_id,
                    "operations": [
                        {
                            "pointer": {"table": "thread", "id": thread_id, "spaceId": self.space_id},
                            "path": [],
                            "command": "set",
                            "args": {
                                "id": thread_id,
                                "version": 1,
                                "parent_id": self.space_id,
                                "parent_table": "space",
                                "space_id": self.space_id,
                                "created_time": int(time.time() * 1000),
                                "created_by_id": self.user_id,
                                "created_by_table": "notion_user",
                                "messages": [],
                                "data": {},
                                "alive": True,
                                "type": thread_type,
                            },
                        }
                    ],
                }
            ],
        }
        try:
            resp = requests.post(
                self.delete_url,
                json=payload,
                headers=self._build_thread_headers(),
                timeout=20,
            )
            if resp.status_code == 200:
                return True
            logger.warning(
                "Pre-create thread failed",
                extra={
                    "request_info": {
                        "event": "thread_precreate_failed",
                        "thread_id": thread_id,
                        "thread_type": thread_type,
                        "status": resp.status_code,
                        "x_notion_request_id": self._extract_request_id(resp),
                    }
                },
            )
        except Exception:
            logger.warning(
                "Pre-create thread raised exception",
                exc_info=True,
                extra={
                    "request_info": {
                        "event": "thread_precreate_error",
                        "thread_id": thread_id,
                        "thread_type": thread_type,
                    }
                },
            )
        return False

    def delete_thread(self, thread_id: str) -> None:
        headers = self._build_thread_headers()
        payload = {
            "requestId": str(uuid.uuid4()),
            "transactions": [
                {
                    "id": str(uuid.uuid4()),
                    "spaceId": self.space_id,
                    "operations": [
                        {
                            "pointer": {
                                "table": "thread",
                                "id": thread_id,
                                "spaceId": self.space_id,
                            },
                            "command": "update",
                            "path": [],
                            "args": {"alive": False},
                        }
                    ],
                }
            ],
        }
        try:
            resp = requests.post(self.delete_url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                logger.info(
                    "Thread auto-deleted from Notion home",
                    extra={"request_info": {"event": "thread_deleted", "thread_id": thread_id}},
                )
            else:
                logger.warning(
                    f"Thread deletion failed: HTTP {resp.status_code}",
                    extra={
                        "request_info": {
                            "event": "thread_delete_failed",
                            "thread_id": thread_id,
                            "status": resp.status_code,
                            "x_notion_request_id": self._extract_request_id(resp),
                        }
                    },
                )
        except Exception as exc:
            logger.warning(
                f"Thread deletion raised an exception: {exc}",
                extra={"request_info": {"event": "thread_delete_error", "thread_id": thread_id}},
            )

    def stream_response(
        self,
        transcript: list,
        thread_id: Optional[str] = None,
    ) -> Generator[dict[str, Any], None, None]:
        if not isinstance(transcript, list) or not transcript:
            raise ValueError("Invalid transcript payload: transcript must be a non-empty list.")

        notion_transcript = self._to_notion_transcript(transcript)
        thread_type = self._resolve_thread_type(notion_transcript)

        should_create_thread = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        response: requests.Response | None = None

        self.current_thread_id = thread_id

        request_profile = self._resolve_request_profile(
            thread_type,
            should_create_thread=should_create_thread,
        )
        if request_profile["precreate_thread"] and should_create_thread:
            if not self._create_thread(thread_id, thread_type):
                request_profile["create_thread"] = True
                request_profile["is_partial_transcript"] = False

        cookies = self._build_cookies()
        headers = self._build_request_headers(referer=request_profile["referer"])
        payload = self._build_payload(
            notion_transcript=notion_transcript,
            thread_id=thread_id,
            trace_id=trace_id,
            thread_type=thread_type,
            request_profile=request_profile,
        )
        log_context = self._build_log_context(
            trace_id=trace_id,
            thread_id=thread_id,
            notion_transcript=notion_transcript,
            request_profile=request_profile,
            headers=headers,
            cookies=cookies,
        )

        logger.info(
            "Dispatching request to Notion upstream",
            extra={"request_info": {"event": "notion_upstream_request", **log_context}},
        )

        try:
            scraper = cloudscraper.create_scraper()
            response = scraper.post(
                self.url,
                cookies=cookies,
                headers=headers,
                json=payload,
                stream=True,
                timeout=(15, 120),
            )
            upstream_request_id = self._extract_request_id(response)
            response_log_context = {
                **log_context,
                "status_code": response.status_code,
                "x_notion_request_id": upstream_request_id,
            }

            if response.status_code != 200:
                excerpt = (response.text or "").strip().replace("\n", " ")[:300]
                logger.warning(
                    "Notion upstream returned non-200 response",
                    extra={
                        "request_info": {
                            "event": "notion_upstream_response",
                            **response_log_context,
                            "response_excerpt": excerpt,
                        }
                    },
                )
                raise NotionUpstreamError(
                    f"Notion upstream returned HTTP {response.status_code}.",
                    status_code=response.status_code,
                    retriable=response.status_code >= 500,
                    response_excerpt=excerpt,
                    request_id=upstream_request_id,
                    should_cooldown=self._is_cooldown_worthy_status(response.status_code),
                    error_kind=self._classify_http_error(response.status_code),
                )

            logger.info(
                "Notion upstream accepted request",
                extra={
                    "request_info": {
                        "event": "notion_upstream_response",
                        **response_log_context,
                    }
                },
            )

            emitted = False
            for chunk in parse_stream(response):
                emitted = True
                yield chunk

            if not emitted:
                raise NotionUpstreamError(
                    "Notion upstream returned an empty stream.",
                    status_code=502,
                    retriable=True,
                    request_id=upstream_request_id,
                    should_cooldown=False,
                    error_kind="upstream_empty_stream",
                )

            logger.info(
                "Thread completed and preserved for conversation context",
                extra={
                    "request_info": {
                        "event": "thread_completed_preserved",
                        "thread_id": thread_id,
                        "was_created_new": should_create_thread,
                        "thread_type": thread_type,
                        "x_notion_request_id": upstream_request_id,
                    }
                },
            )
        except requests.exceptions.Timeout as exc:
            logger.error(
                "Request timeout",
                exc_info=True,
                extra={
                    "request_info": {
                        "event": "notion_upstream_timeout",
                        **log_context,
                    }
                },
            )
            raise NotionUpstreamError(
                "Request to Notion upstream timed out.",
                retriable=True,
                should_cooldown=False,
                error_kind="upstream_timeout",
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.error(
                "Request failed",
                exc_info=True,
                extra={
                    "request_info": {
                        "event": "notion_upstream_request_exception",
                        **log_context,
                    }
                },
            )
            raise NotionUpstreamError(
                "Request to Notion upstream failed. Please try again later.",
                retriable=True,
                should_cooldown=False,
                error_kind="upstream_request_exception",
            ) from exc
        finally:
            if response is not None:
                response.close()
