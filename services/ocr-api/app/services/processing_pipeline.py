from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
from time import perf_counter
from typing import Sequence, cast
from uuid import uuid4
import base64

from app.core.contracts import NormalizationRequest
from app.core.feature_flags import feature_enabled
from app.core.telemetry import log_event
from app.engines.factory import get_heuristic_normalizer_engine, get_structured_normalizer_engine, get_structured_normalizer_mode
from app.schemas import (
    ConfidenceDetails,
    DocumentDecision,
    FieldAdjudicationResult,
    ExtractedFieldResult,
    FieldCandidateResult,
    FieldConsensusResult,
    IntegrityAssessment,
    LayoutKeyValueCandidate,
    NormalizedDocument,
    OCRRunInfo,
    OCRRunPageInfo,
    OCRTokenInfo,
    ProcessingTraceEntry,
    ProcessDocumentInfo,
    ProcessMetadata,
    ProcessPageInfo,
    ProcessResponse,
    QualityAssessment,
    ReportSection,
    ResponseMode,
    ValidationIssue,
)
from app.services.cross_side_consistency import CrossSideConsistencySignal, build_cross_side_consistency_signal
from app.services.integrity_scoring import build_integrity_assessment
from app.services.document_classifier import classify_document
from app.services.document_packs import DocumentPack, PackFieldDefinition, normalize_requested_country, normalize_requested_family, resolve_document_pack
from app.services.document_splitter import SplitDocumentResult, split_document_pages
from app.services.field_adjudication import adjudicate_field, adjudication_runtime_mode, should_adjudicate_pack
from app.services.field_value_utils import (
    canonicalize_chile_run,
    canonicalize_identity_document_number,
    compact as normalized_compact,
    derive_identity_holder_name,
    find_value_by_key_fragments,
    is_placeholder_name,
    normalize_date_value,
    parse_identity_card_td1_fallback,
    slugify,
    validate_chile_run_checksum,
    validate_mrz_check_digits,
)
from app.services.heuristic_normalizer import normalize_text_with_heuristics
from app.services.layout_extraction import LayoutExtractionResult, LayoutKeyValue, extract_layout_from_page_texts, extract_layout_from_tokens
from app.services.mock_pipeline import build_html
from app.services.ocr_ensemble import DEFAULT_LOCAL_ENGINES, VisualOCREnsembleResult, VisualOCRRunRecord, resolve_visual_ocr_engine_names, run_visual_ocr_ensemble
from app.services.page_analysis import analyze_document_pages
from app.services.page_preprocessing import OCRVariantSet, PreprocessedPage, build_ocr_variant_sets, prepare_document_pages
from app.services.quality_analysis import build_quality_assessment
from app.services.rule_packs import FieldDecisionSignal, evaluate_normalized_document
from app.services.text_extraction import extract_document_text
from app.services.visual_ocr import OCRToken, VisualOCRResult
from app.services.supplemental_field_extractors import extract_supplemental_fields
def _append_source_issue(issues: list[ValidationIssue], extraction_source: str) -> list[ValidationIssue]:
    if extraction_source not in {"pdf-no-text", "binary-no-text"}:
        return issues

    return [
        *issues,
        ValidationIssue(
            id="issue-no-source-text",
            type="LOW_EVIDENCE",
            field="source_text",
            severity="medium",
            message="El archivo no ofrecio texto embebido suficiente; el caso podria requerir OCR visual o interpretacion multimodal.",
            suggestedAction="Reprocesar con OCR visual completo o revisar manualmente el documento.",
        ),
    ]


def _slugify(value: str) -> str:
    return slugify(value)


def _compact(value: str | None) -> str:
    return normalized_compact(value)


def _is_missing_value(value: str | None) -> bool:
    return value is None or value.strip().upper() in {"", "-", "NO DETECTADO", "NO DETECTADA", "NO DETECTADOS", "NO DETECTADAS", "PENDING"}


def _bbox_from_polygon(points: list[list[float]]) -> dict[str, float] | None:
    if not points:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _match_token(value: str | None, tokens: Sequence[OCRToken | OCRTokenInfo]) -> OCRToken | OCRTokenInfo | None:
    normalized_value = _compact(value)
    if len(normalized_value) < 4:
        return None

    exact_match = next((token for token in tokens if _compact(token.text) == normalized_value), None)
    if exact_match:
        return exact_match

    partial_candidates = [
        token
        for token in tokens
        if len(_compact(token.text)) >= 4 and (_compact(token.text) in normalized_value or normalized_value in _compact(token.text))
    ]
    if not partial_candidates:
        return None

    return max(partial_candidates, key=lambda token: (token.confidence, len(_compact(token.text))))


def _match_layout_pair(
    label: str,
    field_name: str,
    value: str | None,
    layout_pairs: Sequence[LayoutKeyValue | LayoutKeyValueCandidate],
) -> LayoutKeyValue | LayoutKeyValueCandidate | None:
    normalized_label = _slugify(label)
    normalized_field_name = _slugify(field_name)
    normalized_value = _compact(value)

    exact_label = next(
        (
            pair
            for pair in layout_pairs
            if _slugify(pair.label) in {normalized_label, normalized_field_name}
            and (not normalized_value or normalized_value in _compact(pair.value) or _compact(pair.value) in normalized_value)
        ),
        None,
    )
    if exact_label:
        return exact_label

    fuzzy_label = next(
        (
            pair
            for pair in layout_pairs
            if _slugify(pair.label) in normalized_label or normalized_label in _slugify(pair.label) or _slugify(pair.label) in normalized_field_name
        ),
        None,
    )
    if fuzzy_label:
        return fuzzy_label

    if normalized_value:
        return next((pair for pair in layout_pairs if normalized_value in _compact(pair.value)), None)

    return None


def _build_pages(prepared_pages: list[PreprocessedPage], selected_page_profiles: dict[int, str] | None = None) -> list[ProcessPageInfo]:
    return [
        ProcessPageInfo(
            page_number=page.page_number,
            image_base64=base64.b64encode(page.image_bytes).decode("ascii"),
            width=page.width,
            height=page.height,
            orientation=page.orientation,
            quality_score=page.quality_score,
            blur_score=page.blur_score,
            glare_score=page.glare_score,
            crop_ratio=page.crop_ratio,
            document_coverage=page.document_coverage,
            edge_confidence=page.edge_confidence,
            skew_angle=page.skew_angle,
            skew_applied=page.skew_applied,
            perspective_applied=page.perspective_applied,
            capture_conditions=page.capture_conditions,
            rescue_profiles=page.rescue_profiles,
            selected_ocr_profile=(selected_page_profiles or {}).get(page.page_number),
            corners=page.corners,
            has_embedded_text=page.has_embedded_text,
        )
        for page in prepared_pages
    ]


def _should_escalate_to_structured(normalized: NormalizedDocument, document_family: str) -> bool:
    severities = [issue.severity for issue in normalized.issues]
    threshold = 0.82 if document_family in {"identity", "passport"} else 0.79 if document_family == "driver_license" else 0.78
    medium_or_higher = sum(1 for severity in severities if severity in {"medium", "high"})
    return normalized.global_confidence < threshold or "high" in severities or medium_or_higher >= 2


def _should_use_structured_candidate(heuristic_candidate: NormalizedDocument, structured_candidate: NormalizedDocument) -> bool:
    heuristic_score = heuristic_candidate.global_confidence - (0.04 * len(heuristic_candidate.issues))
    structured_score = structured_candidate.global_confidence - (0.04 * len(structured_candidate.issues))
    heuristic_has_high = any(issue.severity == "high" for issue in heuristic_candidate.issues)
    structured_has_high = any(issue.severity == "high" for issue in structured_candidate.issues)

    if structured_candidate.global_confidence <= 0.05 and heuristic_candidate.global_confidence >= 0.4:
        return False
    if heuristic_candidate.global_confidence >= 0.8 and not heuristic_has_high and structured_candidate.global_confidence < heuristic_candidate.global_confidence + 0.06:
        return False
    if structured_has_high and not heuristic_has_high:
        return False
    if structured_candidate.global_confidence >= heuristic_candidate.global_confidence + 0.05:
        return True
    if structured_score > heuristic_score and len(structured_candidate.issues) <= len(heuristic_candidate.issues):
        return True
    return False


def _average_page_quality(prepared_pages: list[PreprocessedPage]) -> float:
    if not prepared_pages:
        return 0.0
    return sum(page.quality_score for page in prepared_pages) / len(prepared_pages)


def _average_field_agreement(field_signals: dict[str, FieldDecisionSignal]) -> float | None:
    populated = [signal.agreement_ratio for signal in field_signals.values() if signal.candidate_count > 0]
    if not populated:
        return None
    return round(sum(populated) / len(populated), 3)


def _build_global_confidence_details(
    *,
    final_confidence: float,
    normalized_confidence: float,
    issues: list[ValidationIssue],
    prepared_pages: list[PreprocessedPage],
    ocr_runs: list[OCRRunInfo],
    field_signals: dict[str, FieldDecisionSignal],
    integrity_assessment: IntegrityAssessment | None,
) -> ConfidenceDetails:
    selected_run = next((run for run in ocr_runs if run.selected), None)
    ocr_confidence = selected_run.average_confidence if selected_run and selected_run.average_confidence is not None else None
    quality_score = round(_average_page_quality(prepared_pages), 3) if prepared_pages else None
    consensus_confidence = _average_field_agreement(field_signals)
    issue_penalty = min(0.35, sum(0.09 if issue.severity == "high" else 0.045 if issue.severity == "medium" else 0.02 for issue in issues))
    validation_confidence = round(max(0.05, min(0.99, 0.96 - issue_penalty)), 3)
    integrity_score = integrity_assessment.score if integrity_assessment is not None else None
    reasons: list[str] = []

    if quality_score is not None:
        reasons.append(f"quality={quality_score:.2f}")
    if ocr_confidence is not None:
        reasons.append(f"ocr={ocr_confidence:.2f}")
    if consensus_confidence is not None:
        reasons.append(f"consensus={consensus_confidence:.2f}")
    if integrity_score is not None:
        reasons.append(f"integrity={integrity_score:.2f}")
    if issue_penalty > 0:
        reasons.append(f"validation_penalty={issue_penalty:.2f}")

    return ConfidenceDetails(
        final=round(final_confidence, 3),
        ocr_confidence=ocr_confidence,
        normalization_confidence=round(normalized_confidence, 3),
        validation_confidence=validation_confidence,
        quality_score=quality_score,
        consensus_confidence=consensus_confidence,
        integrity_score=integrity_score,
        issue_penalty=round(issue_penalty, 3),
        reasons=reasons,
    )


def _count_report_section_rows(report_sections: list[ReportSection], section_id: str) -> int:
    section = next((entry for entry in report_sections if entry.id == section_id), None)
    return len(section.rows or []) if section else 0


def _certificate_support_snapshot(normalized: NormalizedDocument) -> tuple[int, int, int]:
    values = _flatten_report_section_values(normalized.report_sections)
    key_fields = (
        normalized.holder_name or values.get("titular") or values.get("nombre-completo"),
        values.get("rut"),
        values.get("numero-de-certificado"),
        values.get("fecha-de-emision"),
        values.get("cuenta"),
        normalized.issuer or values.get("emisor"),
    )
    populated_key_fields = sum(1 for value in key_fields if not _is_missing_value(value))
    contribution_rows = _count_report_section_rows(normalized.report_sections, "movements")
    blocking_issues = sum(1 for issue in normalized.issues if issue.severity in {"medium", "high"})
    return populated_key_fields, contribution_rows, blocking_issues


def _looks_like_previsional_certificate(text: str) -> bool:
    normalized = text.upper()
    return "AFP" in normalized and (
        "COTIZACIONES" in normalized or "CUENTA DE CAPITALIZACION" in normalized or "NUMERO DE CERTIFICADO" in normalized
    )


def _should_probe_visual_ocr_for_embedded_pdf(text: str, classification, prepared_pages: list[PreprocessedPage]) -> bool:
    if not feature_enabled("certificate_pdf_visual_support"):
        return False
    if not prepared_pages:
        return False
    if getattr(classification, "document_family", None) != "certificate":
        return False
    return _looks_like_previsional_certificate(text)


def _should_try_visual_support_for_certificate(normalized: NormalizedDocument, extraction_source: str, pack_id: str | None) -> bool:
    if not feature_enabled("certificate_pdf_visual_support"):
        return False
    if extraction_source != "pdf-embedded-text":
        return False
    if normalized.document_family != "certificate":
        return False
    if pack_id != "certificate-cl-previsional" and not _looks_like_previsional_certificate("\n".join(section.body or "" for section in normalized.report_sections if section.body)):
        return False

    key_fields, contribution_rows, blocking_issues = _certificate_support_snapshot(normalized)
    return key_fields < 6 or contribution_rows < 6 or blocking_issues > 0 or normalized.global_confidence < 0.9


def _should_use_visual_certificate_candidate(base_candidate: NormalizedDocument, visual_candidate: NormalizedDocument) -> bool:
    base_keys, base_rows, base_blockers = _certificate_support_snapshot(base_candidate)
    visual_keys, visual_rows, visual_blockers = _certificate_support_snapshot(visual_candidate)

    if visual_keys > base_keys:
        return True
    if visual_keys == base_keys and visual_rows >= base_rows + 2:
        return True
    if visual_blockers < base_blockers and visual_candidate.global_confidence >= base_candidate.global_confidence - 0.02:
        return True
    if visual_candidate.global_confidence >= base_candidate.global_confidence + 0.05:
        return True
    return False


