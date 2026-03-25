from __future__ import annotations

import os
import re


RUT_LIKE_PATTERN = re.compile(r"\b(?:\d{1,2}\.?\d{3}\.?\d{3}|\d{7,8})-[\dkK]\b")
DNI_LIKE_PATTERN = re.compile(r"\b\d{8,10}\b")
ACCOUNT_LIKE_PATTERN = re.compile(r"\b\d{4}-\d{4}-\d{8,}\b")
EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")


def should_redact_logs() -> bool:
    return os.getenv("OCR_LOG_REDACT_PII", "true").lower() != "false"


def _mask(value: str, visible_start: int = 2, visible_end: int = 2) -> str:
    if len(value) <= visible_start + visible_end:
        return "*" * len(value)
    return f"{value[:visible_start]}{'*' * max(4, len(value) - visible_start - visible_end)}{value[-visible_end:]}"


def redact_text(value: str | None) -> str | None:
    if value is None or not should_redact_logs():
        return value

    redacted = EMAIL_PATTERN.sub(lambda match: _mask(match.group(0), 2, 2), value)
    redacted = ACCOUNT_LIKE_PATTERN.sub(lambda match: _mask(match.group(0), 2, 2), redacted)
    redacted = RUT_LIKE_PATTERN.sub(lambda match: _mask(match.group(0), 2, 2), redacted)
    redacted = DNI_LIKE_PATTERN.sub(lambda match: _mask(match.group(0), 2, 2), redacted)
    return redacted


def safe_preview(value: str | None, limit: int = 160) -> str | None:
    redacted = redact_text(value)
    if redacted is None:
        return None
    return redacted[:limit]
