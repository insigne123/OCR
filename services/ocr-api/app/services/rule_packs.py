from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import cast

from app.core.feature_flags import feature_enabled
from app.schemas import DocumentDecision, NormalizedDocument, ReportSection, ValidationIssue, ValidationSeverity
from app.services.cross_side_consistency import CrossSideConsistencySignal
from app.services.decision_policy import DecisionThresholdSettings, resolve_decision_thresholds
from app.services.document_packs import DocumentPack, PackFieldDefinition, iter_pack_field_keys, resolve_document_pack
from app.services.field_value_utils import (
    compact as normalized_compact,
    canonicalize_chile_run,
    canonicalize_identity_document_number,
    canonicalize_passport_number,
    derive_identity_holder_name,
    find_value_by_key_fragments,
    normalize_date_value,
    parse_passport_mrz,
    slugify,
    validate_chile_run_checksum,
    validate_mrz_check_digits,
)

CL_RUT_PATTERN = re.compile(r"\b(?:\d{1,2}[.,]?\d{3}[.,]?\d{3}|\d{7,8})-[\dkK]\b")
PE_DNI_PATTERN = re.compile(r"\b\d{8}\b")
CO_CEDULA_PATTERN = re.compile(r"\b\d{6,10}\b")
ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MISSING_VALUES = {"", "-", "NO DETECTADO", "NO DETECTADA", "NO DETECTADOS", "NO DETECTADAS", "PENDING", "NOMBRE POR CONFIRMAR"}
DECISION_PROFILES = {"strict", "balanced", "aggressive"}
WARNING_AUTO_ACCEPT_TYPES = {
    "FORMAT_REVIEW",
    "RULE_LOW_EVIDENCE",
    "LOW_EVIDENCE",
    "ocr_error",
    "text_recognition_error",
    "ocr_uncertainty",
    "text_inaccuracy",
    "typo",
    "format",
    "format_error",
    "date_format",
    "date_anomaly",
    "date_inconsistency",
    "RULE_DATE_CONSISTENCY",
    "field_confusion",
    "field_clarity",
    "text",
}


@dataclass(frozen=True)
class RuleEvaluation:
    rule_pack_id: str | None
    issues: list[ValidationIssue]
    decision: DocumentDecision
    review_required: bool
    assumptions: list[str]


@dataclass(frozen=True)
class FieldDecisionSignal:
    agreement_ratio: float = 0.0
    disagreement: bool = False
    candidate_count: int = 0
    supporting_engines: tuple[str, ...] = ()


def _normalize_decision_profile(value: str | None) -> str:
    profile = (value or "balanced").strip().lower()
    return profile if profile in DECISION_PROFILES else "balanced"


def _slugify(value: str) -> str:
    return slugify(value)


def _compact(value: str | None) -> str:
    return normalized_compact(value)


