from __future__ import annotations

from dataclasses import dataclass
import re

from app.schemas import CustomExtractionFieldResult
from app.services.document_classifier import DocumentClassification
from app.services.field_value_utils import normalize_date_value, slugify
from app.services.layout_extraction import LayoutExtractionResult, LayoutKeyValue

NUMBER_PATTERN = re.compile(r"-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?")
DATE_PATTERN = re.compile(r"\b(?:\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b")
STOPWORDS = {"del", "de", "la", "el", "los", "las", "para", "with", "con", "holder", "titular", "name", "nombre", "field", "schema"}


@dataclass(frozen=True)
class SchemaFieldDefinition:
    field_name: str
    field_type: str
    description: str


def _normalized_keywords(field_name: str, description: str) -> list[str]:
    values = [field_name, description, field_name.replace("_", " ")]
    keywords: list[str] = []
    for value in values:
        for token in re.split(r"[^a-zA-Z0-9]+", value.lower()):
            token = token.strip()
            if len(token) >= 3 and token not in STOPWORDS and token not in keywords:
                keywords.append(token)
    normalized_field = field_name.lower()
    normalized_description = description.lower()
    if "rut" in normalized_field or "rut" in normalized_description or "run" in normalized_field:
        for alias in ("rut", "run"):
            if alias not in keywords:
                keywords.insert(0, alias)
    if "account" in normalized_field or "cuenta" in normalized_field or "capitalizacion" in normalized_description:
        for alias in ("cuenta", "capitalizacion", "account"):
            if alias not in keywords:
                keywords.insert(0, alias)
    if "certificate" in normalized_field or "certificado" in normalized_field or "certificado" in normalized_description:
        for alias in ("certificado", "certificate"):
            if alias not in keywords:
                keywords.insert(0, alias)
    return keywords[:8]


def _score_layout_pair(pair: LayoutKeyValue, keywords: list[str]) -> int:
    label = slugify(pair.label)
    value = slugify(pair.value)
    score = 0
    label_hits = 0
    for keyword in keywords:
        if keyword in label:
            score += 4
            label_hits += 1
        if keyword in value:
            score += 1
    return score if label_hits > 0 else 0


def _coerce_value(raw_value: str | None, field_type: str) -> str | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None
    if field_type == "date":
        return normalize_date_value(value) or value
    if field_type == "number":
        match = NUMBER_PATTERN.search(value)
        return match.group(0) if match else value
    return value


def _fallback_from_text(source_text: str, definition: SchemaFieldDefinition) -> tuple[str | None, str]:
    if definition.field_type == "date":
        match = DATE_PATTERN.search(source_text)
        if match:
            return normalize_date_value(match.group(0)) or match.group(0), "Detected date-like value in raw text."
    if definition.field_type == "number":
        match = NUMBER_PATTERN.search(source_text)
        if match:
            return match.group(0), "Detected numeric candidate in raw text."
    return None, "No reliable evidence found in raw text."


def _score_known_value(label: str, value: str | None, keywords: list[str]) -> int:
    if value is None or not value.strip():
        return 0
    normalized_label = slugify(label)
    normalized_value = slugify(value)
    score = 0
    label_hits = 0
    for keyword in keywords:
        if keyword in normalized_label:
            score += 5
            label_hits += 1
        if keyword in normalized_value:
            score += 1
    return score if label_hits > 0 else 0


def extract_custom_fields(
    *,
    schema: dict[str, dict[str, str]],
    source_text: str,
    layout: LayoutExtractionResult,
    classification: DocumentClassification,
    known_values: dict[str, str] | None = None,
) -> list[CustomExtractionFieldResult]:
    results: list[CustomExtractionFieldResult] = []
    supported_values = known_values or {}

    for field_name, schema_entry in schema.items():
        definition = SchemaFieldDefinition(
            field_name=field_name,
            field_type=(schema_entry.get("type") or "string").strip().lower(),
            description=(schema_entry.get("description") or "").strip(),
        )
        keywords = _normalized_keywords(definition.field_name, definition.description)
        ranked_known_values = sorted(
            supported_values.items(),
            key=lambda item: _score_known_value(item[0], item[1], keywords),
            reverse=True,
        )
        best_known = ranked_known_values[0] if ranked_known_values and _score_known_value(ranked_known_values[0][0], ranked_known_values[0][1], keywords) > 0 else None
        if best_known is not None:
            label, raw_value = best_known
            coerced = _coerce_value(raw_value, definition.field_type)
            confidence = 0.91 if slugify(label) in {slugify(field_name), slugify(field_name.replace("_", " "))} else 0.82
            results.append(
                CustomExtractionFieldResult(
                    field_name=field_name,
                    value=coerced,
                    confidence=confidence,
                    evidence_text=raw_value,
                    page_number=1,
                    source="supported-pack",
                    reasoning=f"Matched schema field against normalized supported field '{label}'.",
                )
            )
            continue

        ranked_pairs = sorted(layout.key_value_pairs, key=lambda pair: _score_layout_pair(pair, keywords), reverse=True)
        best_pair = ranked_pairs[0] if ranked_pairs and _score_layout_pair(ranked_pairs[0], keywords) > 0 else None

        if best_pair is not None:
            coerced = _coerce_value(best_pair.value, definition.field_type)
            confidence = 0.88 if slugify(best_pair.label) in {slugify(field_name), slugify(field_name.replace("_", " "))} else 0.74
            results.append(
                CustomExtractionFieldResult(
                    field_name=field_name,
                    value=coerced,
                    confidence=confidence,
                    evidence_text=best_pair.raw_line,
                    page_number=best_pair.page_number,
                    source="layout-key-value",
                    reasoning=f"Matched schema field against layout label '{best_pair.label}'.",
                )
            )
            continue

        if classification.supported:
            fallback_value, reasoning = None, "No direct label evidence was found in supported fields or layout pairs."
        else:
            fallback_value, reasoning = _fallback_from_text(source_text, definition)
        results.append(
            CustomExtractionFieldResult(
                field_name=field_name,
                value=fallback_value,
                confidence=0.56 if fallback_value is not None else 0.12,
                evidence_text=fallback_value,
                page_number=1,
                source="text-fallback",
                reasoning=reasoning,
            )
        )

    if classification.supported and classification.document_family != "unclassified":
        return [
            CustomExtractionFieldResult(
                field_name=result.field_name,
                value=result.value,
                confidence=min(0.99, round(result.confidence + 0.03, 3)) if result.value else result.confidence,
                evidence_text=result.evidence_text,
                page_number=result.page_number,
                source=result.source,
                reasoning=f"{result.reasoning} Classification context: {classification.document_family}/{classification.country}.",
            )
            for result in results
        ]

    return results
