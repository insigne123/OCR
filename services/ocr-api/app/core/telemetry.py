from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from app.core.security import redact_text


def _logger() -> logging.Logger:
    logger = logging.getLogger("ocr-api")
    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, os.getenv("OCR_LOG_LEVEL", "INFO").upper(), logging.INFO))
    logger.propagate = False
    return logger


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def log_event(event: str, **payload: Any) -> None:
    message = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **_sanitize(payload),
    }
    _logger().info(json.dumps(message, ensure_ascii=True))