def _is_missing(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().upper() in MISSING_VALUES


def _make_issue(issue_id: str, issue_type: str, field: str, severity: ValidationSeverity, message: str, suggested_action: str) -> ValidationIssue:
    return ValidationIssue(
        id=issue_id,
        type=issue_type,
        field=field,
        severity=cast(ValidationSeverity, severity),
        message=message,
        suggestedAction=suggested_action,
    )


def _flatten_sections(report_sections: list[ReportSection]) -> dict[str, str]:
    values: dict[str, str] = {}

    for section in report_sections:
        if section.variant == "pairs" and section.rows:
            for row in section.rows:
                if not row:
                    continue
                label = row[0]
                value = row[1] if len(row) > 1 else ""
                values[_slugify(label)] = value

        if section.variant == "table" and section.columns and section.rows:
            if len(section.columns) == 2 and section.columns[0].lower() == "campo":
                for row in section.rows:
                    if not row:
                        continue
                    label = row[0]
                    value = row[1] if len(row) > 1 else ""
                    values[_slugify(label)] = value
            else:
                row_header = section.columns[0]
                for row in section.rows:
                    if not row:
                        continue
                    row_context = row[0]
                    values[_slugify(f"{section.id}-{row_context}-{row_header}")] = row_context
                    for index, column in enumerate(section.columns[1:], start=1):
                        values[_slugify(f"{row_context}-{column}")] = row[index] if index < len(row) else ""

        if section.variant == "text" and section.body:
            values[_slugify(section.title)] = section.body

    return values


def _extract_dates(values: dict[str, str]) -> list[date]:
    dates: list[date] = []
    for value in values.values():
        if _is_missing(value):
            continue
        for year, month, day in ISO_DATE_PATTERN.findall(value):
            try:
                parsed = date(int(year), int(month), int(day))
            except ValueError:
                continue
            if parsed not in dates:
                dates.append(parsed)
    return dates


def _merge_issues(existing: list[ValidationIssue], additional: list[ValidationIssue]) -> list[ValidationIssue]:
    deduped = {issue.id: issue for issue in existing}
    for issue in additional:
        deduped[issue.id] = issue
    return list(deduped.values())


def _resolve_pack_value(values: dict[str, str], pack: DocumentPack | None, field_key: str, fallback_keys: tuple[str, ...] = ()) -> str | None:
    resolved: str | None = None
    for candidate_key in (*iter_pack_field_keys(pack, field_key), *fallback_keys):
        resolved = values.get(_slugify(candidate_key))
        if not _is_missing(resolved):
            break

    country = pack.country if pack else values.get("pais", "")
    if field_key == "holder_name":
        return derive_identity_holder_name(values, resolved)
    if field_key == "document_number":
        if resolved is None:
            for candidate_key in ("numero-de-identificacion", "numero-de-identidad", "dni", "cedula"):
                candidate_value = values.get(_slugify(candidate_key))
                if not _is_missing(candidate_value):
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
        return canonicalize_identity_document_number(country or "", resolved)
    if field_key == "run":
        return canonicalize_chile_run(resolved)
    if field_key in {"birth_date", "issue_date", "expiry_date"}:
        return normalize_date_value(resolved)
    return resolved


def _pack_expected_field(pack: DocumentPack | None, field_key: str) -> PackFieldDefinition | None:
    if pack is None:
        return None
    return next((field for field in pack.expected_fields if field.field_key == field_key), None)


def _field_signal(signals: dict[str, FieldDecisionSignal] | None, field_key: str) -> FieldDecisionSignal:
    if not signals:
        return FieldDecisionSignal()
    return signals.get(field_key, FieldDecisionSignal())


def _is_auto_accept_blocker(issue: ValidationIssue, critical_field_names: set[str] | None = None) -> bool:
    critical_names = critical_field_names or set()
    field_name = _slugify(issue.field)

    if issue.severity == "high":
        return True
    if issue.type in {"RULE_REQUIRED_FIELD", "RULE_ENGINE_DISAGREEMENT", "RULE_CROSS_SIDE_MISMATCH", "RULE_CHECKSUM"}:
        return True
    if issue.type == "MISSING_FIELD" and field_name in critical_names:
        return True
    if issue.severity == "medium" and issue.type not in WARNING_AUTO_ACCEPT_TYPES:
        return True
    return False


def _append_pack_field_issues(
    issues: list[ValidationIssue],
    pack: DocumentPack | None,
    values: dict[str, str],
    field_signals: dict[str, FieldDecisionSignal] | None,
) -> list[ValidationIssue]:
    if pack is None or not pack.expected_fields:
        return issues

    enriched = [*issues]
    for field in pack.expected_fields:
        value = _resolve_pack_value(values, pack, field.field_key)
        signal = _field_signal(field_signals, field.field_key)
        if field.required and _is_missing(value):
            enriched.append(
                _make_issue(
                    f"rule-pack-missing-{field.field_key}",
                    "RULE_REQUIRED_FIELD",
                    field.field_key,
                    "high" if field.critical else "medium",
                    f"El pack {pack.pack_id} requiere el campo {field.label} para automatizacion confiable.",
                    f"Confirmar {field.label} manualmente o mejorar la extraccion del pack.",
                )
            )
            continue

        if _is_missing(value):
            continue

        if signal.disagreement and field.critical:
            enriched.append(
                _make_issue(
                    f"rule-pack-disagreement-{field.field_key}",
                    "RULE_ENGINE_DISAGREEMENT",
                    field.field_key,
                    "high" if signal.agreement_ratio < 0.5 else "medium",
                    f"Los motores OCR discrepan en el campo critico {field.label}.",
                    "Mantener revision humana o adjudicar con evidencia adicional antes de autoaceptar.",
                )
            )
        elif signal.disagreement and signal.agreement_ratio < pack.decision_thresholds.review_agreement:
            enriched.append(
                _make_issue(
                    f"rule-pack-low-agreement-{field.field_key}",
                    "RULE_LOW_EVIDENCE",
                    field.field_key,
                    "medium",
                    f"El campo {field.label} presenta acuerdo insuficiente entre motores OCR.",
                    "Revisar el campo o esperar adjudicacion adicional antes de aceptar el documento.",
                )
            )

    return enriched


def _evaluate_identity(
    normalized: NormalizedDocument,
    pack_id: str | None,
    classification_confidence: float | None,
    document_side: str | None = None,
    decision_profile: str = "balanced",
    field_signals: dict[str, FieldDecisionSignal] | None = None,
    cross_side_signal: CrossSideConsistencySignal | None = None,
    tenant_id: str | None = None,
) -> RuleEvaluation:
    values = _flatten_sections(normalized.report_sections)
    country = normalized.country.upper()
    variant = normalized.variant or ""
    pack = resolve_document_pack(pack_id=pack_id, document_family=normalized.document_family, country=normalized.country, variant=normalized.variant)
    resolved_document_side = document_side or ("front+back" if "front-back" in variant else ("back" if "-back-" in variant else "front"))
    issues: list[ValidationIssue] = []
    assumptions = ["Se aplicaron reglas deterministicas para documento de identidad por pais y variante."]

    document_number = _resolve_pack_value(values, pack, "document_number", ("numero-de-documento", "numero", "documento"))
    holder_name = derive_identity_holder_name(values, normalized.holder_name or _resolve_pack_value(values, pack, "holder_name", ("nombre-completo",)))
    birth_date = _resolve_pack_value(values, pack, "birth_date", ("fecha-de-nacimiento",))
    issue_date = _resolve_pack_value(values, pack, "issue_date", ("fecha-de-emision",))
    expiry_date = _resolve_pack_value(values, pack, "expiry_date", ("fecha-de-vencimiento",))
    sex_value = _resolve_pack_value(values, pack, "sex", ("sexo",))
    run_value = _resolve_pack_value(values, pack, "run", ("run",))
    mrz_value = _resolve_pack_value(values, pack, "mrz", ("mrz",))
    back_evidence = [
        values.get("domicilio"),
        values.get("comuna"),
        values.get("profesion"),
        values.get("circunscripcion"),
        values.get("estado-civil"),
        values.get("grado-de-instruccion"),
        values.get("donacion-de-organos"),
        values.get("restriccion"),
        values.get("lugar-de-nacimiento"),
        values.get("estatura"),
        values.get("grupo-sanguineo"),
        values.get("lugar-de-expedicion"),
    ]
    back_evidence_count = sum(1 for value in back_evidence if not _is_missing(value))
    requires_back = resolved_document_side in {"back", "front+back"}
    requires_front = resolved_document_side in {"front", "front+back"}

    if _is_missing(holder_name):
        issues.append(
            _make_issue(
                "rule-identity-missing-holder",
                "RULE_REQUIRED_FIELD",
                "holder_name",
                "high",
                "El documento de identidad no contiene un titular utilizable para validacion automatica.",
                "Corregir el nombre del titular o reprocesar el documento con mejor calidad.",
            )
        )

    if _is_missing(document_number):
        issues.append(
            _make_issue(
                "rule-identity-missing-document-number",
                "RULE_REQUIRED_FIELD",
                "document_number",
                "high",
                "No se detecto un numero documental valido en la extraccion estructurada.",
                "Verificar el OCR del identificador principal o revisar manualmente el documento.",
            )
        )
    elif country == "PE" and document_number is not None and not PE_DNI_PATTERN.search(document_number):
        issues.append(
            _make_issue(
                "rule-identity-invalid-dni-pe",
                "RULE_FORMAT",
                "document_number",
                "high",
                "El DNI peruano debe contener 8 digitos numericos.",
                "Validar el numero detectado contra el frente del documento.",
            )
        )
    elif country == "CO" and document_number is not None and not CO_CEDULA_PATTERN.search(document_number):
        issues.append(
            _make_issue(
                "rule-identity-invalid-cedula-co",
                "RULE_FORMAT",
                "document_number",
                "high",
                "La cedula colombiana debe contener entre 6 y 10 digitos.",
                "Confirmar el identificador con una segunda lectura o revision humana.",
            )
        )

    if country == "CL" and requires_front and _is_missing(run_value):
        issues.append(
            _make_issue(
                "rule-identity-missing-run-cl",
                "RULE_REQUIRED_FIELD",
                "run",
                "medium",
                "La cedula chilena deberia contener RUN legible para autoaprobacion conservadora.",
                "Verificar frente/dorso del documento o mejorar la calidad de la imagen.",
            )
        )
    elif country == "CL" and requires_front and run_value and not CL_RUT_PATTERN.search(run_value):
        issues.append(
            _make_issue(
                "rule-identity-invalid-run-cl",
                "RULE_FORMAT",
                "run",
                "high",
                "El RUN detectado no cumple el formato esperado de cedula chilena.",
                "Confirmar el RUN antes de aceptar automaticamente.",
            )
        )
    elif country == "CL" and requires_front and run_value and not validate_chile_run_checksum(run_value):
        issues.append(
            _make_issue(
                "rule-identity-invalid-run-checksum-cl",
                "RULE_CHECKSUM",
                "run",
                "high",
                "El RUN detectado no supera la validacion de digito verificador modulo 11.",
                "Confirmar el RUN antes de aceptar automaticamente.",
            )
        )

    if country == "CL" and requires_back and _is_missing(mrz_value):
        issues.append(
            _make_issue(
                "rule-identity-missing-mrz-cl",
                "RULE_LOW_EVIDENCE",
                "mrz",
                "low",
                "No se detecto MRZ o zona legible por maquina para un dorso de documento chileno.",
                "Si el flujo requiere autoaceptacion, revisar visualmente la banda MRZ del dorso.",
            )
        )

    if requires_front and _is_missing(birth_date) and _is_missing(issue_date) and _is_missing(expiry_date):
        issues.append(
            _make_issue(
                "rule-identity-missing-dates",
                "RULE_REQUIRED_FIELD",
                "dates",
                "medium",
                "No se detectaron fechas suficientes para validar identidad y vigencia.",
                "Revisar visualmente el documento o aumentar la calidad del OCR.",
            )
        )

    if country == "CL" and resolved_document_side == "front" and _is_missing(sex_value):
        issues.append(
            _make_issue(
                "rule-identity-missing-sex-front",
                "RULE_LOW_EVIDENCE",
                "sexo",
                "medium",
                "No se detecto el sexo en el frente de la cedula chilena.",
                "Reintentar OCR focalizado en el bloque central derecho antes de autoaceptar el documento.",
            )
        )

    if country == "CL" and resolved_document_side == "front" and _is_missing(issue_date):
        issues.append(
            _make_issue(
                "rule-identity-missing-issue-date-front",
                "RULE_REQUIRED_FIELD",
                "fecha_de_emision",
                "medium",
                "No se detecto una fecha de emision confiable en el frente de la cedula chilena.",
                "Reintentar OCR focalizado sobre el bloque de fechas antes de autoaceptar el documento.",
            )
        )

    if requires_back and back_evidence_count == 0:
        issues.append(
            _make_issue(
                "rule-identity-missing-back-evidence",
                "RULE_LOW_EVIDENCE",
                "reverse_fields",
                "medium",
                "Se esperaba evidencia del dorso del documento, pero no se detectaron campos reversos suficientes.",
                "Verificar si el archivo incluye el dorso o separar las paginas del documento.",
            )
        )

    if resolved_document_side == "front+back" and cross_side_signal:
        if cross_side_signal.identifier_match is False:
            issues.append(
                _make_issue(
                    "rule-identity-cross-side-identifier-mismatch",
                    "RULE_CROSS_SIDE_MISMATCH",
                    "document_number",
                    "high",
                    "El identificador detectado en frente y dorso no coincide.",
                    "Confirmar el numero documental antes de cualquier autoaprobacion.",
                )
            )
        elif cross_side_signal.identifier_match is None:
            issues.append(
                _make_issue(
                    "rule-identity-cross-side-identifier-missing",
                    "RULE_LOW_EVIDENCE",
                    "document_number",
                    "medium",
                    "No fue posible comparar un identificador consistente entre frente y dorso.",
                    "Mantener warning o revision hasta contar con evidencia comparable en ambos lados.",
                )
            )

    parsed_dates = _extract_dates(values)
    if len(parsed_dates) >= 2:
        sorted_dates = sorted(parsed_dates)
        if issue_date and expiry_date:
            try:
                issue = date.fromisoformat(issue_date)
                expiry = date.fromisoformat(expiry_date)
                if expiry <= issue:
                    issues.append(
                        _make_issue(
                            "rule-identity-date-order",
                            "RULE_DATE_CONSISTENCY",
                            "fecha_de_vencimiento",
                            "medium" if resolved_document_side == "front" else "high",
                            "La fecha de vencimiento no puede ser anterior o igual a la fecha de emision.",
                            "Reintentar OCR focalizado sobre el bloque de fechas o corregir las fechas detectadas antes de aceptar el caso.",
                        )
                    )
            except ValueError:
                pass
        if birth_date and issue_date:
            try:
                birth = date.fromisoformat(birth_date)
                issue = date.fromisoformat(issue_date)
                if birth >= issue:
                    issues.append(
                        _make_issue(
                            "rule-identity-birth-after-issue",
                            "RULE_DATE_CONSISTENCY",
                            "fecha_de_nacimiento",
                            "high",
                            "La fecha de nacimiento no puede ser posterior a la fecha de emision.",
                            "Corregir o confirmar manualmente las fechas del documento.",
                        )
                    )
            except ValueError:
                pass

    issues = _append_pack_field_issues(issues, pack, values, field_signals)
    merged_issues = _merge_issues(normalized.issues, issues)
    severity_set = {issue.severity for issue in merged_issues}
    medium_issues = [issue for issue in merged_issues if issue.severity == "medium"]
    critical_field_defs = [field for field in (pack.expected_fields if pack else ()) if field.critical]
    agreement_field_defs = critical_field_defs
    if resolved_document_side == "front+back" and cross_side_signal and cross_side_signal.identifier_match is True:
        agreement_field_defs = [field for field in critical_field_defs if field.field_key != "holder_name"]
    critical_field_names = {_slugify(field.field_key) for field in critical_field_defs}
    blocking_medium_issues = [
        issue
        for issue in medium_issues
        if issue.type not in WARNING_AUTO_ACCEPT_TYPES
        and not (issue.type == "RULE_REQUIRED_FIELD" and _slugify(issue.field) not in critical_field_names)
    ]
    weighted_confidence = (normalized.global_confidence * 0.82) + ((classification_confidence or 0.0) * 0.18)
    if pack:
        base_confidence = max(weighted_confidence, normalized.global_confidence - 0.02)
    else:
        base_confidence = weighted_confidence
    profile = _normalize_decision_profile(decision_profile)
    pack_thresholds = pack.decision_thresholds if pack else None
    configured_thresholds = resolve_decision_thresholds(
        tenant_id=tenant_id,
        document_family=normalized.document_family,
        country=normalized.country,
        pack_id=pack_id,
        defaults=DecisionThresholdSettings(
            reject_confidence=0.45 if profile == "strict" else 0.4 if profile == "balanced" else 0.34,
            accept_with_warning_confidence=(
                min(0.98, pack_thresholds.accept_with_warning_confidence + (0.02 if profile == "strict" else -0.02 if profile == "aggressive" else 0.0))
                if pack_thresholds
                else (0.92 if profile == "strict" else 0.9 if profile == "balanced" else 0.84)
            ),
            auto_accept_confidence=(
                min(0.99, pack_thresholds.auto_accept_confidence + (0.02 if profile == "strict" else -0.02 if profile == "aggressive" else 0.0))
                if pack_thresholds
                else (0.96 if profile == "strict" else 0.94 if profile == "balanced" else 0.9)
            ),
            auto_accept_agreement=(
                max(0.0, pack_thresholds.auto_accept_agreement + (0.05 if profile == "strict" else -0.05 if profile == "aggressive" else 0.0))
                if pack_thresholds
                else (0.9 if profile == "strict" else 0.85 if profile == "balanced" else 0.75)
            ),
            review_agreement=(
                pack_thresholds.review_agreement if pack_thresholds else (0.65 if profile == "strict" else 0.55 if profile == "balanced" else 0.45)
            ),
            cross_side_confidence=0.9 if profile == "strict" else 0.86 if profile == "balanced" else 0.8,
        ),
    )
    accept_threshold = configured_thresholds.accept_with_warning_confidence
    cross_side_threshold = configured_thresholds.cross_side_confidence
    reject_threshold = configured_thresholds.reject_confidence
    auto_accept_threshold = configured_thresholds.auto_accept_confidence
    critical_agreement_values = [
        _field_signal(field_signals, field.field_key).agreement_ratio
        for field in agreement_field_defs
        if _field_signal(field_signals, field.field_key).candidate_count > 0
    ]
    minimum_agreement = min(critical_agreement_values) if critical_agreement_values else 1.0
    critical_fields_complete = all(
        not _is_missing(_resolve_pack_value(values, pack, field.field_key))
        for field in critical_field_defs
    )
    strong_critical_support = sum(
        1
        for field in critical_field_defs
        if (signal := _field_signal(field_signals, field.field_key)).agreement_ratio >= 0.67 and len(signal.supporting_engines) >= 2
    )
    required_back_fields_met = not pack or pack.min_back_fields == 0 or back_evidence_count >= pack.min_back_fields
    minimum_auto_accept_agreement = configured_thresholds.auto_accept_agreement
    cross_side_confirmed = resolved_document_side != "front+back" or (cross_side_signal is not None and cross_side_signal.identifier_match is True)
    run_checksum_valid = country == "CL" and run_value is not None and validate_chile_run_checksum(run_value)
    mrz_checksum_valid = validate_mrz_check_digits(mrz_value) if mrz_value else False
    adaptive_auto_accept_threshold = configured_thresholds.auto_accept_confidence
    if tenant_id:
        adaptive_auto_accept_threshold = configured_thresholds.auto_accept_confidence
    elif run_checksum_valid:
        adaptive_auto_accept_threshold -= 0.03
    if not tenant_id and mrz_checksum_valid:
        adaptive_auto_accept_threshold -= 0.04
    if not tenant_id and critical_field_defs and strong_critical_support == len(critical_field_defs):
        adaptive_auto_accept_threshold -= 0.02
    if not tenant_id and cross_side_signal and cross_side_signal.identifier_match is True:
        adaptive_auto_accept_threshold -= 0.01
    adaptive_auto_accept_threshold = max(0.84, round(adaptive_auto_accept_threshold, 3))
    auto_accept_blockers = [issue for issue in merged_issues if _is_auto_accept_blocker(issue, critical_field_names)]

    if normalized.global_confidence < reject_threshold:
        decision = cast(DocumentDecision, "reject")
    elif "high" in severity_set:
        decision = cast(DocumentDecision, "human_review")
    elif blocking_medium_issues and resolved_document_side != "front+back":
        decision = cast(DocumentDecision, "human_review")
    elif (
        country in {"CL", "PE", "CO"}
        and critical_fields_complete
        and required_back_fields_met
        and cross_side_confirmed
        and base_confidence >= adaptive_auto_accept_threshold
        and minimum_agreement >= minimum_auto_accept_agreement
        and not auto_accept_blockers
    ):
        decision = cast(DocumentDecision, "auto_accept")
    elif medium_issues and base_confidence >= accept_threshold and critical_fields_complete:
        decision = cast(DocumentDecision, "accept_with_warning")
    elif resolved_document_side == "front+back" and back_evidence_count > 0 and base_confidence >= cross_side_threshold:
        decision = cast(DocumentDecision, "accept_with_warning")
    elif base_confidence >= accept_threshold and country in {"CL", "PE", "CO"} and critical_fields_complete:
        decision = cast(DocumentDecision, "accept_with_warning")
    else:
        decision = cast(DocumentDecision, "human_review")

    assumptions.append(f"Rule pack aplicado: {pack_id or 'identity-generic'}.")
    assumptions.append(f"Evaluacion side-aware: {resolved_document_side}.")
    assumptions.append(f"Perfil de decision: {profile}.")
    assumptions.append(f"Agreement minimo en campos criticos: {minimum_agreement:.2f}.")
    if tenant_id:
        assumptions.append(f"Threshold policy evaluada para tenant: {tenant_id}.")
    if cross_side_signal:
        assumptions.extend(cross_side_signal.assumptions)
    return RuleEvaluation(
        rule_pack_id=pack_id or "identity-generic",
        issues=merged_issues,
        decision=decision,
        review_required=decision in {"human_review", "reject"},
        assumptions=assumptions,
    )


def _collect_certificate_evidence(values: dict[str, str]) -> tuple[int, int]:
    amount_count = 0
    period_count = 0
    for key, value in values.items():
        if _is_missing(value):
            continue
        if any(char.isdigit() for char in value) and any(char in value for char in ",."):
            amount_count += 1
        if "202" in value or "periodo" in key:
            period_count += 1
    return amount_count, period_count


def _count_certificate_contribution_rows(values: dict[str, str]) -> int:
    row_keys = [key for key in values if key.endswith("-rut-empleador") or key.endswith("-fondo-pensiones") or key.endswith("-renta-imponible")]
    return len({key.rsplit("-", 1)[0] for key in row_keys})


def _evaluate_certificate(
    normalized: NormalizedDocument,
    pack_id: str | None,
    classification_confidence: float | None,
    decision_profile: str = "balanced",
    field_signals: dict[str, FieldDecisionSignal] | None = None,
    tenant_id: str | None = None,
) -> RuleEvaluation:
    values = _flatten_sections(normalized.report_sections)
    pack = resolve_document_pack(pack_id=pack_id, document_family=normalized.document_family, country=normalized.country, variant=normalized.variant)
    country = normalized.country.upper()
    issues: list[ValidationIssue] = []
    assumptions = ["Se aplicaron reglas deterministicas para certificado/comprobante por pais y pack documental."]

    holder_name = normalized.holder_name or values.get("titular") or values.get("nombre-completo")
    issuer = normalized.issuer or values.get("emisor")
    certificate_number = _resolve_pack_value(values, pack, "certificate_number", ("numero-de-certificado",))
    issue_date = _resolve_pack_value(values, pack, "issue_date", ("fecha-de-emision",))
    account = _resolve_pack_value(values, pack, "account", ("cuenta",))
    identifiers = [
        values.get("rut"),
        values.get("rut-del-afiliado"),
        account,
        values.get("cuenta-de-cotizacion"),
        certificate_number,
        values.get("numero-de-documento"),
    ]
    amount_count, period_count = _collect_certificate_evidence(values)
    contribution_row_count = _count_certificate_contribution_rows(values)

    if _is_missing(holder_name):
        issues.append(
            _make_issue(
                "rule-certificate-missing-holder",
                "RULE_REQUIRED_FIELD",
                "holder_name",
                "medium",
                "No se detecto un titular claro para el certificado procesado.",
                "Confirmar el titular manualmente o mejorar el OCR del encabezado.",
            )
        )

    if _is_missing(issuer):
        issues.append(
            _make_issue(
                "rule-certificate-missing-issuer",
                "RULE_REQUIRED_FIELD",
                "issuer",
                "medium",
                "El certificado no contiene un emisor suficientemente claro para autoaprobacion.",
                "Verificar el encabezado o aplicar un extractor especifico para este emisor.",
            )
        )

    if not any(not _is_missing(value) for value in identifiers):
        issues.append(
            _make_issue(
                "rule-certificate-missing-identifiers",
                "RULE_REQUIRED_FIELD",
                "identifiers",
                "high",
                "No se detectaron identificadores estructurados suficientes en el certificado.",
                "Revisar el OCR del documento o mantener el caso en revision humana.",
            )
        )

    if pack and pack.pack_id == "certificate-cl-previsional":
        if _is_missing(certificate_number):
            issues.append(
                _make_issue(
                    "rule-certificate-missing-certificate-number",
                    "RULE_REQUIRED_FIELD",
                    "certificate_number",
                    "medium",
                    "El certificado previsional no contiene un numero de certificado extraible.",
                    "Confirmar el numero de certificado en el encabezado antes de aceptar automaticamente.",
                )
            )
        if _is_missing(issue_date):
            issues.append(
                _make_issue(
                    "rule-certificate-missing-issue-date",
                    "RULE_REQUIRED_FIELD",
                    "issue_date",
                    "medium",
                    "El certificado previsional no contiene una fecha de emision suficientemente clara.",
                    "Revisar el encabezado o extraer una fecha de emision valida desde la primera pagina.",
                )
            )
        if contribution_row_count < 3:
            issues.append(
                _make_issue(
                    "rule-certificate-insufficient-contribution-rows",
                    "RULE_LOW_EVIDENCE",
                    "contribution_rows",
                    "medium",
                    "El certificado previsional no aporta suficientes filas de cotizacion estructuradas para una validacion fuerte.",
                    "Reprocesar con extractor AFP o OCR visual antes de aceptar automaticamente.",
                )
            )

    if country == "CL":
        rut_candidate = next((value for value in identifiers if value and CL_RUT_PATTERN.search(value)), None)
        if not rut_candidate:
            issues.append(
                _make_issue(
                    "rule-certificate-missing-rut-cl",
                    "RULE_FORMAT",
                    "rut",
                    "medium",
                    "Los certificados chilenos requieren al menos un RUT legible para trazabilidad.",
                    "Confirmar el RUT del afiliado o del empleador antes de aceptar el documento.",
                )
            )

    if amount_count == 0:
        issues.append(
            _make_issue(
                "rule-certificate-missing-amounts",
                "RULE_LOW_EVIDENCE",
                "amounts",
                "medium",
                "No se detectaron montos estructurables suficientes en el certificado.",
                "Reprocesar con OCR visual o revisar si el documento corresponde a otra variante.",
            )
        )

    if period_count == 0:
        issues.append(
            _make_issue(
                "rule-certificate-missing-periods",
                "RULE_LOW_EVIDENCE",
                "dates",
                "low",
                "El certificado no ofrece periodos o fechas suficientes para validacion automatica fuerte.",
                "Revisar manualmente los periodos o ajustar el extractor del pack.",
            )
        )

    issues = _append_pack_field_issues(issues, pack, values, field_signals)
    merged_issues = _merge_issues(normalized.issues, issues)
    severity_set = {issue.severity for issue in merged_issues}
    base_confidence = (normalized.global_confidence * 0.82) + ((classification_confidence or 0.0) * 0.18)
    profile = _normalize_decision_profile(decision_profile)
    pack_thresholds = pack.decision_thresholds if pack else None
    configured_thresholds = resolve_decision_thresholds(
        tenant_id=tenant_id,
        document_family=normalized.document_family,
        country=normalized.country,
        pack_id=pack_id,
        defaults=DecisionThresholdSettings(
            reject_confidence=0.48 if profile == "strict" else 0.42 if profile == "balanced" else 0.36,
            accept_with_warning_confidence=(
                min(0.98, pack_thresholds.accept_with_warning_confidence + (0.02 if profile == "strict" else -0.02 if profile == "aggressive" else 0.0))
                if pack_thresholds
                else (0.78 if profile == "strict" else 0.72 if profile == "balanced" else 0.66)
            ),
            auto_accept_confidence=(
                min(0.99, pack_thresholds.auto_accept_confidence + (0.02 if profile == "strict" else -0.02 if profile == "aggressive" else 0.0))
                if pack_thresholds
                else (0.91 if profile == "strict" else 0.87 if profile == "balanced" else 0.8)
            ),
            auto_accept_agreement=(
                max(0.0, pack_thresholds.auto_accept_agreement + (0.05 if profile == "strict" else -0.05 if profile == "aggressive" else 0.0))
                if pack_thresholds
                else 0.8
            ),
            review_agreement=pack_thresholds.review_agreement if pack_thresholds else 0.5,
            cross_side_confidence=0.8,
        ),
    )
    reject_threshold = configured_thresholds.reject_confidence
    warning_threshold = configured_thresholds.accept_with_warning_confidence
    auto_accept_threshold = configured_thresholds.auto_accept_confidence
    auto_accept_blockers = [issue for issue in merged_issues if _is_auto_accept_blocker(issue)]

    if normalized.global_confidence < reject_threshold:
        decision = cast(DocumentDecision, "reject")
    elif "high" in severity_set:
        decision = cast(DocumentDecision, "human_review")
    elif "medium" in severity_set and base_confidence < 0.8:
        decision = cast(DocumentDecision, "human_review")
    elif not auto_accept_blockers and base_confidence >= auto_accept_threshold:
        decision = cast(DocumentDecision, "auto_accept")
    elif base_confidence >= warning_threshold:
        decision = cast(DocumentDecision, "accept_with_warning")
    else:
        decision = cast(DocumentDecision, "human_review")

    if contribution_row_count:
        assumptions.append(f"Filas de cotizacion estructuradas detectadas: {contribution_row_count}.")
    assumptions.append(f"Rule pack aplicado: {pack_id or 'certificate-generic'}.")
    assumptions.append(f"Perfil de decision: {profile}.")
    if tenant_id:
        assumptions.append(f"Threshold policy evaluada para tenant: {tenant_id}.")
    return RuleEvaluation(
        rule_pack_id=pack_id or "certificate-generic",
        issues=merged_issues,
        decision=decision,
        review_required=decision in {"human_review", "accept_with_warning", "reject"},
        assumptions=assumptions,
    )


def _evaluate_passport(
    normalized: NormalizedDocument,
    pack_id: str | None,
    classification_confidence: float | None,
    decision_profile: str = "balanced",
    tenant_id: str | None = None,
) -> RuleEvaluation:
    values = _flatten_sections(normalized.report_sections)
    pack = resolve_document_pack(pack_id=pack_id, document_family=normalized.document_family, country=normalized.country, variant=normalized.variant)
    issues: list[ValidationIssue] = []
    assumptions = ["Se aplicaron reglas genericas de pasaporte con foco en numero documental, fechas y MRZ."]

    holder_name = normalized.holder_name or _resolve_pack_value(values, pack, "holder_name", ("nombre-completo",))
    document_number = _resolve_pack_value(values, pack, "document_number", ("numero-de-documento", "passport-number"))
    birth_date = _resolve_pack_value(values, pack, "birth_date", ("fecha-de-nacimiento",))
    expiry_date = _resolve_pack_value(values, pack, "expiry_date", ("fecha-de-vencimiento",))
    mrz = _resolve_pack_value(values, pack, "mrz", ("mrz",))

    if _is_missing(holder_name):
        issues.append(_make_issue("passport-missing-holder", "RULE_REQUIRED_FIELD", "holder_name", "medium", "No se detecto titular claro del pasaporte.", "Verificar la pagina de datos o la MRZ."))
    if _is_missing(document_number):
        issues.append(_make_issue("passport-missing-document", "RULE_REQUIRED_FIELD", "document_number", "high", "No se detecto numero de pasaporte legible.", "Confirmar numero documental antes de aceptar."))
    if _is_missing(expiry_date):
        issues.append(_make_issue("passport-missing-expiry", "RULE_REQUIRED_FIELD", "expiry_date", "medium", "No se detecto fecha de vencimiento del pasaporte.", "Verificar fechas visuales o MRZ."))
    if _is_missing(mrz):
        issues.append(_make_issue("passport-missing-mrz", "RULE_LOW_EVIDENCE", "mrz", "low", "No se detecto MRZ valida en el pasaporte.", "Mantener warning o revisar MRZ manualmente."))
    if _is_missing(birth_date):
        issues.append(_make_issue("passport-missing-birth", "RULE_LOW_EVIDENCE", "birth_date", "low", "No se detecto fecha de nacimiento clara.", "Verificar datos visuales o MRZ."))
    if not _is_missing(mrz) and not validate_mrz_check_digits(mrz):
        issues.append(_make_issue("passport-invalid-mrz-checksum", "RULE_CHECKSUM", "mrz", "high", "La MRZ detectada no supera las validaciones ICAO de check digit.", "Reprocesar la zona MRZ o confirmar manualmente antes de aceptar."))

    mrz_consistency_hits = 0
    if feature_enabled("mrz_cross_validation"):
        parsed_mrz = parse_passport_mrz(mrz or "") if not _is_missing(mrz) else {"document_number": None, "holder_name": None, "birth_date": None, "expiry_date": None}
        if parsed_mrz.get("document_number") and document_number:
            if canonicalize_passport_number(parsed_mrz.get("document_number")) != canonicalize_passport_number(document_number):
                issues.append(
                    _make_issue(
                        "passport-mrz-document-mismatch",
                        "RULE_CROSS_FIELD_MISMATCH",
                        "document_number",
                        "high",
                        "El numero documental del pasaporte no coincide con el valor derivado desde la MRZ.",
                        "Confirmar la zona MRZ y el numero visual antes de aceptar automaticamente.",
                    )
                )
            else:
                mrz_consistency_hits += 1
        if parsed_mrz.get("birth_date") and birth_date:
            if parsed_mrz.get("birth_date") != birth_date:
                issues.append(
                    _make_issue(
                        "passport-mrz-birth-mismatch",
                        "RULE_CROSS_FIELD_MISMATCH",
                        "birth_date",
                        "medium",
                        "La fecha de nacimiento visual no coincide con la fecha derivada desde la MRZ.",
                        "Verificar el campo de nacimiento antes de aceptar automaticamente.",
                    )
                )
            else:
                mrz_consistency_hits += 1
        if parsed_mrz.get("expiry_date") and expiry_date:
            if parsed_mrz.get("expiry_date") != expiry_date:
                issues.append(
                    _make_issue(
                        "passport-mrz-expiry-mismatch",
                        "RULE_CROSS_FIELD_MISMATCH",
                        "expiry_date",
                        "high",
                        "La fecha de vencimiento visual no coincide con la fecha derivada desde la MRZ.",
                        "Confirmar la vigencia del pasaporte antes de autoaceptar.",
                    )
                )
            else:
                mrz_consistency_hits += 1
        if parsed_mrz.get("holder_name") and holder_name:
            if _compact(parsed_mrz.get("holder_name")) != _compact(holder_name):
                issues.append(
                    _make_issue(
                        "passport-mrz-holder-mismatch",
                        "RULE_CROSS_FIELD_MISMATCH",
                        "holder_name",
                        "medium",
                        "El nombre del titular no coincide con la lectura de la MRZ.",
                        "Confirmar el nombre principal antes de aceptar automaticamente.",
                    )
                )
            else:
                mrz_consistency_hits += 1

    merged_issues = _merge_issues(normalized.issues, issues)
    severity_set = {issue.severity for issue in merged_issues}
    medium_issues = [issue for issue in merged_issues if issue.severity == "medium"]
    weighted_confidence = (normalized.global_confidence * 0.82) + ((classification_confidence or 0.0) * 0.18)
    base_confidence = max(weighted_confidence, normalized.global_confidence - 0.02)
    profile = _normalize_decision_profile(decision_profile)
    configured_thresholds = resolve_decision_thresholds(
        tenant_id=tenant_id,
        document_family=normalized.document_family,
        country=normalized.country,
        pack_id=pack_id,
        defaults=DecisionThresholdSettings(
            reject_confidence=0.42 if profile == "balanced" else 0.36,
            accept_with_warning_confidence=0.82 if profile == "balanced" else 0.76,
            auto_accept_confidence=0.93 if profile == "balanced" else 0.9,
            auto_accept_agreement=0.8,
            review_agreement=0.45,
            cross_side_confidence=0.8,
        ),
    )
    adaptive_auto_accept_threshold = configured_thresholds.auto_accept_confidence - (0.04 if not tenant_id and validate_mrz_check_digits(mrz) else 0.0)
    if not tenant_id and mrz_consistency_hits >= 3:
        adaptive_auto_accept_threshold -= 0.03
    adaptive_auto_accept_threshold = max(0.88, round(adaptive_auto_accept_threshold, 3))
    auto_accept_blockers = [issue for issue in merged_issues if _is_auto_accept_blocker(issue, {"holder_name", "document_number", "mrz"})]

    if normalized.global_confidence < configured_thresholds.reject_confidence:
        decision = cast(DocumentDecision, "reject")
    elif "high" in severity_set:
        decision = cast(DocumentDecision, "human_review")
    elif not auto_accept_blockers and base_confidence >= adaptive_auto_accept_threshold:
        decision = cast(DocumentDecision, "auto_accept")
    elif base_confidence >= configured_thresholds.accept_with_warning_confidence and len(medium_issues) <= 1:
        decision = cast(DocumentDecision, "accept_with_warning")
    else:
        decision = cast(DocumentDecision, "human_review")

    assumptions.append(f"Rule pack aplicado: {pack_id or 'passport-generic'}.")
    if mrz_consistency_hits > 0:
        assumptions.append(f"Cross-validation MRZ consistente en {mrz_consistency_hits} campo(s) clave del pasaporte.")
    return RuleEvaluation(
        rule_pack_id=pack_id or "passport-generic",
        issues=merged_issues,
        decision=decision,
        review_required=decision in {"human_review", "reject"},
        assumptions=assumptions,
    )


def _evaluate_driver_license(
    normalized: NormalizedDocument,
    pack_id: str | None,
    classification_confidence: float | None,
    decision_profile: str = "balanced",
    tenant_id: str | None = None,
) -> RuleEvaluation:
    values = _flatten_sections(normalized.report_sections)
    pack = resolve_document_pack(pack_id=pack_id, document_family=normalized.document_family, country=normalized.country, variant=normalized.variant)
    issues: list[ValidationIssue] = []
    assumptions = ["Se aplicaron reglas genericas de licencia de conducir."]

    holder_name = normalized.holder_name or _resolve_pack_value(values, pack, "holder_name", ("nombre-completo",))
    document_number = _resolve_pack_value(values, pack, "document_number", ("numero-de-documento", "license-number"))
    expiry_date = _resolve_pack_value(values, pack, "expiry_date", ("fecha-de-vencimiento",))

    if _is_missing(holder_name):
        issues.append(_make_issue("driver-missing-holder", "RULE_REQUIRED_FIELD", "holder_name", "medium", "No se detecto titular claro en la licencia.", "Verificar el nombre principal del documento."))
    if _is_missing(document_number):
        issues.append(_make_issue("driver-missing-document", "RULE_REQUIRED_FIELD", "document_number", "high", "No se detecto numero de licencia legible.", "Confirmar el numero antes de aceptar."))
    if _is_missing(expiry_date):
        issues.append(_make_issue("driver-missing-expiry", "RULE_LOW_EVIDENCE", "expiry_date", "low", "No se detecto fecha de vencimiento clara.", "Mantener warning o revisar visualmente."))
    if normalized.country.upper() == "CL" and document_number and not validate_chile_run_checksum(document_number):
        issues.append(_make_issue("driver-invalid-id-checksum-cl", "RULE_CHECKSUM", "document_number", "high", "El identificador chileno de la licencia no supera modulo 11.", "Confirmar el RUT o reintentar OCR."))

    merged_issues = _merge_issues(normalized.issues, issues)
    severity_set = {issue.severity for issue in merged_issues}
    medium_issues = [issue for issue in merged_issues if issue.severity == "medium"]
    profile = _normalize_decision_profile(decision_profile)
    base_confidence = max((normalized.global_confidence * 0.82) + ((classification_confidence or 0.0) * 0.18), normalized.global_confidence - 0.02)
    configured_thresholds = resolve_decision_thresholds(
        tenant_id=tenant_id,
        document_family=normalized.document_family,
        country=normalized.country,
        pack_id=pack_id,
        defaults=DecisionThresholdSettings(
            reject_confidence=0.4 if profile == "balanced" else 0.34,
            accept_with_warning_confidence=0.8 if profile == "balanced" else 0.74,
            auto_accept_confidence=0.92 if profile == "balanced" else 0.88,
            auto_accept_agreement=0.76,
            review_agreement=0.42,
            cross_side_confidence=0.8,
        ),
    )
    adaptive_auto_accept_threshold = configured_thresholds.auto_accept_confidence - (
        0.03 if not tenant_id and normalized.country.upper() == "CL" and document_number and validate_chile_run_checksum(document_number) else 0.0
    )
    adaptive_auto_accept_threshold = max(0.87, round(adaptive_auto_accept_threshold, 3))
    auto_accept_blockers = [issue for issue in merged_issues if _is_auto_accept_blocker(issue, {"holder_name", "document_number"})]

    if normalized.global_confidence < configured_thresholds.reject_confidence:
        decision = cast(DocumentDecision, "reject")
    elif "high" in severity_set:
        decision = cast(DocumentDecision, "human_review")
    elif not auto_accept_blockers and base_confidence >= adaptive_auto_accept_threshold:
        decision = cast(DocumentDecision, "auto_accept")
    elif base_confidence >= configured_thresholds.accept_with_warning_confidence and len(medium_issues) <= 1:
        decision = cast(DocumentDecision, "accept_with_warning")
    else:
        decision = cast(DocumentDecision, "human_review")

    assumptions.append(f"Rule pack aplicado: {pack_id or 'driver-license-generic'}.")
    return RuleEvaluation(
        rule_pack_id=pack_id or "driver-license-generic",
        issues=merged_issues,
        decision=decision,
        review_required=decision in {"human_review", "reject"},
        assumptions=assumptions,
    )


def evaluate_normalized_document(
    normalized: NormalizedDocument,
    pack_id: str | None = None,
    classification_confidence: float | None = None,
    document_side: str | None = None,
    decision_profile: str | None = None,
    field_signals: dict[str, FieldDecisionSignal] | None = None,
    cross_side_signal: CrossSideConsistencySignal | None = None,
    tenant_id: str | None = None,
) -> RuleEvaluation:
    pack = resolve_document_pack(pack_id=pack_id, document_family=normalized.document_family, country=normalized.country, variant=normalized.variant)
    resolved_pack_id = pack.pack_id if pack else pack_id
    profile = _normalize_decision_profile(decision_profile)

    if normalized.document_family == "identity":
        return _evaluate_identity(
            normalized,
            resolved_pack_id,
            classification_confidence,
            document_side=document_side,
            decision_profile=profile,
            field_signals=field_signals,
            cross_side_signal=cross_side_signal,
            tenant_id=tenant_id,
        )

    if normalized.document_family == "certificate":
        return _evaluate_certificate(
            normalized,
            resolved_pack_id,
            classification_confidence,
            decision_profile=profile,
            field_signals=field_signals,
            tenant_id=tenant_id,
        )

    if normalized.document_family == "passport":
        return _evaluate_passport(normalized, resolved_pack_id, classification_confidence, decision_profile=profile, tenant_id=tenant_id)

    if normalized.document_family == "driver_license":
        return _evaluate_driver_license(normalized, resolved_pack_id, classification_confidence, decision_profile=profile, tenant_id=tenant_id)

    issues = _merge_issues(
        normalized.issues,
        [
            _make_issue(
                "rule-pack-unsupported-family",
                "UNSUPPORTED_DOCUMENT",
                "document_family",
                "high",
                "La familia documental no dispone de un rule pack deterministico para validacion automatica.",
                "Mantener el documento en review o implementar un rule pack especifico.",
            )
        ],
    )
    return RuleEvaluation(
        rule_pack_id=resolved_pack_id,
        issues=issues,
        decision=cast(DocumentDecision, "human_review"),
        review_required=True,
        assumptions=["No existe un rule pack especifico para esta familia documental.", f"Perfil de decision: {profile}."],
    )


def build_normalized_document_from_field_map(document_family: str, country: str, variant: str | None, normalized_fields: dict[str, str]) -> NormalizedDocument:
    summary_rows = [[key, value] for key, value in normalized_fields.items()]
    return NormalizedDocument(
        document_family=document_family,
        country=country,
        variant=variant,
        issuer=normalized_fields.get("issuer"),
        holder_name=normalized_fields.get("holder_name") or normalized_fields.get("nombre_completo") or normalized_fields.get("titular"),
        global_confidence=0.75,
        assumptions=["Se construyo un documento normalizado temporal a partir de campos planos para ejecutar el rule pack."],
        issues=[],
        report_sections=[ReportSection(id="summary", title="Summary", variant="pairs", rows=summary_rows)],
        human_summary=None,
    )


def evaluate_normalized_fields(
    document_family: str,
    country: str,
    variant: str | None,
    normalized_fields: dict[str, str],
    pack_id: str | None = None,
    classification_confidence: float | None = None,
    document_side: str | None = None,
    decision_profile: str | None = None,
    field_signals: dict[str, FieldDecisionSignal] | None = None,
    tenant_id: str | None = None,
) -> RuleEvaluation:
    normalized_document = build_normalized_document_from_field_map(document_family, country, variant, normalized_fields)
    return evaluate_normalized_document(
        normalized_document,
        pack_id=pack_id,
        classification_confidence=classification_confidence,
        document_side=document_side,
        decision_profile=decision_profile,
        field_signals=field_signals,
        tenant_id=tenant_id,
    )