def _recalibrate_normalized_confidence(
    normalized: NormalizedDocument,
    pack: DocumentPack | None,
    field_signals: dict[str, FieldDecisionSignal],
    prepared_pages: list[PreprocessedPage],
    cross_side_signal: CrossSideConsistencySignal | None,
) -> NormalizedDocument:
    values = _flatten_report_section_values(normalized.report_sections)
    critical_fields = [field for field in (pack.expected_fields if pack else ()) if field.critical]
    critical_present = 0
    agreement_values: list[float] = []
    multi_source_critical = 0

    for field in critical_fields:
        value = _resolve_pack_field_value(values, pack, field)
        if not _is_missing_value(value):
            critical_present += 1
        signal = field_signals.get(field.field_key)
        if signal and signal.candidate_count > 0:
            agreement_values.append(signal.agreement_ratio)
        if signal and signal.agreement_ratio >= 0.67 and len(signal.supporting_engines) >= 2:
            multi_source_critical += 1

    recalibrated = normalized.global_confidence
    if critical_fields:
        critical_ratio = critical_present / len(critical_fields)
        recalibrated = max(recalibrated, 0.4 + (critical_ratio * 0.32))

    if agreement_values:
        minimum_agreement = min(agreement_values)
        average_agreement = sum(agreement_values) / len(agreement_values)
        if minimum_agreement >= 0.95:
            recalibrated += 0.05
        elif minimum_agreement >= 0.85:
            recalibrated += 0.03
        elif average_agreement >= 0.75:
            recalibrated += 0.015

    page_quality = _average_page_quality(prepared_pages)
    if page_quality >= 0.82:
        recalibrated += 0.03
    elif page_quality >= 0.72:
        recalibrated += 0.015
    elif page_quality and page_quality < 0.45:
        recalibrated -= 0.02

    if critical_fields and multi_source_critical == len(critical_fields):
        recalibrated += 0.03

    run_field = next((field for field in critical_fields if field.field_key == "run"), None)
    run_value = _resolve_pack_field_value(values, pack, run_field) if run_field else None
    mrz_field = next((field for field in (pack.expected_fields if pack else ()) if field.field_key == "mrz"), None)
    mrz_value = _resolve_pack_field_value(values, pack, mrz_field) if mrz_field else values.get("mrz")

    if pack and pack.country == "CL" and validate_chile_run_checksum(run_value):
        recalibrated += 0.06
    if validate_mrz_check_digits(mrz_value):
        recalibrated += 0.08
    if cross_side_signal and cross_side_signal.identifier_match is True:
        recalibrated += 0.03

    normalized.global_confidence = round(max(0.05, min(recalibrated, 0.99)), 3)
    normalized.assumptions = [
        *normalized.assumptions,
        (
            "Confidence recalibrada por evidencia operativa "
            f"(quality {page_quality:.2f}, critical_fields {critical_present}/{len(critical_fields) if critical_fields else 0}, "
            f"agreement {min(agreement_values):.2f} minimo)."
            if agreement_values
            else (
                "Confidence recalibrada por evidencia operativa "
                f"(quality {page_quality:.2f}, critical_fields {critical_present}/{len(critical_fields) if critical_fields else 0})."
            )
        ),
    ]
    return normalized


def _should_try_visual_fallback(primary_engine_name: str, visual_text: str, prepared_pages: list[PreprocessedPage]) -> bool:
    if os.getenv("OCR_ENABLE_VISUAL_FALLBACK", "true").lower() == "false":
        return False

    fallback_engine = os.getenv("OCR_PREMIUM_FALLBACK_ENGINE", "google-documentai").strip().lower()
    if not fallback_engine or fallback_engine == primary_engine_name:
        return False

    if not prepared_pages:
        return False

    if not visual_text.strip():
        return True

    return _average_page_quality(prepared_pages) < 0.72


def _should_replace_with_fallback(
    primary_visual_ocr,
    fallback_visual_ocr,
    requested_family: str,
    requested_country: str,
) -> bool:
    if not fallback_visual_ocr or not fallback_visual_ocr.text:
        return False
    if not primary_visual_ocr or not primary_visual_ocr.text:
        return True

    primary_classification = classify_document(primary_visual_ocr.text, requested_family, requested_country)
    fallback_classification = classify_document(fallback_visual_ocr.text, requested_family, requested_country)

    if fallback_classification.supported and not primary_classification.supported:
        return True
    if fallback_classification.confidence >= primary_classification.confidence + 0.08:
        return True
    if len(fallback_visual_ocr.text) > len(primary_visual_ocr.text) * 1.2 and fallback_classification.confidence >= primary_classification.confidence:
        return True
    return False


def _build_layout_sections(layout_extraction: LayoutExtractionResult) -> list[ReportSection]:
    sections: list[ReportSection] = []

    if layout_extraction.key_value_pairs:
        sections.append(
            ReportSection(
                id="layout-kv",
                title="Layout · pares detectados",
                variant="table",
                columns=["Campo", "Valor", "Pagina"],
                rows=[
                    [pair.label, pair.value, str(pair.page_number)]
                    for pair in layout_extraction.key_value_pairs[:20]
                ],
                note="Pares detectados automaticamente desde el layout OCR como apoyo de provenance y debugging.",
            )
        )

    if layout_extraction.table_candidate_rows:
        sections.append(
            ReportSection(
                id="layout-table-candidates",
                title="Layout · filas candidatas a tabla",
                variant="table",
                columns=["Fila candidata"],
                rows=[[row] for row in layout_extraction.table_candidate_rows[:20]],
                note="Filas con estructura numerica/temporal detectadas por heuristica de layout.",
            )
        )

    return sections


def _trace_stage(
    processing_trace: list[ProcessingTraceEntry],
    *,
    stage: str,
    started_at_iso: str,
    started_counter: float,
    summary: str,
    status: str = "completed",
) -> None:
    finished_at_iso = datetime.now(timezone.utc).isoformat()
    processing_trace.append(
        ProcessingTraceEntry(
            stage=stage,
            status=status,
            started_at=started_at_iso,
            finished_at=finished_at_iso,
            duration_ms=round((perf_counter() - started_counter) * 1000, 3),
            summary=summary,
        )
    )


def _average_token_confidence(tokens: list[OCRToken]) -> float | None:
    if not tokens:
        return None
    return sum(token.confidence for token in tokens) / len(tokens)


def _build_ocr_run_pages(run: VisualOCRRunRecord) -> list[OCRRunPageInfo]:
    if not run.result:
        return []

    pages: list[OCRRunPageInfo] = []
    page_texts = run.result.page_texts or ([] if not run.result.text else [run.result.text])
    for page_number, page_text in enumerate(page_texts, start=1):
        page_tokens = [token for token in run.result.tokens if token.page_number == page_number]
        pages.append(
            OCRRunPageInfo(
                page_number=page_number,
                text=page_text,
                token_count=len(page_tokens),
                average_confidence=_average_token_confidence(page_tokens),
                rescue_profile=run.page_profiles[page_number - 1] if page_number - 1 < len(run.page_profiles) else run.preprocess_profile,
            )
        )
    return pages


def _build_ocr_runs(runs: list[VisualOCRRunRecord], selected_visual_engine: str | None) -> list[OCRRunInfo]:
    details: list[OCRRunInfo] = []
    for run in runs:
        result = run.result
        details.append(
            OCRRunInfo(
                engine=run.engine_name,
                source=run.source,
                success=run.success,
                selected=bool(selected_visual_engine and run.source == selected_visual_engine),
                score=run.score,
                page_count=result.page_count if result else 0,
                text=result.text if result else "",
                average_confidence=run.average_confidence,
                classification_family=run.classification.document_family if run.classification else None,
                classification_country=run.classification.country if run.classification else None,
                classification_confidence=run.classification.confidence if run.classification else None,
                supported_classification=run.classification.supported if run.classification else False,
                preprocess_profile=run.preprocess_profile,
                assumptions=[*(result.assumptions if result else []), *([f"error: {run.error}"] if run.error else [])],
                pages=_build_ocr_run_pages(run),
                tokens=[
                    OCRTokenInfo(text=token.text, confidence=token.confidence, bbox=token.bbox, page_number=token.page_number)
                    for token in (result.tokens if result else [])
                ],
                key_value_pairs=[
                    LayoutKeyValueCandidate(
                        label=pair.label,
                        value=pair.value,
                        page_number=pair.page_number,
                        raw_line=pair.raw_line,
                    )
                    for pair in run.layout.key_value_pairs
                ],
                table_candidate_rows=run.layout.table_candidate_rows,
            )
        )
    return details


def _build_ocr_ensemble_sections(ocr_runs: list[OCRRunInfo]) -> list[ReportSection]:
    if not ocr_runs:
        return []

    return [
        ReportSection(
            id="debug-ocr-ensemble",
            title="OCR ensemble",
            variant="table",
            columns=["Engine", "Profile", "Selected", "Classification", "Supported", "Score", "Tokens", "Confidence"],
            rows=[
                [
                    run.source,
                    run.preprocess_profile,
                    "YES" if run.selected else "NO",
                    f"{run.classification_family or '-'} / {run.classification_country or '-'}",
                    "YES" if run.supported_classification else "NO",
                    f"{run.score:.3f}",
                    str(len(run.tokens)),
                    f"{run.average_confidence:.2f}" if run.average_confidence is not None else "-",
                ]
                for run in ocr_runs
            ],
            note="Resumen de engines OCR ejecutados, score de seleccion y evidencia conservada por documento.",
        )
    ]


def _should_use_rescue_profiles(prepared_pages: list[PreprocessedPage]) -> bool:
    if not prepared_pages:
        return False
    average_quality = sum(page.quality_score for page in prepared_pages) / len(prepared_pages)
    return average_quality < 0.86 or any(page.blur_score >= 0.25 or page.glare_score >= 0.24 or page.rescue_profiles for page in prepared_pages)


def _premium_routing_mode() -> str:
    mode = (os.getenv("OCR_PREMIUM_ROUTING_MODE", "adaptive") or "adaptive").strip().lower()
    return mode if mode in {"adaptive", "force", "off"} else "adaptive"


def _split_engine_names(engine_names: list[str]) -> tuple[list[str], list[str]]:
    local = [engine for engine in engine_names if engine in DEFAULT_LOCAL_ENGINES]
    premium = [engine for engine in engine_names if engine not in DEFAULT_LOCAL_ENGINES]
    return local or ["rapidocr"], premium


def _should_accept_local_run(selected_run: VisualOCRRunRecord | None, prepared_pages: list[PreprocessedPage], premium_mode: str) -> bool:
    if premium_mode == "force":
        return False
    if selected_run is None or not selected_run.success or selected_run.result is None:
        return premium_mode == "off"

    classification = selected_run.classification
    average_quality = sum(page.quality_score for page in prepared_pages) / len(prepared_pages) if prepared_pages else 0.0
    severe_capture = any(
        page.blur_score >= 0.32 or page.glare_score >= 0.34 or "perspective" in page.capture_conditions or "cropped" in page.capture_conditions
        for page in prepared_pages
    )

    if premium_mode == "off":
        return True
    if classification and classification.document_family in {"driver_license", "passport", "identity"} and selected_run.score >= 0.65 and average_quality >= 0.88:
        return True
    if classification and classification.supported and selected_run.score >= 0.73 and average_quality >= 0.72:
        return True
    if classification and classification.document_family in {"driver_license", "passport"} and selected_run.score >= 0.68 and not severe_capture:
        return True
    if selected_run.average_confidence is not None and selected_run.average_confidence >= 0.82 and not severe_capture:
        return True
    return False


def _variant_priority(variant_sets: list[OCRVariantSet]) -> list[OCRVariantSet]:
    severe_capture = any(variant.average_quality < 0.62 for variant in variant_sets)
    preferred_order = {
        "original": 0,
        "aggressive_rescue": 1 if severe_capture else 6,
        "adaptive_binarize": 2 if severe_capture else 3,
        "clahe": 3 if severe_capture else 2,
        "denoise_sharpen": 4 if severe_capture else 4,
        "denoise": 5 if severe_capture else 5,
        "deglare": 6 if severe_capture else 1,
        "shadow_boost": 7 if severe_capture else 2,
        "gray_contrast": 8,
        "sharpen": 9,
    }
    prioritized = sorted(
        variant_sets,
        key=lambda variant: (
            preferred_order.get(variant.profile, 10),
            variant.profile,
        ),
    )
    return prioritized[:2]


def _select_best_visual_run(runs: list[VisualOCRRunRecord]) -> VisualOCRRunRecord | None:
    selected_run = max(
        runs,
        key=lambda run: (
            run.score,
            run.success,
            len(run.result.tokens) if run.result else 0,
            len(run.result.text) if run.result else 0,
            1 if run.preprocess_profile == "original" else 0,
        ),
        default=None,
    )
    if selected_run and selected_run.score <= 0:
        return None
    return selected_run


