from __future__ import annotations

from typing import Sequence

from app.schemas import IntegrityAssessment, IntegrityIndicator, ReportSection
from app.services.cross_side_consistency import CrossSideConsistencySignal
from app.services.document_packs import DocumentPack, iter_pack_field_keys
from app.services.field_value_utils import canonicalize_chile_run, validate_chile_run_checksum, validate_mrz_check_digits
from app.services.rule_packs import FieldDecisionSignal


def _flatten_sections(report_sections: list[ReportSection]) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in report_sections:
        if section.variant == "pairs" and section.rows:
            for row in section.rows:
                if row:
                    values[row[0].strip().lower()] = row[1] if len(row) > 1 else ""
        elif section.variant == "table" and section.columns and section.rows:
            if len(section.columns) == 2 and section.columns[0].lower() == "campo":
                for row in section.rows:
                    if row:
                        values[row[0].strip().lower()] = row[1] if len(row) > 1 else ""
    return values


def _pack_value(values: dict[str, str], pack: DocumentPack | None, field_key: str) -> str | None:
    candidate_keys = list(iter_pack_field_keys(pack, field_key)) if pack else [field_key]
    for key in candidate_keys:
        candidate = values.get(key.replace("_", "-").lower()) or values.get(key.replace("_", " ").lower())
        if candidate:
            return candidate
    return None


def _average_page_quality(prepared_pages: Sequence[object]) -> float | None:
    qualities = [getattr(page, "quality_score", None) for page in prepared_pages if getattr(page, "quality_score", None) is not None]
    if not qualities:
        return None
    return round(sum(qualities) / len(qualities), 3)


def _average_agreement(field_signals: dict[str, FieldDecisionSignal]) -> float | None:
    if not field_signals:
        return None
    agreements = [signal.agreement_ratio for signal in field_signals.values() if signal.candidate_count > 0]
    if not agreements:
        return None
    return round(sum(agreements) / len(agreements), 3)


def build_integrity_assessment(
    *,
    report_sections: list[ReportSection],
    pack: DocumentPack | None,
    prepared_pages: Sequence[object],
    field_signals: dict[str, FieldDecisionSignal],
    cross_side_signal: CrossSideConsistencySignal | None,
) -> IntegrityAssessment:
    values = _flatten_sections(report_sections)
    indicators: list[IntegrityIndicator] = []
    score = 0.74

    run_value = canonicalize_chile_run(_pack_value(values, pack, "run"))
    mrz_value = _pack_value(values, pack, "mrz") or values.get("mrz")
    average_page_quality = _average_page_quality(prepared_pages)
    average_agreement = _average_agreement(field_signals)
    checksum_valid: bool | None = None

    if run_value:
        checksum_valid = validate_chile_run_checksum(run_value)
        if checksum_valid:
            score += 0.12
        else:
            score -= 0.22
            indicators.append(
                IntegrityIndicator(
                    code="checksum_mismatch",
                    severity="high",
                    source="checksum",
                    message="El RUN detectado no supera la validacion de checksum.",
                )
            )
    elif mrz_value:
        checksum_valid = validate_mrz_check_digits(mrz_value)
        if checksum_valid:
            score += 0.14
        else:
            score -= 0.25
            indicators.append(
                IntegrityIndicator(
                    code="mrz_checksum_mismatch",
                    severity="high",
                    source="mrz",
                    message="La MRZ detectada contiene digitos de control inconsistentes.",
                )
            )
    else:
        checksum_valid = None

    if cross_side_signal is not None:
        if cross_side_signal.identifier_match is True:
            score += 0.08
        elif cross_side_signal.identifier_match is False:
            score -= 0.2
            indicators.append(
                IntegrityIndicator(
                    code="cross_side_mismatch",
                    severity="high",
                    source="cross-side",
                    message="Los identificadores detectados entre frente y dorso no coinciden.",
                )
            )
        else:
            score -= 0.05
            indicators.append(
                IntegrityIndicator(
                    code="cross_side_incomplete",
                    severity="medium",
                    source="cross-side",
                    message="No hubo evidencia suficiente para comparar ambos lados del documento.",
                )
            )

    if average_page_quality is not None:
        if average_page_quality < 0.55:
            score -= 0.14
            indicators.append(
                IntegrityIndicator(
                    code="low_capture_quality",
                    severity="medium",
                    source="capture-quality",
                    message="La calidad de captura es baja y reduce la confianza de integridad documental.",
                )
            )
        elif average_page_quality >= 0.82:
            score += 0.04

    if average_agreement is not None:
        if average_agreement < 0.65:
            score -= 0.12
            indicators.append(
                IntegrityIndicator(
                    code="low_ocr_agreement",
                    severity="medium",
                    source="ocr-consensus",
                    message="Los motores OCR muestran bajo acuerdo en campos relevantes.",
                )
            )
        elif average_agreement >= 0.9:
            score += 0.05

    final_score = round(max(0.05, min(score, 0.99)), 3)
    if final_score >= 0.82:
        risk_level = "low"
    elif final_score >= 0.62:
        risk_level = "medium"
    else:
        risk_level = "high"

    return IntegrityAssessment(
        score=final_score,
        risk_level=risk_level,
        indicators=indicators,
        checks={
            "checksumValid": checksum_valid,
            "crossSideMatch": cross_side_signal.identifier_match if cross_side_signal is not None else None,
            "averagePageQuality": average_page_quality,
            "averageOcrAgreement": average_agreement,
        },
    )
