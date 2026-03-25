import threading
import time
from typing import Dict, List

from app.logger import logger
from app.notion_client import NotionOpusAPI


class AccountPool:
    def __init__(self, accounts: List[dict]):
        if not accounts:
            raise ValueError("账号池初始化失败：未提供任何账号配置。")

        self.clients = [NotionOpusAPI(acc) for acc in accounts]
        self.cooldown_until = [0.0 for _ in self.clients]
        self._current_index = 0
        self._lock = threading.Lock()

    def get_client(self) -> NotionOpusAPI:
        now = time.time()
        with self._lock:
            start_index = self._current_index

            while True:
                idx = self._current_index
                if self.cooldown_until[idx] <= now:
                    self._current_index = (self._current_index + 1) % len(self.clients)
                    return self.clients[idx]

                self._current_index = (self._current_index + 1) % len(self.clients)
                if self._current_index == start_index:
                    next_available = min(self.cooldown_until)
                    wait_seconds = max(1, int(next_available - now))
                    raise RuntimeError(
                        f"Notion 账号限流中（触发官方公平使用政策），请在 {wait_seconds} 秒后重试。"
                    )

    def get_status_summary(self) -> Dict[str, int]:
        now = time.time()
        with self._lock:
            active = sum(1 for ts in self.cooldown_until if ts <= now)
            cooling = len(self.cooldown_until) - active
            return {
                "total": len(self.clients),
                "active": active,
                "cooling": cooling,
            }

    def mark_failed(
        self,
        client: NotionOpusAPI,
        cooldown_seconds: int = 10,
        *,
        reason: str = "unknown",
        upstream_status_code: int | None = None,
        upstream_request_id: str = "",
    ):
        with self._lock:
            try:
                idx = self.clients.index(client)
                self.cooldown_until[idx] = time.time() + cooldown_seconds
                logger.warning(
                    "Account marked as failed",
                    extra={
                        "request_info": {
                            "event": "account_failed",
                            "account": client.account_key,
                            "space_id": client.space_id,
                            "cooldown_seconds": cooldown_seconds,
                            "reason": reason,
                            "upstream_status_code": upstream_status_code,
                            "x_notion_request_id": upstream_request_id,
                        }
                    },
                )
            except ValueError:
                logger.warning(
                    "Attempted to mark unknown account as failed",
                    extra={"request_info": {"event": "account_failed_unknown", "reason": reason}},
                )