def _run_visual_ocr_with_rescue(
    prepared_pages: list[PreprocessedPage],
    rendered_pages: list[bytes],
    requested_engine: str | None,
    requested_family: str,
    requested_country: str,
    ensemble_mode: str | None,
    ensemble_engines: str | None,
) -> VisualOCREnsembleResult:
    variant_sets: list[OCRVariantSet] = build_ocr_variant_sets(prepared_pages) if _should_use_rescue_profiles(prepared_pages) else []
    if not variant_sets:
        variant_sets = [
            OCRVariantSet(
                profile="original",
                images=rendered_pages,
                page_count=len(rendered_pages),
                average_quality=0.0,
                assumptions=[],
                page_profiles=["original" for _ in rendered_pages],
            )
        ]

    premium_mode = _premium_routing_mode()
    _, configured_engine_names = resolve_visual_ocr_engine_names(requested_engine, ensemble_mode=ensemble_mode, ensemble_engines=ensemble_engines)
    local_engines, premium_engines = _split_engine_names(configured_engine_names)
    prioritized_variants = _variant_priority(variant_sets)

    aggregated_runs: list[VisualOCRRunRecord] = []
    local_runs: list[VisualOCRRunRecord] = []
    aggregated_assumptions: list[str] = []
    effective_mode = "single"

    for variant_set in prioritized_variants:
        local_result = run_visual_ocr_ensemble(
            variant_set.images,
            local_engines[0] if len(local_engines) == 1 else "auto",
            requested_family,
            requested_country,
            ensemble_mode="single" if len(local_engines) <= 1 else "always",
            ensemble_engines=",".join(local_engines),
            preprocess_profile=variant_set.profile,
            page_profiles=variant_set.page_profiles,
        )
        aggregated_runs.extend(local_result.runs)
        local_runs.extend(local_result.runs)
        aggregated_assumptions.extend([*variant_set.assumptions, *local_result.assumptions])
        selected_local = local_result.selected_run
        if _should_accept_local_run(selected_local, prepared_pages, premium_mode) or not premium_engines:
            selected_run = _select_best_visual_run(aggregated_runs)
            if len(prioritized_variants) > 1:
                aggregated_assumptions.insert(0, f"Se evaluaron perfiles de rescate OCR: {', '.join(variant.profile for variant in prioritized_variants)}.")
            aggregated_assumptions.append("Se aplico routing adaptativo: el OCR local fue suficiente y se omitieron motores premium.")
            return VisualOCREnsembleResult(
                mode="single" if len(local_engines) <= 1 else "ensemble",
                runs=aggregated_runs,
                selected_run=selected_run,
                assumptions=list(dict.fromkeys(aggregated_assumptions)),
            )

    best_local = _select_best_visual_run(local_runs)
    premium_variant = prioritized_variants[0]
    if best_local is not None:
        matched_variant = next((variant for variant in prioritized_variants if variant.profile == best_local.preprocess_profile), None)
        if matched_variant is not None:
            premium_variant = matched_variant

    premium_result = run_visual_ocr_ensemble(
        premium_variant.images,
        premium_engines[0] if len(premium_engines) == 1 else "auto",
        requested_family,
        requested_country,
        ensemble_mode="single" if len(premium_engines) <= 1 else "always",
        ensemble_engines=",".join(premium_engines),
        preprocess_profile=premium_variant.profile,
        page_profiles=premium_variant.page_profiles,
    )
    aggregated_runs.extend(premium_result.runs)
    aggregated_assumptions.extend(premium_result.assumptions)
    if len(prioritized_variants) > 1 and premium_variant.profile != prioritized_variants[0].profile:
        aggregated_assumptions.append(f"El routing premium se ejecuto sobre el mejor perfil local detectado: {premium_variant.profile}.")
    if premium_result.mode == "ensemble" or len(local_engines) > 1:
        effective_mode = "ensemble"

    selected_run = _select_best_visual_run(aggregated_runs)

    if len(prioritized_variants) > 1:
        aggregated_assumptions.insert(0, f"Se evaluaron perfiles de rescate OCR: {', '.join(variant.profile for variant in prioritized_variants)}.")

    return VisualOCREnsembleResult(
        mode=effective_mode,
        runs=aggregated_runs,
        selected_run=selected_run,
        assumptions=list(dict.fromkeys(aggregated_assumptions)),
    )


def _execute_visual_ocr_stage(
    *,
    prepared_pages: list[PreprocessedPage],
    rendered_pages: list[bytes],
    ocr_visual_engine: str | None,
    requested_family: str,
    requested_country: str,
    ocr_ensemble_mode: str | None,
    ocr_ensemble_engines: str | None,
    processing_trace: list[ProcessingTraceEntry],
    stage: str = "ocr_ensemble",
    summary_prefix: str | None = None,
    support_only_local: bool = False,
) -> tuple[VisualOCRResult | None, str, list[OCRToken], str | None, dict[int, str], str, list[str], list[OCRRunInfo]]:
    ocr_started_at = datetime.now(timezone.utc).isoformat()
    ocr_started_counter = perf_counter()
    runtime_ensemble_mode = ocr_ensemble_mode
    runtime_ensemble_engines = ocr_ensemble_engines
    if support_only_local:
        _, configured_engine_names = resolve_visual_ocr_engine_names(ocr_visual_engine, ensemble_mode=ocr_ensemble_mode, ensemble_engines=ocr_ensemble_engines)
        local_engines, _ = _split_engine_names(configured_engine_names)
        runtime_ensemble_mode = "single" if len(local_engines) <= 1 else "always"
        runtime_ensemble_engines = ",".join(local_engines)
    visual_ensemble = _run_visual_ocr_with_rescue(
        prepared_pages,
        rendered_pages,
        ocr_visual_engine,
        requested_family,
        requested_country,
        runtime_ensemble_mode,
        runtime_ensemble_engines,
    )
    ensemble_mode = visual_ensemble.mode
    visual_assumptions = [*visual_ensemble.assumptions]
    visual_ocr: VisualOCRResult | None = None
    visual_text = ""
    visual_tokens: list[OCRToken] = []
    selected_visual_engine: str | None = None
    selected_page_profiles: dict[int, str] = {}

    if visual_ensemble.selected_run and visual_ensemble.selected_run.result:
        visual_ocr = visual_ensemble.selected_run.result
        visual_text = visual_ocr.text
        visual_tokens = visual_ocr.tokens
        selected_visual_engine = visual_ensemble.selected_run.source
        selected_page_profiles = {
            index + 1: profile
            for index, profile in enumerate(
                visual_ensemble.selected_run.page_profiles or [visual_ensemble.selected_run.preprocess_profile] * max(1, visual_ocr.page_count)
            )
        }
        visual_assumptions = [*visual_assumptions, *visual_ocr.assumptions]

    ocr_runs = _build_ocr_runs(visual_ensemble.runs, selected_visual_engine)
    trace_summary = (
        f"{summary_prefix + ' ' if summary_prefix else ''}OCR ensemble {visual_ensemble.mode} ejecutado con {len(visual_ensemble.runs)} run(s); "
        f"seleccionado {selected_visual_engine or 'none'}; perfiles pagina {selected_page_profiles or {}}."
    )
    _trace_stage(
        processing_trace,
        stage=stage,
        started_at_iso=ocr_started_at,
        started_counter=ocr_started_counter,
        summary=trace_summary,
        status="completed" if selected_visual_engine else "degraded",
    )
    return visual_ocr, visual_text, visual_tokens, selected_visual_engine, selected_page_profiles, ensemble_mode, visual_assumptions, ocr_runs


def _heuristic_normalize(
    request: NormalizationRequest,
    source_text: str,
    supplemental_fields: dict[str, str] | None = None,
) -> NormalizedDocument:
    return normalize_text_with_heuristics(
        request.document_family,
        request.country,
        request.filename,
        source_text,
        request.assumptions or [],
        variant=request.variant,
        pack_id=request.pack_id,
        document_side=request.document_side,
        supplemental_fields=supplemental_fields,
    )


def _page_numbers_for_side(page_analysis, side: str) -> list[int]:
    return [result.page_number for result in page_analysis.pages if result.classification.document_side == side]


def _join_page_texts(page_texts: list[str], page_numbers: list[int]) -> str:
    return "\n".join(page_texts[page_number - 1] for page_number in page_numbers if 0 < page_number <= len(page_texts))


def _prepared_pages_for_numbers(prepared_pages: list[PreprocessedPage], page_numbers: list[int]) -> list[PreprocessedPage]:
    page_number_set = set(page_numbers)
    return [page for page in prepared_pages if page.page_number in page_number_set]


def _pick_non_missing(*values: str | None) -> str | None:
    return next((value for value in values if not _is_missing_value(value)), None)


def _looks_suspicious_identity_holder(value: str | None) -> bool:
    if not value or is_placeholder_name(value):
        return True
    parts = [part for part in value.split() if part]
    if len(parts) >= 2 and len(set(parts)) == 1:
        return True
    normalized = _compact(value)
    return normalized in {"nombretitular", "titular"}


def _build_identity_cross_side_normalized(
    *,
    filename: str,
    page_analysis,
    page_texts: list[str],
    prepared_pages: list[PreprocessedPage],
    cross_side_signal: CrossSideConsistencySignal | None,
    assumptions: list[str],
) -> NormalizedDocument | None:
    front_pages = _page_numbers_for_side(page_analysis, "front")
    back_pages = _page_numbers_for_side(page_analysis, "back")
    if not front_pages or not back_pages:
        return None

    front_text = _join_page_texts(page_texts, front_pages)
    back_text = _join_page_texts(page_texts, back_pages)
    if not front_text.strip() or not back_text.strip():
        return None

    front_request = NormalizationRequest(
        document_family="identity",
        country="CL",
        filename=filename,
        variant="identity-cl-front-text",
        pack_id="identity-cl-front",
        document_side="front",
        assumptions=[*assumptions, "Se normalizo el frente de la cedula por separado antes de fusionar frente+dorso."],
    )
    back_request = NormalizationRequest(
        document_family="identity",
        country="CL",
        filename=filename,
        variant="identity-cl-back-text",
        pack_id="identity-cl-back",
        document_side="back",
        assumptions=[*assumptions, "Se normalizo el dorso de la cedula por separado antes de fusionar frente+dorso."],
    )

    front_supplemental = extract_supplemental_fields(
        _prepared_pages_for_numbers(prepared_pages, front_pages),
        document_family="identity",
        country="CL",
        pack_id="identity-cl-front",
        document_side="front",
    )
    front_normalized = _heuristic_normalize(front_request, front_text, supplemental_fields=front_supplemental)
    back_normalized = _heuristic_normalize(back_request, back_text)

    front_values = _flatten_report_section_values(front_normalized.report_sections)
    back_values = _flatten_report_section_values(back_normalized.report_sections)
    back_fallback = parse_identity_card_td1_fallback(back_text)

    holder_name = derive_identity_holder_name(front_values, front_normalized.holder_name)
    if _looks_suspicious_identity_holder(holder_name):
        holder_name = derive_identity_holder_name(back_values, back_normalized.holder_name)
    if _looks_suspicious_identity_holder(holder_name):
        holder_name = back_fallback.get("holder_name")
    first_names = _pick_non_missing(front_values.get("nombres"), back_values.get("nombres"))
    last_names = _pick_non_missing(front_values.get("apellidos"), back_values.get("apellidos"))
    if not first_names:
        first_names = back_fallback.get("first_names")
    if not last_names:
        last_names = back_fallback.get("last_names")
    if _looks_suspicious_identity_holder(holder_name) and first_names and last_names:
        holder_name = f"{first_names} {last_names}"

    document_number = canonicalize_identity_document_number(
        "CL",
        _pick_non_missing(
            front_values.get("numero-de-documento"),
            front_values.get("numero"),
            back_values.get("numero-de-documento"),
            back_values.get("numero"),
            back_fallback.get("document_number"),
            cross_side_signal.front_identifier if cross_side_signal and cross_side_signal.front_identifier and "." in cross_side_signal.front_identifier else None,
            cross_side_signal.back_identifier if cross_side_signal and cross_side_signal.back_identifier and "." in cross_side_signal.back_identifier else None,
        ),
    )
    run_value = canonicalize_chile_run(
        _pick_non_missing(
            front_values.get("run"),
            back_values.get("run"),
            back_fallback.get("run"),
            cross_side_signal.front_identifier if cross_side_signal and "-" in (cross_side_signal.front_identifier or "") else None,
            cross_side_signal.back_identifier if cross_side_signal and "-" in (cross_side_signal.back_identifier or "") else None,
        )
    )
    birth_date = normalize_date_value(_pick_non_missing(back_fallback.get("birth_date"), front_values.get("fecha-de-nacimiento"), back_values.get("fecha-de-nacimiento")))
    issue_date = normalize_date_value(_pick_non_missing(front_values.get("fecha-de-emision"), back_values.get("fecha-de-emision")))
    expiry_date = normalize_date_value(_pick_non_missing(back_fallback.get("expiry_date"), front_values.get("fecha-de-vencimiento"), back_values.get("fecha-de-vencimiento")))
    nationality = _pick_non_missing(front_values.get("nacionalidad"), back_values.get("nacionalidad"))
    sex = _pick_non_missing(back_fallback.get("sex"), front_values.get("sexo"), back_values.get("sexo"))
    issuer = _pick_non_missing(front_normalized.issuer, front_values.get("emisor"), back_normalized.issuer)
    mrz_value = _pick_non_missing(front_values.get("mrz"), back_values.get("mrz"), back_fallback.get("mrz"))
    birth_place = _pick_non_missing(back_fallback.get("birth_place"), back_values.get("lugar-de-nacimiento"), back_values.get("nacio-en"), front_values.get("lugar-de-nacimiento"))
    address = _pick_non_missing(back_values.get("domicilio"), back_values.get("direccion"))
    commune = _pick_non_missing(back_values.get("comuna"))
    profession = _pick_non_missing(back_values.get("profesion"))
    electoral_circ = _pick_non_missing(back_values.get("circunscripcion"))

    back_field_count = sum(
        1
        for value in (birth_place, address, commune, profession, electoral_circ)
        if not _is_missing_value(value)
    )
    merged_confidence = round(
        min(
            0.99,
            max(front_normalized.global_confidence, back_normalized.global_confidence)
            + (0.02 if cross_side_signal and cross_side_signal.identifier_match is True else 0.0),
        ),
        3,
    )

    report_sections = [
        ReportSection(
            id="summary",
            title="Resumen",
            variant="pairs",
            rows=[
                ["Documento", "DOCUMENTO DE IDENTIDAD"],
                ["Archivo", filename],
                ["Pais", "CL"],
                ["Lado", "front+back"],
                ["Titular", holder_name or "NO DETECTADO"],
                ["Numero", document_number or "NO DETECTADO"],
                ["RUN", run_value or "NO DETECTADO"],
                ["Emisor", issuer or "NO DETECTADO"],
            ],
        ),
        ReportSection(
            id="dates",
            title="Fechas",
            variant="table",
            columns=["Campo", "Valor"],
            rows=[
                ["Fecha de nacimiento", birth_date or "-"],
                ["Fecha de emision", issue_date or "-"],
                ["Fecha de vencimiento", expiry_date or "-"],
            ],
        ),
        ReportSection(
            id="identity",
            title="Identidad",
            variant="pairs",
            rows=[
                ["Nombre completo", holder_name or "NO DETECTADO"],
                ["Nombres", first_names or "NO DETECTADOS"],
                ["Apellidos", last_names or "NO DETECTADOS"],
                ["Numero de documento", document_number or "NO DETECTADO"],
                ["Nacionalidad", nationality or "NO DETECTADA"],
                ["Sexo", sex or "NO DETECTADO"],
                ["RUN", run_value or "NO DETECTADO"],
                ["MRZ", mrz_value or "NO DETECTADA"],
            ],
        ),
        ReportSection(
            id="reverse",
            title="Dorso / campos reversos",
            variant="pairs",
            rows=[
                ["Lugar de nacimiento", birth_place or "NO DETECTADO"],
                ["Domicilio", address or "NO DETECTADO"],
                ["Comuna", commune or "NO DETECTADA"],
                ["Profesion", profession or "NO DETECTADA"],
                ["Circunscripcion", electoral_circ or "NO DETECTADA"],
            ],
        ),
        ReportSection(
            id="human-summary",
            title="Resumen humano",
            variant="text",
            body="Frente y dorso de la cedula chilena normalizados por separado y fusionados en una unica vista para validacion cruzada.",
        ),
    ]

    return NormalizedDocument(
        document_family="identity",
        country="CL",
        variant="identity-cl-front-text",
        issuer=issuer,
        holder_name=holder_name,
        global_confidence=merged_confidence,
        assumptions=[
            *front_normalized.assumptions,
            *back_normalized.assumptions,
            "Se fusionaron frente y dorso usando normalizacion por lado para evitar mezclar campos entre paginas.",
            f"Se consolidaron {back_field_count} campo(s) de evidencia del dorso.",
        ],
        issues=[],
        report_sections=report_sections,
        human_summary="Cedula chilena frente+dorso fusionada con consistencia cross-side y campos reversos integrados.",
    )


