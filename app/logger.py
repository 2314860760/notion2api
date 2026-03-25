import json
import logging
import os
from datetime import datetime


def _resolve_log_level() -> int:
    raw_level = str(os.getenv("LOG_LEVEL", "INFO") or "INFO").strip().upper()
    return getattr(logging, raw_level, logging.INFO)


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志格式。"""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_info"):
            log_record.update(record.request_info)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, ensure_ascii=False)


def setup_logger(name: str = "notion_opus") -> logging.Logger:
    """配置并返回全局 logger。"""
    logger = logging.getLogger(name)
    logger.setLevel(_resolve_log_level())
    logger.propagate = False

    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(JsonFormatter())
        logger.addHandler(console_handler)

    return logger


logger = setup_logger()
