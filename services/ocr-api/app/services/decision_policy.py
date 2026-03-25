from __future__ import annotations

from dataclasses import dataclass
import json
import os


@dataclass(frozen=True)
class DecisionThresholdSettings:
    reject_confidence: float
    accept_with_warning_confidence: float
    auto_accept_confidence: float
    auto_accept_agreement: float
    review_agreement: float
    cross_side_confidence: float


def _coerce_float(value: object, fallback: float) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _load_policy_config() -> dict[str, object]:
    raw = os.getenv("OCR_DECISION_POLICY_CONFIG")
    if not raw:
        return {"defaults": {}, "rules": []}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"defaults": {}, "rules": []}


def _match_rule(rule: dict[str, object], *, tenant_id: str | None, document_family: str, country: str, pack_id: str | None) -> bool:
    if rule.get("tenantId") not in {None, "", tenant_id}:
        return False
    if rule.get("family") not in {None, "", document_family}:
        return False
    if rule.get("country") not in {None, "", country}:
        return False
    if rule.get("packId") not in {None, "", pack_id}:
        return False
    return True


def _merge_thresholds(base: DecisionThresholdSettings, raw_overrides: dict[str, object] | None) -> DecisionThresholdSettings:
    overrides = raw_overrides or {}
    return DecisionThresholdSettings(
        reject_confidence=_coerce_float(overrides.get("rejectConfidence"), base.reject_confidence),
        accept_with_warning_confidence=_coerce_float(overrides.get("acceptWithWarningConfidence"), base.accept_with_warning_confidence),
        auto_accept_confidence=_coerce_float(overrides.get("autoAcceptConfidence"), base.auto_accept_confidence),
        auto_accept_agreement=_coerce_float(overrides.get("autoAcceptAgreement"), base.auto_accept_agreement),
        review_agreement=_coerce_float(overrides.get("reviewAgreement"), base.review_agreement),
        cross_side_confidence=_coerce_float(overrides.get("crossSideConfidence"), base.cross_side_confidence),
    )


def resolve_decision_thresholds(
    *,
    tenant_id: str | None,
    document_family: str,
    country: str,
    pack_id: str | None,
    defaults: DecisionThresholdSettings,
) -> DecisionThresholdSettings:
    config = _load_policy_config()
    resolved = _merge_thresholds(defaults, config.get("defaults") if isinstance(config.get("defaults"), dict) else None)

    for rule in config.get("rules", []):
        if not isinstance(rule, dict):
            continue
        if not _match_rule(rule, tenant_id=tenant_id, document_family=document_family, country=country, pack_id=pack_id):
            continue
        raw_thresholds = rule.get("thresholds") if isinstance(rule.get("thresholds"), dict) else rule
        resolved = _merge_thresholds(resolved, raw_thresholds if isinstance(raw_thresholds, dict) else None)

    return resolved