def _flatten_report_section_values(report_sections: list[ReportSection]) -> dict[str, str]:
    values: dict[str, str] = {}
    for section in report_sections:
        if section.variant == "pairs" and section.rows:
            for row in section.rows:
                if not row:
                    continue
                values[_slugify(row[0])] = row[1] if len(row) > 1 else ""
        elif section.variant == "table" and section.columns and section.rows:
            if len(section.columns) == 2 and section.columns[0].lower() == "campo":
                for row in section.rows:
                    if not row:
                        continue
                    values[_slugify(row[0])] = row[1] if len(row) > 1 else ""
        elif section.variant == "text" and section.body:
            values[_slugify(section.title)] = section.body
    return values


def _resolve_pack_field_value(values: dict[str, str], pack: DocumentPack | None, field: PackFieldDefinition) -> str | None:
    candidate_keys = (field.field_key, *field.aliases)
    resolved: str | None = None
    for candidate_key in candidate_keys:
        resolved = values.get(_slugify(candidate_key))
        if resolved not in {None, "", "-", "NO DETECTADO", "NO DETECTADA", "NO DETECTADOS", "NO DETECTADAS"}:
            break

    if field.field_key == "holder_name":
        return derive_identity_holder_name(values, resolved)
    if field.field_key == "document_number":
        if resolved is None:
            for fallback_key in ("numero-de-identificacion", "numero-de-identidad", "dni", "cedula"):
                candidate_value = values.get(_slugify(fallback_key))
                if candidate_value not in {None, "", "-", "NO DETECTADO", "NO DETECTADA", "NO DETECTADOS", "NO DETECTADAS"}:
                    resolved = candidate_value
                    break
        if resolved is None:
            resolved = find_value_by_key_fragments(
                values,
                ("numero", "document"),
                ("numero", "identific"),
                ("nuip",),
                ("dni",),
                ("cedula",),
            )
        return canonicalize_identity_document_number(pack.country if pack else "", resolved)
    if field.field_key in {"birth_date", "issue_date", "expiry_date"}:
        return normalize_date_value(resolved)
    if field.field_key == "run":
        return canonicalize_chile_run(resolved)
    return resolved


def _build_rule_field_signals(
    report_sections: list[ReportSection],
    pack: DocumentPack | None,
    ocr_runs: list[OCRRunInfo],
) -> dict[str, FieldDecisionSignal]:
    if pack is None or not pack.expected_fields or not ocr_runs:
        return {}

    values = _flatten_report_section_values(report_sections)
    signals: dict[str, FieldDecisionSignal] = {}

    for field in pack.expected_fields:
        resolved_value = _resolve_pack_field_value(values, pack, field)
        candidates, consensus = _build_field_candidates(field.label, field.field_key, resolved_value, ocr_runs)
        if consensus is None:
            continue
        signals[field.field_key] = FieldDecisionSignal(
            agreement_ratio=consensus.agreement_ratio,
            disagreement=consensus.disagreement,
            candidate_count=consensus.candidate_count,
            supporting_engines=tuple(consensus.supporting_engines),
        )

    return signals


def _pack_field_slugs(field: PackFieldDefinition) -> set[str]:
    return {_slugify(value) for value in (field.label, field.field_key, *field.aliases)}


def _pack_field_update_slugs(field: PackFieldDefinition) -> set[str]:
    return {_slugify(value) for value in (field.label, field.field_key)}


def _update_pack_field_in_sections(report_sections: list[ReportSection], field: PackFieldDefinition, selected_value: str) -> list[ReportSection]:
    target_slugs = _pack_field_update_slugs(field)
    updated_sections: list[ReportSection] = []

    for section in report_sections:
        if section.variant == "pairs" and section.rows:
            updated_sections.append(
                ReportSection(
                    id=section.id,
                    title=section.title,
                    variant=section.variant,
                    columns=section.columns,
                    note=section.note,
                    body=section.body,
                    rows=[
                        [row[0], selected_value if _slugify(row[0]) in target_slugs and len(row) > 1 else (row[1] if len(row) > 1 else "")]
                        if len(row) > 1
                        else row
                        for row in section.rows
                    ],
                )
            )
            continue

        if section.variant == "table" and section.columns and section.rows and len(section.columns) == 2 and section.columns[0].lower() == "campo":
            updated_sections.append(
                ReportSection(
                    id=section.id,
                    title=section.title,
                    variant=section.variant,
                    columns=section.columns,
                    note=section.note,
                    body=section.body,
                    rows=[
                        [row[0], selected_value if _slugify(row[0]) in target_slugs and len(row) > 1 else (row[1] if len(row) > 1 else "")]
                        if len(row) > 1
                        else row
                        for row in section.rows
                    ],
                )
            )
            continue

        updated_sections.append(section)

    return updated_sections


def _apply_pack_field_adjudication(
    normalized: NormalizedDocument,
    pack: DocumentPack | None,
    ocr_runs: list[OCRRunInfo],
    adjudication_mode_override: str | None = None,
) -> tuple[NormalizedDocument, dict[str, FieldAdjudicationResult]]:
    if pack is None or not should_adjudicate_pack(pack, adjudication_mode_override) or not ocr_runs:
        return normalized, {}

    report_sections = list(normalized.report_sections)
    values = _flatten_report_section_values(report_sections)
    adjudications: dict[str, FieldAdjudicationResult] = {}
    assumptions = [*normalized.assumptions]
    holder_name = normalized.holder_name

    for field in pack.expected_fields:
        current_value = _resolve_pack_field_value(values, pack, field)
        candidates, consensus = _build_field_candidates(field.label, field.field_key, current_value, ocr_runs)
        adjudication = adjudicate_field(
            field=field,
            current_value=current_value,
            candidates=candidates,
            consensus=consensus,
            mode_override=adjudication_mode_override,
        )
        adjudications[field.field_key] = adjudication

        if adjudication.abstained or not adjudication.selected_value:
            assumptions.append(f"Adjudicacion {field.field_key}: abstencion segura.")
            continue

        report_sections = _update_pack_field_in_sections(report_sections, field, adjudication.selected_value)
        values = _flatten_report_section_values(report_sections)
        assumptions.append(f"Adjudicacion {field.field_key}: {adjudication.selected_source or adjudication.method}.")
        if field.field_key == "holder_name":
            holder_name = adjudication.selected_value

    return (
        NormalizedDocument(
            document_family=normalized.document_family,
            country=normalized.country,
            variant=normalized.variant,
            issuer=normalized.issuer,
            holder_name=holder_name,
            global_confidence=normalized.global_confidence,
            assumptions=assumptions,
            issues=normalized.issues,
            report_sections=report_sections,
            human_summary=normalized.human_summary,
        ),
        adjudications,
    )


def _build_adjudication_sections(pack: DocumentPack | None, adjudications: dict[str, FieldAdjudicationResult]) -> list[ReportSection]:
    if pack is None or not adjudications:
        return []

    return [
        ReportSection(
            id="debug-field-adjudication",
            title="Field adjudication",
            variant="table",
            columns=["Field", "Method", "Abstained", "Value", "Source", "Confidence"],
            rows=[
                [
                    field.label,
                    adjudications.get(field.field_key, FieldAdjudicationResult()).method,
                    "YES" if adjudications.get(field.field_key, FieldAdjudicationResult()).abstained else "NO",
                    adjudications.get(field.field_key, FieldAdjudicationResult()).selected_value or "-",
                    adjudications.get(field.field_key, FieldAdjudicationResult()).selected_source or "-",
                    f"{(adjudications.get(field.field_key, FieldAdjudicationResult()).confidence or 0.0):.2f}",
                ]
                for field in pack.expected_fields
            ],
            note="Resultado de adjudicacion por campo usando candidatos OCR fusionados.",
        )
    ]


def _build_pack_quality_sections(pack: DocumentPack | None, field_signals: dict[str, FieldDecisionSignal]) -> list[ReportSection]:
    if pack is None or not pack.expected_fields:
        return []

    return [
        ReportSection(
            id="debug-pack-quality",
            title="Pack quality",
            variant="table",
            columns=["Field", "Required", "Critical", "Agreement", "Candidates", "Disagreement"],
            rows=[
                [
                    field.label,
                    "YES" if field.required else "NO",
                    "YES" if field.critical else "NO",
                    f"{field_signals.get(field.field_key, FieldDecisionSignal()).agreement_ratio:.2f}",
                    str(field_signals.get(field.field_key, FieldDecisionSignal()).candidate_count),
                    "YES" if field_signals.get(field.field_key, FieldDecisionSignal()).disagreement else "NO",
                ]
                for field in pack.expected_fields
            ],
            note="Cobertura del pack sobre campos esperados, con senales de acuerdo/desacuerdo entre motores.",
        )
    ]


def _build_cross_side_sections(cross_side_signal: CrossSideConsistencySignal | None) -> list[ReportSection]:
    if cross_side_signal is None:
        return []

    return [
        ReportSection(
            id="debug-cross-side",
            title="Cross-side consistency",
            variant="table",
            columns=["Front", "Back", "Match"],
            rows=[
                [
                    cross_side_signal.front_identifier or "-",
                    cross_side_signal.back_identifier or "-",
                    "YES" if cross_side_signal.identifier_match else ("NO" if cross_side_signal.identifier_match is False else "UNKNOWN"),
                ]
            ],
            note="Comparacion de identificadores entre paginas clasificadas como frente y dorso.",
        )
    ]


def _build_split_sections(split_result: SplitDocumentResult) -> list[ReportSection]:
    if not split_result.segments:
        return []

    return [
        ReportSection(
            id="document-segments",
            title="Segmentos detectados",
            variant="table",
            columns=["Segmento", "Paginas", "Familia", "Pais", "Variante", "Lado", "Confidence"],
            rows=[
                [
                    segment.segment_id,
                    ", ".join(str(page) for page in segment.page_numbers),
                    segment.document_family,
                    segment.country,
                    segment.variant or "-",
                    segment.document_side or "-",
                    f"{segment.confidence:.2f}",
                ]
                for segment in split_result.segments
            ],
            note="Segmentacion automatica para PDFs/documentos mixtos basada en clasificacion por pagina.",
        )
    ]


def _value_type(value: str | None) -> str:
    if not value:
        return "text"
    if len(value) == 10 and value[4] in {"-", "/"} and value[7] in {"-", "/"}:
        return "date"
    if all(char.isdigit() or char in ",.-" for char in value):
        return "number"
    return "text"


def _link_issue_ids(label: str, field_name: str, issues: list[ValidationIssue]) -> list[str]:
    normalized_label = _slugify(label)
    normalized_field_name = _slugify(field_name)
    return [issue.id for issue in issues if _slugify(issue.field) in {normalized_label, normalized_field_name}]


def _match_page_text(value: str | None, run: OCRRunInfo) -> tuple[str, int] | None:
    normalized_value = _compact(value)
    if len(normalized_value) < 4:
        return None

    for page in run.pages:
        if normalized_value in _compact(page.text):
            return value or page.text, page.page_number
    return None


@lru_cache(maxsize=128)
def _derive_run_field_values(
    source: str,
    document_family: str | None,
    country: str | None,
    variant: str | None,
    pack_id: str | None,
    document_side: str | None,
    text: str,
) -> tuple[dict[str, str], str | None]:
    if not text.strip() or document_family not in {"identity", "certificate", "passport", "driver_license"} or not country:
        return {}, None

    normalized = normalize_text_with_heuristics(
        document_family,
        country,
        f"{source}.txt",
        text,
        assumptions=[],
        variant=variant,
        pack_id=pack_id,
        document_side=document_side,
    )
    return _flatten_report_section_values(normalized.report_sections), normalized.holder_name


