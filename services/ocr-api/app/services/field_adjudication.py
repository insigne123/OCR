from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import os

from openai import OpenAI

from app.schemas import FieldAdjudicationResult, FieldCandidateResult, FieldConsensusResult
from app.services.document_packs import DocumentPack, PackFieldDefinition
from app.services.field_value_utils import compact as normalized_compact
from app.services.openai_normalizer import has_openai_config

ADJUDICATION_MODES = {"off", "deterministic", "openai", "auto"}


@dataclass(frozen=True)
class _CandidateGroup:
    normalized_value: str
    display_value: str | None
    sources: tuple[str, ...]
    engines: tuple[str, ...]
    total_score: float
    best_score: float
    best_confidence: float
    best_candidate: FieldCandidateResult


def _compact(value: str | None) -> str:
    return normalized_compact(value)


def _resolve_mode(mode_override: str | None = None) -> str:
    mode = (mode_override or os.getenv("OCR_FIELD_ADJUDICATION_MODE", "auto") or "auto").strip().lower()
    return mode if mode in ADJUDICATION_MODES else "auto"


def _openai_model() -> str:
    return os.getenv("OCR_FIELD_ADJUDICATION_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _group_candidates(candidates: list[FieldCandidateResult]) -> list[_CandidateGroup]:
    grouped: dict[str, list[FieldCandidateResult]] = defaultdict(list)
    for candidate in candidates:
        normalized = _compact(candidate.value or candidate.raw_text)
        if not normalized:
            continue
        grouped[normalized].append(candidate)

    groups: list[_CandidateGroup] = []
    for normalized_value, group_candidates in grouped.items():
        ordered = sorted(
            group_candidates,
            key=lambda candidate: (candidate.selected, candidate.score, candidate.confidence or 0.0),
            reverse=True,
        )
        best = ordered[0]
        groups.append(
            _CandidateGroup(
                normalized_value=normalized_value,
                display_value=best.value or best.raw_text,
                sources=tuple(dict.fromkeys(candidate.source for candidate in ordered)),
                engines=tuple(dict.fromkeys(candidate.engine for candidate in ordered)),
                total_score=round(sum(candidate.score for candidate in ordered), 4),
                best_score=best.score,
                best_confidence=max((candidate.confidence or 0.0) for candidate in ordered),
                best_candidate=best,
            )
        )

    return sorted(groups, key=lambda group: (len(group.sources), group.total_score, group.best_confidence), reverse=True)


def _deterministic_decision(
    *,
    field: PackFieldDefinition,
    current_value: str | None,
    candidates: list[FieldCandidateResult],
    consensus: FieldConsensusResult | None,
) -> FieldAdjudicationResult:
    if not candidates:
        return FieldAdjudicationResult(
            method="deterministic",
            abstained=True,
            rationale=f"No hay candidatos OCR suficientes para adjudicar {field.label}.",
        )

    groups = _group_candidates(candidates)
    if not groups:
        return FieldAdjudicationResult(
            method="deterministic",
            abstained=True,
            rationale=f"No hay evidencia OCR utilizable para adjudicar {field.label}.",
        )

    best_group = groups[0]
    second_group = groups[1] if len(groups) > 1 else None
    margin = best_group.total_score - (second_group.total_score if second_group else 0.0)
    agreement_ratio = consensus.agreement_ratio if consensus else 0.0
    disagreement = consensus.disagreement if consensus else len(groups) > 1
    current_matches = _compact(current_value) == best_group.normalized_value if current_value else False
    select_threshold = 0.12 if field.critical else 0.08
    high_evidence = len(best_group.sources) >= 2 or agreement_ratio >= 0.67 or best_group.best_confidence >= 0.94
    safe_to_select = high_evidence and margin >= select_threshold

    if current_matches and not disagreement:
        safe_to_select = True
    if current_matches and field.critical and agreement_ratio >= 0.5 and best_group.best_confidence >= 0.9:
        safe_to_select = True

    if not safe_to_select:
        return FieldAdjudicationResult(
            method="deterministic",
            abstained=True,
            confidence=round(min(max(best_group.best_confidence, agreement_ratio), 1.0), 3),
            rationale=(
                f"Se evita adjudicar {field.label} porque la evidencia es insuficiente o hay conflicto entre motores. "
                f"Agreement {agreement_ratio:.2f}, margen {margin:.2f}."
            ),
            evidence_sources=list(best_group.sources),
        )

    return FieldAdjudicationResult(
        method="deterministic",
        abstained=False,
        selected_value=best_group.display_value,
        selected_source=best_group.best_candidate.source,
        selected_engine=best_group.best_candidate.engine,
        confidence=round(min(max((best_group.best_confidence * 0.7) + (agreement_ratio * 0.3), 0.0), 1.0), 3),
        rationale=(
            f"Se selecciona {field.label} desde {best_group.best_candidate.source} por mejor soporte OCR "
            f"({len(best_group.sources)} motores, agreement {agreement_ratio:.2f})."
        ),
        evidence_sources=list(best_group.sources),
    )


def _openai_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["select", "abstain"]},
            "candidate_id": {"type": ["string", "null"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "evidence_sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["decision", "candidate_id", "confidence", "rationale", "evidence_sources"],
    }


def _call_openai_adjudicator(
    *,
    field: PackFieldDefinition,
    current_value: str | None,
    candidates: list[FieldCandidateResult],
    consensus: FieldConsensusResult | None,
) -> FieldAdjudicationResult:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    candidate_index = {f"candidate_{index + 1}": candidate for index, candidate in enumerate(candidates[:6])}
    payload = {
        "field": {
            "field_key": field.field_key,
            "label": field.label,
            "critical": field.critical,
            "required": field.required,
            "current_value": current_value,
        },
        "consensus": {
            "agreement_ratio": consensus.agreement_ratio if consensus else 0.0,
            "disagreement": consensus.disagreement if consensus else len(candidate_index) > 1,
            "candidate_count": consensus.candidate_count if consensus else len(candidate_index),
        },
        "candidates": [
            {
                "candidate_id": candidate_id,
                "source": candidate.source,
                "engine": candidate.engine,
                "value": candidate.value,
                "raw_text": candidate.raw_text,
                "confidence": candidate.confidence,
                "score": candidate.score,
                "selected": candidate.selected,
                "match_type": candidate.match_type,
                "evidence_text": candidate.evidence_text,
            }
            for candidate_id, candidate in candidate_index.items()
        ],
    }

    response = client.responses.create(
        model=_openai_model(),
        input=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Eres un adjudicador OCR por campo. Debes elegir un candidato existente o abstenerte. "
                            "No inventes valores, no combines candidatos y no reescribas el contenido. "
                            "Si la evidencia es insuficiente o contradictoria, responde abstain."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=True)}],
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "field_adjudication",
                "schema": _openai_schema(),
                "strict": True,
            }
        },
    )

    parsed = json.loads(response.output_text)
    if parsed["decision"] == "abstain":
        return FieldAdjudicationResult(
            method="openai",
            abstained=True,
            confidence=float(parsed["confidence"]),
            rationale=parsed["rationale"],
            evidence_sources=list(parsed["evidence_sources"]),
        )

    candidate = candidate_index.get(parsed["candidate_id"] or "")
    if candidate is None:
        return FieldAdjudicationResult(
            method="openai",
            abstained=True,
            rationale="El adjudicador OpenAI no devolvio un candidato valido; se fuerza abstencion segura.",
        )

    return FieldAdjudicationResult(
        method="openai",
        abstained=False,
        selected_value=candidate.value or candidate.raw_text,
        selected_source=candidate.source,
        selected_engine=candidate.engine,
        confidence=float(parsed["confidence"]),
        rationale=parsed["rationale"],
        evidence_sources=list(dict.fromkeys([*parsed["evidence_sources"], candidate.source])),
    )


