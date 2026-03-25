from __future__ import annotations

from functools import lru_cache
import json
import os


DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "adaptive_confidence_recalibration": True,
    "certificate_pdf_visual_support": True,
    "mrz_cross_validation": True,
    "pack_prompt_specialization": True,
}


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return None


@lru_cache(maxsize=1)
def get_feature_flags() -> dict[str, bool]:
    resolved = dict(DEFAULT_FEATURE_FLAGS)
    raw = os.getenv("OCR_FEATURE_FLAGS")
    if not raw:
        return resolved

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return resolved

    if not isinstance(parsed, dict):
        return resolved

    for key, value in parsed.items():
        coerced = _coerce_bool(value)
        if key in resolved and coerced is not None:
            resolved[key] = coerced

    return resolved


def feature_enabled(name: str, default: bool | None = None) -> bool:
    flags = get_feature_flags()
    if name in flags:
        return flags[name]
    return DEFAULT_FEATURE_FLAGS.get(name, True if default is None else default)


def feature_flags_snapshot() -> dict[str, bool]:
    return dict(get_feature_flags())


def clear_feature_flags_cache() -> None:
    get_feature_flags.cache_clear()