def _resolve_run_heuristic_candidate(label: str, field_name: str, run: VisualOCRRunRecord | OCRRunInfo) -> str | None:
    result = getattr(run, "result", None)
    text = result.text if result else getattr(run, "text", "")
    classification = getattr(run, "classification", None)
    values, holder_name = _derive_run_field_values(
        getattr(run, "source"),
        classification.document_family if classification else getattr(run, "classification_family", None),
        classification.country if classification else getattr(run, "classification_country", None),
        classification.variant if classification else None,
        classification.pack_id if classification else None,
        classification.document_side if classification else None,
        text or "",
    )
    if not values and not holder_name:
        return None

    slug_field_name = _slugify(field_name)
    slug_label = _slugify(label)
    if slug_field_name in {"holder-name", "titular", "nombre-completo", "nombres", "apellidos", "apellido"} or slug_label in {"titular", "nombre-completo", "nombres", "apellidos"}:
        candidate = derive_identity_holder_name(values, holder_name)
        return None if is_placeholder_name(candidate) else candidate
    if slug_field_name in {"document-number", "numero-de-documento", "numero", "dni", "cedula", "numero-de-identificacion"}:
        country = classification.country if classification else getattr(run, "classification_country", "")
        raw_value = values.get("numero-de-documento") or values.get("numero-de-identificacion") or values.get("numero") or values.get("dni") or values.get("cedula")
        return canonicalize_identity_document_number(country or "", raw_value)
    if slug_field_name in {"birth-date", "fecha-de-nacimiento"}:
        return normalize_date_value(values.get("fecha-de-nacimiento"))
    if slug_field_name in {"issue-date", "fecha-de-emision", "fecha-de-expedicion"}:
        return normalize_date_value(values.get("fecha-de-emision") or values.get("fecha-de-expedicion"))
    if slug_field_name in {"expiry-date", "fecha-de-vencimiento", "fecha-de-expiracion", "fecha-de-caducidad"}:
        return normalize_date_value(values.get("fecha-de-vencimiento") or values.get("fecha-de-expiracion") or values.get("fecha-de-caducidad"))
    if slug_field_name == "run":
        return canonicalize_chile_run(values.get("run"))
    if slug_field_name == "mrz":
        candidate = values.get("mrz")
        return None if _is_missing_value(candidate) else candidate
    candidate = values.get(slug_field_name) or values.get(slug_label)
    return None if _is_missing_value(candidate) else candidate


def _layout_pair_bbox(pair: LayoutKeyValue | LayoutKeyValueCandidate | None) -> dict[str, float] | None:
    if pair is None or not hasattr(pair, "bbox"):
        return None
    bbox = getattr(pair, "bbox")
    if not bbox:
        return None
    return _bbox_from_polygon(bbox)


def _score_field_candidate(value: str | None, candidate_value: str | None, confidence: float | None, match_type: str) -> float:
    selected_compact = _compact(value)
    candidate_compact = _compact(candidate_value)
    if not candidate_compact:
        return 0.0

    score = 0.12
    if selected_compact and candidate_compact == selected_compact:
        score += 0.55
    elif selected_compact and (candidate_compact in selected_compact or selected_compact in candidate_compact):
        score += 0.36
    else:
        score += 0.18

    if confidence is not None:
        score += min(max(confidence, 0.0), 1.0) * 0.2

    if match_type == "layout-pair":
        score += 0.08
    elif match_type == "page-text":
        score += 0.04
    elif match_type == "run-heuristic":
        score += 0.1

    return round(min(score, 1.0), 3)


def _build_field_candidates(
    label: str,
    field_name: str,
    value: str | None,
    ocr_runs: list[OCRRunInfo],
) -> tuple[list[FieldCandidateResult], FieldConsensusResult | None]:
    successful_runs = [run for run in ocr_runs if run.success]
    candidates: list[FieldCandidateResult] = []

    for run in successful_runs:
        matched_token = _match_token(value, cast(Sequence[OCRToken | OCRTokenInfo], run.tokens))
        match_type = "token"
        candidate_value = matched_token.text if matched_token else None
        raw_text = matched_token.text if matched_token else None
        page_number = matched_token.page_number if matched_token else 1
        bbox = _bbox_from_polygon(matched_token.bbox) if matched_token else None
        evidence_text = matched_token.text if matched_token else None
        confidence = matched_token.confidence if matched_token else run.average_confidence

        if matched_token is None:
            matched_layout_pair = _match_layout_pair(
                label,
                field_name,
                value,
                cast(Sequence[LayoutKeyValue | LayoutKeyValueCandidate], run.key_value_pairs),
            )
            if matched_layout_pair:
                match_type = "layout-pair"
                candidate_value = matched_layout_pair.value
                raw_text = matched_layout_pair.raw_line
                page_number = matched_layout_pair.page_number
                evidence_text = matched_layout_pair.raw_line
                confidence = run.average_confidence
            else:
                matched_page_text = _match_page_text(value, run)
                if matched_page_text:
                    match_type = "page-text"
                    candidate_value, page_number = matched_page_text
                    raw_text = candidate_value
                    evidence_text = candidate_value
                    confidence = run.average_confidence
                else:
                    heuristic_candidate = _resolve_run_heuristic_candidate(label, field_name, run)
                    if heuristic_candidate:
                        match_type = "run-heuristic"
                        candidate_value = heuristic_candidate
                        raw_text = heuristic_candidate
                        evidence_text = heuristic_candidate
                        confidence = run.average_confidence

        if candidate_value is None and raw_text is None:
            heuristic_candidate = _resolve_run_heuristic_candidate(label, field_name, run)
            if not heuristic_candidate:
                continue
            match_type = "run-heuristic"
            candidate_value = heuristic_candidate
            raw_text = heuristic_candidate
            evidence_text = heuristic_candidate
            confidence = run.average_confidence

        candidates.append(
            FieldCandidateResult(
                engine=run.engine,
                source=run.source,
                value=candidate_value,
                raw_text=raw_text,
                confidence=confidence,
                page_number=page_number,
                bbox=bbox,
                evidence_text=evidence_text,
                selected=_compact(candidate_value) == _compact(value) and bool(value),
                match_type=match_type,
                score=_score_field_candidate(value, candidate_value, confidence, match_type),
            )
        )

        heuristic_candidate = _resolve_run_heuristic_candidate(label, field_name, run)
        primary_compact = _compact(candidate_value) or _compact(raw_text)
        heuristic_compact = _compact(heuristic_candidate)
        if heuristic_candidate and heuristic_compact and heuristic_compact != primary_compact:
            candidates.append(
                FieldCandidateResult(
                    engine=run.engine,
                    source=run.source,
                    value=heuristic_candidate,
                    raw_text=heuristic_candidate,
                    confidence=run.average_confidence,
                    page_number=1,
                    bbox=None,
                    evidence_text=heuristic_candidate,
                    selected=_compact(heuristic_candidate) == _compact(value) and bool(value),
                    match_type="run-heuristic",
                    score=_score_field_candidate(value, heuristic_candidate, run.average_confidence, "run-heuristic"),
                )
            )

    deduped: dict[tuple[str, str, int], FieldCandidateResult] = {}
    for candidate in candidates:
        key = (candidate.source, _compact(candidate.value) or _compact(candidate.raw_text), candidate.page_number)
        current = deduped.get(key)
        if current is None or candidate.score > current.score:
            deduped[key] = candidate

    sorted_candidates = sorted(deduped.values(), key=lambda candidate: (candidate.selected, candidate.score, candidate.confidence or 0.0), reverse=True)
    if not sorted_candidates:
        return [], None

    supporting_engines = [candidate.source for candidate in sorted_candidates if candidate.selected]
    distinct_values = {_compact(candidate.value) or _compact(candidate.raw_text) for candidate in sorted_candidates if candidate.value or candidate.raw_text}
    selected_values = {_compact(candidate.value) or _compact(candidate.raw_text) for candidate in sorted_candidates if candidate.selected and (candidate.value or candidate.raw_text)}
    engines_considered = len(successful_runs)
    agreement_ratio = len(supporting_engines) / engines_considered if engines_considered else 0.0
    consensus = FieldConsensusResult(
        engines_considered=engines_considered,
        candidate_count=len(distinct_values),
        supporting_engines=supporting_engines,
        agreement_ratio=round(agreement_ratio, 3),
        disagreement=engines_considered > 1 and len(selected_values) > 1,
    )
    return sorted_candidates, consensus