def adjudicate_field(
    *,
    field: PackFieldDefinition,
    current_value: str | None,
    candidates: list[FieldCandidateResult],
    consensus: FieldConsensusResult | None,
    mode_override: str | None = None,
) -> FieldAdjudicationResult:
    mode = _resolve_mode(mode_override)
    if mode == "off":
        return FieldAdjudicationResult(method="off", abstained=True, rationale="Adjudicacion deshabilitada por configuracion.")

    should_try_openai = (
        mode == "openai"
        or (mode == "auto" and has_openai_config() and field.critical and (consensus.disagreement if consensus else len(candidates) > 1))
    )

    if should_try_openai:
        try:
            return _call_openai_adjudicator(field=field, current_value=current_value, candidates=candidates, consensus=consensus)
        except Exception as exc:  # noqa: BLE001
            deterministic = _deterministic_decision(field=field, current_value=current_value, candidates=candidates, consensus=consensus)
            return FieldAdjudicationResult(
                method=f"{deterministic.method}-fallback",
                abstained=deterministic.abstained,
                selected_value=deterministic.selected_value,
                selected_source=deterministic.selected_source,
                selected_engine=deterministic.selected_engine,
                confidence=deterministic.confidence,
                rationale=f"{deterministic.rationale} Fallback por error OpenAI: {exc}",
                evidence_sources=deterministic.evidence_sources,
            )

    return _deterministic_decision(field=field, current_value=current_value, candidates=candidates, consensus=consensus)


def adjudication_runtime_mode(mode_override: str | None = None) -> str:
    mode = _resolve_mode(mode_override)
    if mode == "auto" and not has_openai_config():
        return "deterministic"
    return mode


def should_adjudicate_pack(pack: DocumentPack | None, mode_override: str | None = None) -> bool:
    return bool(
        pack
        and pack.expected_fields
        and pack.document_family in {"identity", "certificate"}
        and adjudication_runtime_mode(mode_override) != "off"
    )