def _build_fields(
    response: ProcessResponse,
    *,
    engine: str,
    tokens: list[OCRToken] | None = None,
    layout_pairs: list[LayoutKeyValue] | None = None,
    ocr_runs: list[OCRRunInfo] | None = None,
    pack: DocumentPack | None = None,
    adjudications: dict[str, FieldAdjudicationResult] | None = None,
) -> list[ExtractedFieldResult]:
    fields: list[ExtractedFieldResult] = []
    available_tokens = tokens or []
    available_layout_pairs = layout_pairs or []
    available_ocr_runs = ocr_runs or []
    pack_fields = {field.field_key: field for field in (pack.expected_fields if pack else ())}
    page_quality_by_page = {page.page_number: page.quality_score for page in response.pages}

    def resolve_adjudication(label: str, field_name: str) -> FieldAdjudicationResult | None:
        if not adjudications:
            return None
        for pack_field in pack_fields.values():
            candidate_slugs = _pack_field_slugs(pack_field)
            if _slugify(label) in candidate_slugs or _slugify(field_name) in candidate_slugs:
                return adjudications.get(pack_field.field_key)
        return None

    def resolve_pack_field(label: str, field_name: str) -> PackFieldDefinition | None:
        for pack_field in pack_fields.values():
            candidate_slugs = _pack_field_slugs(pack_field)
            if _slugify(label) in candidate_slugs or _slugify(field_name) in candidate_slugs:
                return pack_field
        return None

    def compute_confidence_details(
        *,
        label: str,
        field_name: str,
        value: str | None,
        issue_ids: list[str],
        matched_token: OCRToken | OCRTokenInfo | None,
        matched_layout_pair: LayoutKeyValue | LayoutKeyValueCandidate | None,
        candidates: list[FieldCandidateResult],
        consensus: FieldConsensusResult | None,
        adjudication: FieldAdjudicationResult | None,
    ) -> ConfidenceDetails:
        pack_field = resolve_pack_field(label, field_name)
        confidence = 0.66
        ocr_confidence = None
        if matched_token and matched_token.confidence is not None:
            confidence = max(confidence, matched_token.confidence)
            ocr_confidence = matched_token.confidence
        elif candidates:
            candidate_confidences = [candidate.confidence for candidate in candidates if candidate.confidence is not None]
            if candidate_confidences:
                ocr_confidence = max(candidate_confidences)
        normalization_confidence = max([candidate.score for candidate in candidates], default=0.66)
        if candidates:
            confidence = max(confidence, max(candidate.score for candidate in candidates))
        if consensus:
            confidence = max(confidence, 0.52 + (consensus.agreement_ratio * 0.38))
        if adjudication and not adjudication.abstained and adjudication.confidence is not None:
            confidence = max(confidence, adjudication.confidence)
            normalization_confidence = max(normalization_confidence, adjudication.confidence)
        issue_penalty = min(0.18, len(issue_ids) * 0.05)
        if issue_ids:
            confidence -= issue_penalty

        normalized_value = value or (adjudication.selected_value if adjudication and not adjudication.abstained else None)
        normalized_key = _slugify(field_name)
        integrity_score = None
        if normalized_key in {"run", "document-number", "numero-de-documento"} and pack and pack.country == "CL" and validate_chile_run_checksum(normalized_value):
            confidence = max(confidence, 0.99)
            integrity_score = 0.99
        if normalized_key == "mrz" and validate_mrz_check_digits(normalized_value):
            confidence = max(confidence, 0.99)
            integrity_score = 0.99
        if pack_field and pack_field.critical and not issue_ids:
            confidence += 0.04
        page_number = matched_token.page_number if matched_token else (matched_layout_pair.page_number if matched_layout_pair else 1)
        quality_score = page_quality_by_page.get(page_number)
        reasons: list[str] = []
        if ocr_confidence is not None:
            reasons.append(f"ocr={ocr_confidence:.2f}")
        if quality_score is not None:
            reasons.append(f"quality={quality_score:.2f}")
        if consensus is not None:
            reasons.append(f"consensus={consensus.agreement_ratio:.2f}")
        if issue_penalty > 0:
            reasons.append(f"issue_penalty={issue_penalty:.2f}")
        if integrity_score is not None:
            reasons.append(f"integrity={integrity_score:.2f}")
        return ConfidenceDetails(
            final=round(max(0.05, min(confidence, 0.99)), 3),
            ocr_confidence=ocr_confidence,
            normalization_confidence=round(max(0.05, min(normalization_confidence, 0.99)), 3),
            validation_confidence=round(max(0.05, min(0.99, 0.96 - issue_penalty)), 3),
            quality_score=quality_score,
            consensus_confidence=consensus.agreement_ratio if consensus else None,
            integrity_score=integrity_score,
            issue_penalty=round(issue_penalty, 3),
            reasons=reasons,
        )

    for section in response.report_sections:
        if section.id.startswith("layout-") or section.id.startswith("debug-"):
            continue
        if section.variant == "pairs" and section.rows:
            for row in section.rows:
                label = row[0]
                value = row[1] if len(row) > 1 else None
                field_name = _slugify(label)
                issue_ids = _link_issue_ids(label, field_name, response.issues)
                matched_token = _match_token(value, available_tokens)
                matched_layout_pair = _match_layout_pair(label, field_name, value, available_layout_pairs) if not matched_token else None
                candidates, consensus = _build_field_candidates(label, field_name, value, available_ocr_runs)
                adjudication = resolve_adjudication(label, field_name)
                confidence_details = compute_confidence_details(
                    label=label,
                    field_name=field_name,
                    value=value,
                    issue_ids=issue_ids,
                    matched_token=matched_token,
                    matched_layout_pair=matched_layout_pair,
                    candidates=candidates,
                    consensus=consensus,
                    adjudication=adjudication,
                )
                fields.append(
                    ExtractedFieldResult(
                        id=f"{section.id}-{field_name or 'field'}",
                        section=section.id,
                        field_name=field_name or "field",
                        label=label,
                        value=value,
                        raw_text=value,
                        value_type=_value_type(value),
                        confidence=confidence_details.final,
                        engine=engine,
                        page_number=matched_token.page_number if matched_token else (matched_layout_pair.page_number if matched_layout_pair else 1),
                        issue_ids=issue_ids,
                        bbox=_bbox_from_polygon(matched_token.bbox) if matched_token else _layout_pair_bbox(matched_layout_pair),
                        evidence={
                            "text": matched_token.text if matched_token else (matched_layout_pair.raw_line if matched_layout_pair else value),
                            "confidence": matched_token.confidence if matched_token else None,
                            "source": "visual-ocr-token" if matched_token else ("layout-key-value" if matched_layout_pair else "normalized-value"),
                        },
                        candidates=candidates,
                        consensus=consensus,
                        adjudication=adjudication,
                        confidence_details=confidence_details,
                    )
                )

        if section.variant == "table" and section.columns and section.rows:
            if len(section.columns) == 2 and section.columns[0].lower() == "campo":
                for row in section.rows:
                    label = row[0]
                    value = row[1] if len(row) > 1 else None
                    field_name = _slugify(label)
                    issue_ids = _link_issue_ids(label, field_name, response.issues)
                    matched_token = _match_token(value, available_tokens)
                    matched_layout_pair = _match_layout_pair(label, field_name, value, available_layout_pairs) if not matched_token else None
                    candidates, consensus = _build_field_candidates(label, field_name, value, available_ocr_runs)
                    adjudication = resolve_adjudication(label, field_name)
                    confidence_details = compute_confidence_details(
                        label=label,
                        field_name=field_name,
                        value=value,
                        issue_ids=issue_ids,
                        matched_token=matched_token,
                        matched_layout_pair=matched_layout_pair,
                        candidates=candidates,
                        consensus=consensus,
                        adjudication=adjudication,
                    )
                    fields.append(
                        ExtractedFieldResult(
                            id=f"{section.id}-{field_name or 'field'}",
                            section=section.id,
                            field_name=field_name or "field",
                            label=label,
                            value=value,
                            raw_text=value,
                            value_type=_value_type(value),
                            confidence=confidence_details.final,
                            engine=engine,
                            page_number=matched_token.page_number if matched_token else (matched_layout_pair.page_number if matched_layout_pair else 1),
                            issue_ids=issue_ids,
                            bbox=_bbox_from_polygon(matched_token.bbox) if matched_token else _layout_pair_bbox(matched_layout_pair),
                            evidence={
                                "text": matched_token.text if matched_token else (matched_layout_pair.raw_line if matched_layout_pair else value),
                                "confidence": matched_token.confidence if matched_token else None,
                                "source": "visual-ocr-token" if matched_token else ("layout-key-value" if matched_layout_pair else "normalized-value"),
                            },
                            candidates=candidates,
                            consensus=consensus,
                            adjudication=adjudication,
                            confidence_details=confidence_details,
                        )
                    )
            else:
                for row in section.rows:
                    row_context = row[0] if row else section.title
                    for column_index, column in enumerate(section.columns[1:], start=1):
                        value = row[column_index] if column_index < len(row) else None
                        label = f"{row_context} · {column}"
                        field_name = _slugify(f"{row_context}-{column}")
                        issue_ids = _link_issue_ids(label, field_name, response.issues)
                        matched_token = _match_token(value, available_tokens)
                        matched_layout_pair = _match_layout_pair(label, field_name, value, available_layout_pairs) if not matched_token else None
                        candidates, consensus = _build_field_candidates(label, field_name, value, available_ocr_runs)
                        adjudication = resolve_adjudication(label, field_name)
                        confidence_details = compute_confidence_details(
                            label=label,
                            field_name=field_name,
                            value=value,
                            issue_ids=issue_ids,
                            matched_token=matched_token,
                            matched_layout_pair=matched_layout_pair,
                            candidates=candidates,
                            consensus=consensus,
                            adjudication=adjudication,
                        )
                        fields.append(
                            ExtractedFieldResult(
                                id=f"{section.id}-{field_name or 'field'}",
                                section=section.id,
                                field_name=field_name or "field",
                                label=label,
                                value=value,
                                raw_text=value,
                                value_type=_value_type(value),
                                confidence=confidence_details.final,
                                engine=engine,
                                page_number=matched_token.page_number if matched_token else (matched_layout_pair.page_number if matched_layout_pair else 1),
                                issue_ids=issue_ids,
                                bbox=_bbox_from_polygon(matched_token.bbox) if matched_token else _layout_pair_bbox(matched_layout_pair),
                                evidence={
                                    "text": matched_token.text if matched_token else (matched_layout_pair.raw_line if matched_layout_pair else value),
                                    "confidence": matched_token.confidence if matched_token else None,
                                    "source": "visual-ocr-token" if matched_token else ("layout-key-value" if matched_layout_pair else "normalized-value"),
                                },
                                candidates=candidates,
                                consensus=consensus,
                                adjudication=adjudication,
                                confidence_details=confidence_details,
                            )
                        )

        if section.variant == "text" and section.body:
            label = section.title
            field_name = _slugify(label)
            issue_ids = _link_issue_ids(label, field_name, response.issues)
            matched_token = _match_token(section.body, available_tokens)
            matched_layout_pair = _match_layout_pair(label, field_name, section.body, available_layout_pairs) if not matched_token else None
            candidates, consensus = _build_field_candidates(label, field_name, section.body, available_ocr_runs)
            adjudication = resolve_adjudication(label, field_name)
            confidence_details = compute_confidence_details(
                label=label,
                field_name=field_name,
                value=section.body,
                issue_ids=issue_ids,
                matched_token=matched_token,
                matched_layout_pair=matched_layout_pair,
                candidates=candidates,
                consensus=consensus,
                adjudication=adjudication,
            )
            fields.append(
                ExtractedFieldResult(
                    id=f"{section.id}-{field_name or 'field'}",
                    section=section.id,
                    field_name=field_name or "field",
                    label=label,
                    value=section.body,
                    raw_text=section.body,
                    value_type="text",
                    confidence=confidence_details.final,
                    engine=engine,
                    page_number=matched_token.page_number if matched_token else (matched_layout_pair.page_number if matched_layout_pair else 1),
                    issue_ids=issue_ids,
                    bbox=_bbox_from_polygon(matched_token.bbox) if matched_token else _layout_pair_bbox(matched_layout_pair),
                    evidence={
                        "text": matched_token.text if matched_token else (matched_layout_pair.raw_line if matched_layout_pair else section.body),
                        "confidence": matched_token.confidence if matched_token else None,
                        "source": "visual-ocr-token" if matched_token else ("layout-key-value" if matched_layout_pair else "normalized-value"),
                    },
                    candidates=candidates,
                    consensus=consensus,
                    adjudication=adjudication,
                    confidence_details=confidence_details,
                )
            )

    return fields


def _enrich_response(
    response: ProcessResponse,
    *,
    engine: str,
    extraction_source: str,
    response_mode: ResponseMode,
    request_id: str | None = None,
    tokens: list[OCRToken] | None = None,
    layout_pairs: list[LayoutKeyValue] | None = None,
    pack_id: str | None = None,
    pack_version: str | None = None,
    document_side: str | None = None,
    decision_profile: str | None = None,
    requested_visual_engine: str | None = None,
    classification_confidence: float | None = None,
    selected_visual_engine: str | None = None,
    ensemble_mode: str | None = None,
    ocr_runs: list[OCRRunInfo] | None = None,
    adjudication_mode: str | None = None,
    adjudications: dict[str, FieldAdjudicationResult] | None = None,
    pack: DocumentPack | None = None,
    processing_trace: list[ProcessingTraceEntry] | None = None,
    confidence_details: ConfidenceDetails | None = None,
    integrity_assessment: IntegrityAssessment | None = None,
    quality_assessment: QualityAssessment | None = None,
) -> ProcessResponse:
    resolved_request_id = request_id or str(uuid4())
    response.request_id = resolved_request_id
    response.response_mode = response_mode
    response.document = ProcessDocumentInfo(
        family=response.document_family,
        country=response.country,
        variant=response.variant,
        pack_id=pack_id,
        pack_version=pack_version,
        document_side=document_side,
        issuer=response.issuer,
        holder_name=response.holder_name,
    )
    response.processing = ProcessMetadata(
        request_id=resolved_request_id,
        response_mode=response_mode,
        page_count=response.page_count,
        engine=engine,
        extraction_source=extraction_source,
        selected_visual_engine=selected_visual_engine,
        ensemble_mode=ensemble_mode,
        decision_profile=decision_profile,
        requested_visual_engine=requested_visual_engine,
        classification_confidence=classification_confidence,
        global_confidence=response.global_confidence,
        decision=cast(DocumentDecision, response.decision),
        review_required=response.review_required,
        processed_at=datetime.now(timezone.utc).isoformat(),
        ocr_runs=ocr_runs or [],
        adjudication_mode=adjudication_mode,
        adjudicated_fields=sum(1 for adjudication in (adjudications or {}).values() if not adjudication.abstained),
        adjudication_abstentions=sum(1 for adjudication in (adjudications or {}).values() if adjudication.abstained),
        processing_trace=processing_trace or [],
        confidence_details=confidence_details,
        integrity_assessment=integrity_assessment,
        quality_assessment=quality_assessment or build_quality_assessment(response.pages),
    )
    response.fields = _build_fields(
        response,
        engine=engine,
        tokens=tokens,
        layout_pairs=layout_pairs,
        ocr_runs=ocr_runs,
        pack=pack,
        adjudications=adjudications,
    )

    if response_mode == "json":
        response.report_html = None

    return response


def _build_unsupported_response(
    *,
    filename: str,
    document_family: str,
    country: str,
    variant: str | None,
    page_count: int,
    extraction_source: str,
    response_mode: ResponseMode,
    reason: str,
    assumptions: list[str],
    issues: list[ValidationIssue] | None = None,
    pack_id: str | None = None,
    pack_version: str | None = None,
    document_side: str | None = None,
    decision_profile: str | None = None,
    requested_visual_engine: str | None = None,
    classification_confidence: float | None = None,
    selected_visual_engine: str | None = None,
    ensemble_mode: str | None = None,
    ocr_runs: list[OCRRunInfo] | None = None,
    processing_trace: list[ProcessingTraceEntry] | None = None,
    tokens: list[OCRToken] | None = None,
    layout_pairs: list[LayoutKeyValue] | None = None,
    pages: list[ProcessPageInfo] | None = None,
) -> ProcessResponse:
    pack = resolve_document_pack(pack_id=pack_id, document_family=document_family, country=country, variant=variant)
    response = ProcessResponse(
        document_family=document_family,
        country=country,
        variant=variant or (pack.variant if pack else None),
        issuer=None,
        holder_name=None,
        page_count=page_count,
        global_confidence=min(classification_confidence or 0.28, 0.42),
        decision=cast(DocumentDecision, "human_review"),
        review_required=True,
        assumptions=assumptions,
        pages=pages or [],
        issues=issues
        or [
            ValidationIssue(
                id="issue-unsupported-document",
                type="UNSUPPORTED_DOCUMENT",
                field="document_family",
                severity="high",
                message=reason,
                suggestedAction="Enviar a revision humana o crear un country pack/extractor especifico para esta variante.",
            )
        ],
        report_sections=[
            ReportSection(
                id="summary",
                title="Resumen",
                variant="pairs",
                rows=[
                    ["Archivo", filename],
                    ["Familia detectada", document_family],
                    ["Pais detectado", country],
                    ["Variante", variant or "SIN VARIANTE"],
                    ["Estado", "REQUIERE SOPORTE O REVISION HUMANA"],
                ],
            ),
            ReportSection(
                id="human-summary",
                title="Resumen humano",
                variant="text",
                body=reason,
            ),
            *_build_layout_sections(LayoutExtractionResult(engine="layout", lines=[], key_value_pairs=layout_pairs or [], table_candidate_rows=[])),
            *_build_ocr_ensemble_sections(ocr_runs or []),
        ],
        human_summary=reason,
        report_html="",
    )
    response.report_html = build_html(response, filename)
    return _enrich_response(
        response,
        engine="unsupported-document",
        extraction_source=extraction_source,
        response_mode=response_mode,
        tokens=tokens,
        layout_pairs=layout_pairs,
        pack_id=pack_id,
        pack_version=pack_version,
        document_side=document_side,
        decision_profile=decision_profile,
        requested_visual_engine=requested_visual_engine,
        classification_confidence=classification_confidence,
        selected_visual_engine=selected_visual_engine,
        ensemble_mode=ensemble_mode,
        ocr_runs=ocr_runs,
        processing_trace=processing_trace,
    )


def _build_mixed_document_response(
    *,
    filename: str,
    extraction_source: str,
    response_mode: ResponseMode,
    split_result: SplitDocumentResult,
    assumptions: list[str],
    pages: list[ProcessPageInfo],
    decision_profile: str | None,
    requested_visual_engine: str | None,
    classification_confidence: float | None,
    selected_visual_engine: str | None = None,
    ensemble_mode: str | None = None,
    ocr_runs: list[OCRRunInfo] | None = None,
    processing_trace: list[ProcessingTraceEntry] | None = None,
) -> ProcessResponse:
    response = ProcessResponse(
        document_family="mixed",
        country="XX",
        variant="mixed-by-pages",
        issuer=None,
        holder_name=None,
        pages=pages,
        page_count=split_result.page_count,
        global_confidence=min(classification_confidence or 0.5, 0.7),
        decision=cast(DocumentDecision, "human_review"),
        review_required=True,
        assumptions=assumptions,
        issues=[
            ValidationIssue(
                id="issue-mixed-document",
                type="MIXED_DOCUMENT",
                field="document_family",
                severity="high",
                message="Se detectaron multiples segmentos documentales dentro del mismo archivo.",
                suggestedAction="Separar el PDF por segmentos antes de continuar con extraccion y validacion individual.",
            )
        ],
        report_sections=[
            ReportSection(
                id="summary",
                title="Resumen",
                variant="pairs",
                rows=[
                    ["Archivo", filename],
                    ["Familia", "MIXED"],
                    ["Segmentos", str(len(split_result.segments))],
                    ["Estado", "REQUIERE SPLIT / REVIEW"],
                ],
            ),
            *_build_split_sections(split_result),
            *_build_ocr_ensemble_sections(ocr_runs or []),
            ReportSection(
                id="human-summary",
                title="Resumen humano",
                variant="text",
                body="El archivo contiene multiples grupos de paginas con clasificaciones distintas. Debe separarse por segmento antes del procesamiento final.",
            ),
        ],
        human_summary="Documento mixto detectado automaticamente; se recomienda segmentacion por paginas antes de la extraccion final.",
        report_html="",
    )
    response.report_html = build_html(response, filename)
    return _enrich_response(
        response,
        engine="mixed-document-detector",
        extraction_source=extraction_source,
        response_mode=response_mode,
        decision_profile=decision_profile,
        requested_visual_engine=requested_visual_engine,
        classification_confidence=classification_confidence,
        selected_visual_engine=selected_visual_engine,
        ensemble_mode=ensemble_mode,
        ocr_runs=ocr_runs,
        processing_trace=processing_trace,
    )


def run_processing_pipeline(
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    document_family: str,
    country: str,
    response_mode: ResponseMode = "json",
    ocr_visual_engine: str | None = None,
    decision_profile: str | None = None,
    tenant_id: str | None = None,
    structured_mode_override: str | None = None,
    ocr_ensemble_mode: str | None = None,
    ocr_ensemble_engines: str | None = None,
    field_adjudication_mode: str | None = None,
) -> ProcessResponse:
    processing_trace: list[ProcessingTraceEntry] = []
    log_event(
        "processing_pipeline_started",
        filename=filename,
        requested_family=document_family,
        requested_country=country,
        response_mode=response_mode,
        ocr_visual_engine=ocr_visual_engine,
        decision_profile=decision_profile,
        tenant_id=tenant_id,
        structured_mode_override=structured_mode_override,
        ocr_ensemble_mode=ocr_ensemble_mode,
        ocr_ensemble_engines=ocr_ensemble_engines,
        field_adjudication_mode=field_adjudication_mode,
    )
    extraction_started_at = datetime.now(timezone.utc).isoformat()
    extraction_started_counter = perf_counter()
    extraction = extract_document_text(file_bytes, filename, content_type)
    _trace_stage(
        processing_trace,
        stage="extract_embedded_text",
        started_at_iso=extraction_started_at,
        started_counter=extraction_started_counter,
        summary=f"Texto embebido detectado en {extraction.page_count} pagina(s) desde {extraction.source}.",
    )
    suffix = Path(filename).suffix.lower()
    mime_type = (content_type or "").lower()
    requested_family = normalize_requested_family(document_family)
    requested_country = normalize_requested_country(country)

    normalized: NormalizedDocument | None = None
    normalization_engine = "heuristic"
    visual_text = ""
    visual_assumptions: list[str] = []
    effective_family = requested_family
    effective_country = requested_country
    effective_variant: str | None = None
    visual_tokens: list[OCRToken] = []
    layout_extraction = LayoutExtractionResult(engine="none", lines=[], key_value_pairs=[], table_candidate_rows=[])
    prepared_pages: list[PreprocessedPage] = []
    rendered_pages: list[bytes] = []
    visual_ocr = None
    selected_visual_engine: str | None = None
    selected_page_profiles: dict[int, str] = {}
    ensemble_mode = "single"
    ocr_runs: list[OCRRunInfo] = []
    structured_normalizer = get_structured_normalizer_engine()
    structured_mode = (structured_mode_override or get_structured_normalizer_mode()).strip().lower()
    if structured_mode not in {"heuristic", "openai", "auto"}:
        structured_mode = get_structured_normalizer_mode()
    heuristic_normalizer = get_heuristic_normalizer_engine()

    if mime_type == "application/pdf" or suffix == ".pdf" or mime_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}:
        preflight_started_at = datetime.now(timezone.utc).isoformat()
        preflight_started_counter = perf_counter()
        try:
            prepared_pages = prepare_document_pages(file_bytes, filename, content_type, extraction.page_texts)
            rendered_pages = [page.image_bytes for page in prepared_pages]
            _trace_stage(
                processing_trace,
                stage="preflight",
                started_at_iso=preflight_started_at,
                started_counter=preflight_started_counter,
                summary=f"Preflight local completado sobre {len(prepared_pages)} pagina(s) renderizadas.",
            )
        except Exception:
            prepared_pages = []
            rendered_pages = []
            _trace_stage(
                processing_trace,
                stage="preflight",
                started_at_iso=preflight_started_at,
                started_counter=preflight_started_counter,
                summary="Preflight local fallo; se continua sin paginas derivadas.",
                status="degraded",
            )

    if not extraction.text:
        (
            visual_ocr,
            visual_text,
            visual_tokens,
            selected_visual_engine,
            selected_page_profiles,
            ensemble_mode,
            visual_assumptions,
            ocr_runs,
        ) = _execute_visual_ocr_stage(
            prepared_pages=prepared_pages,
            rendered_pages=rendered_pages,
            ocr_visual_engine=ocr_visual_engine,
            requested_family=requested_family,
            requested_country=requested_country,
            ocr_ensemble_mode=ocr_ensemble_mode,
            ocr_ensemble_engines=ocr_ensemble_engines,
            processing_trace=processing_trace,
            stage="ocr_ensemble",
            support_only_local=False,
        )

    classification_source = extraction.text or visual_text
    classify_started_at = datetime.now(timezone.utc).isoformat()
    classify_started_counter = perf_counter()
    classification = classify_document(classification_source, document_family, country)
    if visual_tokens:
        layout_extraction = extract_layout_from_tokens(visual_tokens, engine=f"{visual_ocr.source}-layout" if visual_ocr else "visual-layout")
    elif any(page.strip() for page in extraction.page_texts):
        layout_extraction = extract_layout_from_page_texts(extraction.page_texts, engine="embedded-text-layout")
    elif extraction.text.strip():
        layout_extraction = extract_layout_from_page_texts([extraction.text], engine="plain-text-layout")
    layout_assumptions = (
        [f"Layout extraction: {len(layout_extraction.key_value_pairs)} pares clave-valor y {len(layout_extraction.table_candidate_rows)} filas candidatas a tabla detectadas."]
        if layout_extraction.lines
        else []
    )
    analysis_page_texts = extraction.page_texts if any(page.strip() for page in extraction.page_texts) else (visual_ocr.page_texts if visual_ocr else [])
    page_analysis = analyze_document_pages(analysis_page_texts, document_family, country)
    split_source_pages = analysis_page_texts
    split_result = split_document_pages(split_source_pages, document_family, country) if split_source_pages else SplitDocumentResult(page_count=max(extraction.page_count, 1), segments=[], mixed_detected=False, assumptions=[])
    _trace_stage(
        processing_trace,
        stage="classification_and_split",
        started_at_iso=classify_started_at,
        started_counter=classify_started_counter,
        summary=(
            f"Clasificacion principal {classification.document_family}/{classification.country} y {len(split_result.segments)} segmento(s) detectados."
        ),
    )

    if split_result.mixed_detected and (requested_family == "mixed" or len(split_result.segments) > 1):
        mixed_response = _build_mixed_document_response(
            filename=filename,
            extraction_source=visual_ocr.source if visual_ocr and visual_text else extraction.source,
            response_mode=response_mode,
            split_result=split_result,
            assumptions=[
                *extraction.assumptions,
                *visual_assumptions,
                *split_result.assumptions,
            ],
            pages=_build_pages(prepared_pages, selected_page_profiles),
            decision_profile=decision_profile,
            requested_visual_engine=ocr_visual_engine,
            classification_confidence=max((segment.confidence for segment in split_result.segments), default=0.5),
            selected_visual_engine=selected_visual_engine,
            ensemble_mode=ensemble_mode,
            ocr_runs=ocr_runs,
            processing_trace=processing_trace,
        )
        log_event(
            "processing_pipeline_completed",
            filename=filename,
            document_family=mixed_response.document_family,
            country=mixed_response.country,
            decision=mixed_response.decision,
            extraction_source=mixed_response.processing.extraction_source if mixed_response.processing else extraction.source,
            processing_engine=mixed_response.processing.engine if mixed_response.processing else "mixed-document-detector",
            page_count=mixed_response.page_count,
        )
        return mixed_response

    resolved_classification = classification
    if page_analysis.dominant and (
        page_analysis.cross_side_detected
        or page_analysis.dominant.confidence > classification.confidence
        or not classification.supported
    ):
        resolved_classification = page_analysis.dominant

    effective_family = resolved_classification.document_family
    effective_country = resolved_classification.country
    effective_variant = resolved_classification.variant
    effective_pack_id = resolved_classification.pack_id
    effective_pack_version = resolved_classification.pack_version
    effective_document_side = page_analysis.document_side or resolved_classification.document_side
    normalization_request = NormalizationRequest(
        document_family=effective_family,
        country=effective_country,
        filename=filename,
        variant=effective_variant,
        pack_id=effective_pack_id,
        document_side=effective_document_side,
        assumptions=[*extraction.assumptions, *page_analysis.assumptions],
    )
    supplemental_fields = extract_supplemental_fields(
        prepared_pages,
        document_family=effective_family,
        country=effective_country,
        pack_id=effective_pack_id,
        document_side=effective_document_side,
    )
    normalization_started_at = datetime.now(timezone.utc).isoformat()
    normalization_started_counter = perf_counter()
    text_normalization_request = normalization_request
    text_request_assumptions = list(normalization_request.assumptions or [])
    if extraction.text and visual_text and effective_family == "certificate" and effective_pack_id == "certificate-cl-previsional":
        text_normalization_request = NormalizationRequest(
            document_family=normalization_request.document_family,
            country=normalization_request.country,
            filename=normalization_request.filename,
            variant=normalization_request.variant,
            pack_id=normalization_request.pack_id,
            document_side=normalization_request.document_side,
            assumptions=text_request_assumptions + visual_assumptions + ["Se ejecutó OCR visual de apoyo para un PDF previsional con texto embebido."],
        )

    if normalized is None and effective_family == "identity" and effective_country == "CL" and page_analysis.cross_side_detected and analysis_page_texts:
        cross_side_candidate = _build_identity_cross_side_normalized(
            filename=filename,
            page_analysis=page_analysis,
            page_texts=analysis_page_texts,
            prepared_pages=prepared_pages,
            cross_side_signal=build_cross_side_consistency_signal(page_analysis, analysis_page_texts, effective_country),
            assumptions=[*(text_normalization_request.assumptions or []), *visual_assumptions],
        )
        if cross_side_candidate is not None:
            normalized = cross_side_candidate
            normalization_engine = "heuristic-cross-side"

    if structured_mode == "openai" and extraction.text and structured_normalizer.name != "heuristic":
        try:
            structured_candidate = structured_normalizer.normalize_text(normalization_request, extraction.text)
            structured_candidate.assumptions = [*extraction.assumptions, *structured_candidate.assumptions]
            normalized = structured_candidate
            normalization_engine = structured_normalizer.name
            if normalized.global_confidence <= 0.05:
                normalized = None
        except Exception:
            normalized = None

    if normalized is None and structured_mode == "openai" and visual_text and structured_normalizer.name != "heuristic":
        try:
            structured_candidate = structured_normalizer.normalize_text(normalization_request, visual_text)
            structured_candidate.assumptions = [*extraction.assumptions, *visual_assumptions, *structured_candidate.assumptions]
            normalized = structured_candidate
            normalization_engine = structured_normalizer.name
            if normalized.global_confidence <= 0.05:
                normalized = None
        except Exception:
            normalized = None

    if normalized is None and extraction.text and resolved_classification.supported and effective_family in {"identity", "certificate", "passport", "driver_license"}:
        normalized = _heuristic_normalize(text_normalization_request, extraction.text, supplemental_fields=supplemental_fields)
        normalization_engine = f"{heuristic_normalizer.name}-text"

        if structured_mode == "auto" and effective_family in {"identity", "certificate", "passport", "driver_license"} and structured_normalizer.name != "heuristic" and _should_escalate_to_structured(normalized, effective_family):
            try:
                structured_candidate = structured_normalizer.normalize_text(text_normalization_request, extraction.text)
                structured_candidate.assumptions = [*extraction.assumptions, *structured_candidate.assumptions, "Structured normalization se activo solo por baja confianza o issues heuristicas."]
                if _should_use_structured_candidate(normalized, structured_candidate):
                    normalized = structured_candidate
                    normalization_engine = structured_normalizer.name
            except Exception:
                pass

        if _should_try_visual_support_for_certificate(normalized, extraction.source, effective_pack_id):
            if not visual_text and prepared_pages:
                (
                    visual_ocr,
                    visual_text,
                    visual_tokens,
                    selected_visual_engine,
                    selected_page_profiles,
                    ensemble_mode,
                    visual_assumptions,
                    ocr_runs,
                ) = _execute_visual_ocr_stage(
                    prepared_pages=prepared_pages,
                    rendered_pages=rendered_pages,
                    ocr_visual_engine=ocr_visual_engine,
                    requested_family=requested_family,
                    requested_country=requested_country,
                    ocr_ensemble_mode=ocr_ensemble_mode,
                    ocr_ensemble_engines=ocr_ensemble_engines,
                    processing_trace=processing_trace,
                    stage="ocr_ensemble_support",
                    summary_prefix="OCR de soporte para PDF tabular con texto embebido insuficiente.",
                    support_only_local=True,
                )

            if visual_text:
                visual_request = NormalizationRequest(
                    document_family=effective_family,
                    country=effective_country,
                    filename=filename,
                    variant=effective_variant,
                    pack_id=effective_pack_id,
                    document_side=effective_document_side,
                    assumptions=[*extraction.assumptions, *visual_assumptions, *page_analysis.assumptions, "Se intento rescate visual para certificado tabular con texto embebido."],
                )
                visual_candidate = _heuristic_normalize(visual_request, visual_text, supplemental_fields=supplemental_fields)
                visual_candidate.assumptions = [*visual_candidate.assumptions, "La normalizacion visual se uso como apoyo para rescatar encabezado o tabla del certificado."]
                visual_candidate_engine = f"{heuristic_normalizer.name}-visual-ocr"
                visual_request_assumptions = list(visual_request.assumptions or [])

                if structured_mode == "auto" and structured_normalizer.name != "heuristic" and _should_escalate_to_structured(visual_candidate, effective_family):
                    try:
                        structured_visual_candidate = structured_normalizer.normalize_text(visual_request, visual_text)
                        structured_visual_candidate.assumptions = visual_request_assumptions + structured_visual_candidate.assumptions + [
                            "Structured normalization visual se activo para certificado tabular con evidencia insuficiente."
                        ]
                        if _should_use_structured_candidate(visual_candidate, structured_visual_candidate):
                            visual_candidate = structured_visual_candidate
                            visual_candidate_engine = structured_normalizer.name
                    except Exception:
                        pass

                if _should_use_visual_certificate_candidate(normalized, visual_candidate):
                    normalized = visual_candidate
                    normalization_engine = visual_candidate_engine

    if normalized is None and visual_text and resolved_classification.supported and effective_family in {"identity", "certificate", "passport", "driver_license"}:
        visual_request = NormalizationRequest(
            document_family=effective_family,
            country=effective_country,
            filename=filename,
            variant=effective_variant,
            pack_id=effective_pack_id,
            document_side=effective_document_side,
            assumptions=[*extraction.assumptions, *visual_assumptions, *page_analysis.assumptions],
        )
        normalized = _heuristic_normalize(visual_request, visual_text, supplemental_fields=supplemental_fields)
        normalization_engine = f"{heuristic_normalizer.name}-visual-ocr"

        if structured_mode == "auto" and effective_family in {"identity", "certificate", "passport", "driver_license"} and structured_normalizer.name != "heuristic" and _should_escalate_to_structured(normalized, effective_family):
            try:
                structured_candidate = structured_normalizer.normalize_text(visual_request, visual_text)
                structured_candidate.assumptions = [*extraction.assumptions, *visual_assumptions, *structured_candidate.assumptions, "Structured normalization se activo solo por baja confianza o issues heuristicas."]
                if _should_use_structured_candidate(normalized, structured_candidate):
                    normalized = structured_candidate
                    normalization_engine = structured_normalizer.name
            except Exception:
                pass

    if normalized is None and structured_mode == "openai" and not extraction.text and structured_normalizer.name != "heuristic" and (mime_type.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}):
        try:
            normalized = structured_normalizer.normalize_image(normalization_request, content_type or "image/png", file_bytes)
            normalized.assumptions = [
                *extraction.assumptions,
                "Se utilizo interpretacion multimodal con OpenAI como fallback visual para este prototipo.",
                *normalized.assumptions,
            ]
            normalization_engine = f"{structured_normalizer.name}-image"
        except Exception:
            normalized = None

    if normalized is None and structured_mode == "openai" and not extraction.text and structured_normalizer.name != "heuristic" and (mime_type == "application/pdf" or suffix == ".pdf"):
        try:
            if rendered_pages:
                normalized = structured_normalizer.normalize_rendered_pages(normalization_request, rendered_pages)
                normalized.assumptions = [
                    *extraction.assumptions,
                    "Se renderizaron paginas del PDF a imagenes para una interpretacion visual multimodal.",
                    *normalized.assumptions,
                ]
                normalization_engine = f"{structured_normalizer.name}-rendered-pdf"
        except Exception:
            normalized = None

    if normalized is None:
        _trace_stage(
            processing_trace,
            stage="normalization",
            started_at_iso=normalization_started_at,
            started_counter=normalization_started_counter,
            summary="No fue posible obtener un documento normalizado soportado con los extractores disponibles.",
            status="failed",
        )
        reason = (
            f"El documento fue clasificado como {effective_family}/{effective_country}"
            + (f" ({effective_variant})" if effective_variant else "")
            + ", pero todavia no existe un extractor confiable para autoaprobarlo."
        )
        if effective_family == "unclassified":
            reason = "No se pudo clasificar el documento con suficiente confianza para aplicar un pack conocido."
        if not classification_source:
            reason = "No se detecto texto embebido ni OCR visual suficiente para aplicar un pack conocido."

        unsupported_response = _build_unsupported_response(
            filename=filename,
            document_family=effective_family,
            country=effective_country,
            variant=effective_variant,
            page_count=max(extraction.page_count, max((token.page_number for token in visual_tokens), default=0), len(rendered_pages) or 0, 1),
            extraction_source=visual_ocr.source if visual_ocr and visual_text else extraction.source,
            response_mode=response_mode,
            reason=reason,
            assumptions=[
                *extraction.assumptions,
                *visual_assumptions,
                *page_analysis.assumptions,
                *layout_assumptions,
                f"Clasificacion automatica: {resolved_classification.document_family}/{resolved_classification.country} ({'; '.join(resolved_classification.reasons)})",
            ],
            pack_id=effective_pack_id,
            classification_confidence=resolved_classification.confidence,
            tokens=visual_tokens,
            layout_pairs=layout_extraction.key_value_pairs,
            pack_version=effective_pack_version,
            document_side=effective_document_side,
            decision_profile=decision_profile,
            requested_visual_engine=ocr_visual_engine,
            selected_visual_engine=selected_visual_engine,
            ensemble_mode=ensemble_mode,
            ocr_runs=ocr_runs,
            processing_trace=processing_trace,
            pages=_build_pages(prepared_pages, selected_page_profiles),
        )
        log_event(
            "processing_pipeline_completed",
            filename=filename,
            document_family=unsupported_response.document_family,
            country=unsupported_response.country,
            decision=unsupported_response.decision,
            extraction_source=unsupported_response.processing.extraction_source if unsupported_response.processing else extraction.source,
            processing_engine=unsupported_response.processing.engine if unsupported_response.processing else "unsupported-document",
            page_count=unsupported_response.page_count,
        )
        return unsupported_response

    if not normalized.variant:
        normalized.variant = effective_variant or normalized.variant

    if normalized.country in {"", "XX"} and effective_country not in {"", "XX"}:
        normalized.country = effective_country

    _trace_stage(
        processing_trace,
        stage="normalization",
        started_at_iso=normalization_started_at,
        started_counter=normalization_started_counter,
        summary=f"Normalizacion final resuelta con {normalization_engine} para {normalized.document_family}/{normalized.country}.",
    )

    final_extraction_source = visual_ocr.source if visual_ocr and visual_text else extraction.source
    resolved_pack = resolve_document_pack(
        pack_id=effective_pack_id,
        document_family=normalized.document_family,
        country=normalized.country,
        variant=normalized.variant,
    )
    adjudication_started_at = datetime.now(timezone.utc).isoformat()
    adjudication_started_counter = perf_counter()
    normalized, adjudications = _apply_pack_field_adjudication(
        normalized,
        resolved_pack,
        ocr_runs,
        adjudication_mode_override=field_adjudication_mode,
    )
    _trace_stage(
        processing_trace,
        stage="adjudication",
        started_at_iso=adjudication_started_at,
        started_counter=adjudication_started_counter,
        summary=f"Adjudicacion por campo ejecutada sobre {len(adjudications)} campo(s).",
        status="completed" if adjudications else "skipped",
    )
    field_signals = _build_rule_field_signals(normalized.report_sections, resolved_pack, ocr_runs)
    cross_side_signal = build_cross_side_consistency_signal(page_analysis, analysis_page_texts, normalized.country)
    quality_assessment = build_quality_assessment(prepared_pages)
    if feature_enabled("adaptive_confidence_recalibration"):
        normalized = _recalibrate_normalized_confidence(
            normalized,
            resolved_pack,
            field_signals,
            prepared_pages,
            cross_side_signal,
        )
    validation_started_at = datetime.now(timezone.utc).isoformat()
    validation_started_counter = perf_counter()
    rule_evaluation = evaluate_normalized_document(
        normalized,
        pack_id=effective_pack_id,
        classification_confidence=resolved_classification.confidence,
        document_side=effective_document_side,
        decision_profile=decision_profile,
        field_signals=field_signals,
        cross_side_signal=cross_side_signal,
        tenant_id=tenant_id,
    )
    _trace_stage(
        processing_trace,
        stage="validation",
        started_at_iso=validation_started_at,
        started_counter=validation_started_counter,
        summary=f"Rule engine devolvio {rule_evaluation.decision} con {len(rule_evaluation.issues)} issue(s).",
    )
    issues = _append_source_issue(list(rule_evaluation.issues), final_extraction_source)
    decision = rule_evaluation.decision
    review_required = rule_evaluation.review_required
    integrity_assessment = build_integrity_assessment(
        report_sections=normalized.report_sections,
        pack=resolved_pack,
        prepared_pages=prepared_pages,
        field_signals=field_signals,
        cross_side_signal=cross_side_signal,
    )
    confidence_details = _build_global_confidence_details(
        final_confidence=normalized.global_confidence,
        normalized_confidence=normalized.global_confidence,
        issues=issues,
        prepared_pages=prepared_pages,
        ocr_runs=ocr_runs,
        field_signals=field_signals,
        integrity_assessment=integrity_assessment,
    )
    normalized.assumptions = [
        *normalized.assumptions,
        *rule_evaluation.assumptions,
        *page_analysis.assumptions,
        *layout_assumptions,
        f"Clasificacion automatica: {resolved_classification.document_family}/{resolved_classification.country} ({'; '.join(resolved_classification.reasons)})",
    ]

    response = ProcessResponse(
        document_family=normalized.document_family,
        country=normalized.country,
        variant=normalized.variant,
        issuer=normalized.issuer,
        holder_name=normalized.holder_name,
        pages=_build_pages(prepared_pages, selected_page_profiles),
        page_count=max(extraction.page_count, max((token.page_number for token in visual_tokens), default=0), len(rendered_pages) or 0, 1),
        global_confidence=normalized.global_confidence,
        decision=cast(DocumentDecision, decision),
        review_required=review_required,
        assumptions=normalized.assumptions,
        issues=issues,
        report_sections=[
            *normalized.report_sections,
            *_build_layout_sections(layout_extraction),
            *_build_ocr_ensemble_sections(ocr_runs),
            *_build_cross_side_sections(cross_side_signal),
            *_build_adjudication_sections(resolved_pack, adjudications),
            *_build_pack_quality_sections(resolved_pack, field_signals),
        ],
        human_summary=normalized.human_summary,
        report_html="",
    )
    report_started_at = datetime.now(timezone.utc).isoformat()
    report_started_counter = perf_counter()
    response.report_html = build_html(response, filename)
    _trace_stage(
        processing_trace,
        stage="report",
        started_at_iso=report_started_at,
        started_counter=report_started_counter,
        summary=f"Reporte HTML y payload final construidos para decision {response.decision}.",
    )
    enriched_response = _enrich_response(
        response,
        engine=normalization_engine,
        extraction_source=final_extraction_source,
        response_mode=response_mode,
        tokens=visual_tokens,
        layout_pairs=layout_extraction.key_value_pairs,
        pack_id=effective_pack_id,
        pack_version=effective_pack_version,
        document_side=effective_document_side,
        decision_profile=decision_profile,
        requested_visual_engine=ocr_visual_engine,
        classification_confidence=resolved_classification.confidence,
        selected_visual_engine=selected_visual_engine,
        ensemble_mode=ensemble_mode,
        ocr_runs=ocr_runs,
        adjudication_mode=adjudication_runtime_mode(field_adjudication_mode),
        adjudications=adjudications,
        pack=resolved_pack,
        processing_trace=processing_trace,
        confidence_details=confidence_details,
        integrity_assessment=integrity_assessment,
        quality_assessment=quality_assessment,
    )
    log_event(
        "processing_pipeline_completed",
        filename=filename,
        document_family=enriched_response.document_family,
        country=enriched_response.country,
        decision=enriched_response.decision,
        extraction_source=enriched_response.processing.extraction_source if enriched_response.processing else final_extraction_source,
        processing_engine=enriched_response.processing.engine if enriched_response.processing else normalization_engine,
        page_count=enriched_response.page_count,
        confidence=enriched_response.global_confidence,
    )
    return enriched_response
