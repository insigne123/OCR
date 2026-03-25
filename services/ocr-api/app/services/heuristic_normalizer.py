from __future__ import annotations

from datetime import date
import re

from app.schemas import NormalizedDocument, ReportSection, ValidationIssue, ValidationSeverity
from app.services.document_packs import resolve_document_pack
from app.services.field_value_utils import (
    canonicalize_chile_run,
    canonicalize_identity_document_number,
    canonicalize_passport_number,
    clean_value,
    is_placeholder_name,
    normalize_date_value,
    parse_identity_card_mrz,
    parse_passport_mrz,
    strip_accents,
    validate_chile_run_checksum,
    validate_mrz_check_digits,
)

RUT_PATTERN = re.compile(r"(?:RUN|RUT)?\s*(\d{1,2}[.,]?(?:\d{3})[.,]?(?:\d{3})\s*-\s*[\dkK])", re.IGNORECASE)
ACCOUNT_PATTERN = re.compile(r"\b\d{4}-\d{4}-\d{8,}\b")
PERIOD_PATTERN = re.compile(r"\b20\d{2}[-/]\d{2}\b")
MONTH_PERIOD_PATTERN = re.compile(r"\b(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|SET|OCT|NOV|DIC)[-/]20\d{2}\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b20\d{2}[-/]\d{2}[-/]\d{2}\b")
COMPACT_DATE_PATTERN = re.compile(r"\b\d{2}\s*[A-Z]{3}\s*\d{4}\b")
SPACE_DATE_PATTERN = re.compile(r"\b\d{2}\s+\d{2}\s+\d{4}\b")
AMOUNT_PATTERN = re.compile(r"\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?\b")
UPPERCASE_LINE_PATTERN = re.compile(r"^[A-ZÁÉÍÓÚÜÑ ]{8,}$")
DOCUMENT_NUMBER_PATTERN = re.compile(r"\b[A-Z]{1,2}\d{1,3}\.\d{3}\.\d{3}\b")
PE_DNI_PATTERN = re.compile(r"\b\d{8}\b")
CO_CEDULA_PATTERN = re.compile(r"\b\d{6,10}\b")
CO_CEDULA_FLEX_PATTERN = re.compile(r"\b(?:\d{1,3}(?:[.,]\d{3}){1,3}|\d{6,10})\b")
ISO_DATE_PATTERN = re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b")
LATAM_DATE_PATTERN = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")

MONTH_MAP = {
    "ENE": "01",
    "FEB": "02",
    "MAR": "03",
    "ABR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AGO": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DIC": "12",
}

IDENTITY_STOP_TOKENS = {
    "CEDULADEIDENTIDAD",
    "DOCUMENTODEIDENTIDAD",
    "REPUBLICADECHILE",
    "SERVICIODEREGISTROCIVILEIDENTIFICACION",
    "APELLIDOS",
    "NOMBRES",
    "NACIONALIDAD",
    "SEXO",
    "NUMERODOCUMENTO",
    "NUMERODEDOCUMENTO",
    "FECHADENACIMIENTO",
    "FECHADEEMISION",
    "FECHADEVENCIMIENTO",
    "FIRMADELTITULAR",
    "RUN",
    "IDENTIDAD",
    "CHILENA",
    "CHILENO",
    "CEDULA",
    "CEDULADE",
    "FIRMADELTITULAR",
    "FECHADE",
    "FECHA",
    "NUMERO",
    "NUMERODOCUMENTO",
}

PASSPORT_NUMBER_PATTERN = re.compile(r"\b[A-Z]{1,2}\d{7,8}\b")
TEXTUAL_LONG_DATE_PATTERN = re.compile(r"\b\d{2}\s*[A-Z]{3}\s*\d{4}\b")
LONG_SPANISH_DATE_PATTERN = re.compile(r"\b\d{1,2}\s+DE\s+[A-Z]{3,12}\s+DE\s+\d{4}\b", re.IGNORECASE)
AFP_CERTIFICATE_NUMBER_PATTERN = re.compile(r"NUMERO DE CERTIFICADO[:\s]+((?:\d{1,3}[.,])*\d{3})", re.IGNORECASE)
AFP_HOLDER_PATTERN = re.compile(
    r"PERTENECIENTE AL AFILIADO\(A\),?\s*(?:SENOR\(A\)|SENORA|SENOR)?\s*([A-ZÁÉÍÓÚÜÑ ]+?),\s*RUT",
    re.IGNORECASE,
)
AFP_RUT_PATTERN = re.compile(r"AFILIADO\(A\).*?RUT\s+((?:\d{1,2}[.,]?(?:\d{3})[.,]?(?:\d{3})\s*-\s*[\dkK]))", re.IGNORECASE | re.DOTALL)
AFP_ISSUE_DATE_PATTERN = re.compile(
    r"(?:LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO),?\s+(\d{1,2}\s+DE\s+[A-Z]{3,12}\s+DE\s+\d{4})",
    re.IGNORECASE,
)
COMMON_GIVEN_NAMES = {
    "NICOLAS",
    "PAOLA",
    "ANDREA",
    "JUAN",
    "MATEO",
    "MARTIN",
    "SOFIA",
    "DANIELA",
    "CAMILA",
    "VALENTINA",
    "JOSE",
    "MARIA",
}
COMMON_SURNAMES = {
    "FAELLES",
    "YARUR",
    "GONGORA",
    "BRIONES",
    "PEREZ",
    "GONZALEZ",
    "MARTINEZ",
    "RAMOS",
    "VIDAL",
    "LOPEZ",
}

MISSING_TEXT_VALUES = {
    "",
    "-",
    "NO DETECTADO",
    "NO DETECTADA",
    "NO DETECTADOS",
    "NO DETECTADAS",
    "NOMBRE POR CONFIRMAR",
    "EMISOR POR CONFIRMAR",
    "REGISTRO / EMISOR POR CONFIRMAR",
}


def _clean(value: str | None) -> str | None:
    return clean_value(value)


def _meaningful_value(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    normalized = strip_accents(cleaned).upper()
    if normalized in MISSING_TEXT_VALUES or normalized.startswith("SIN "):
        return None
    return cleaned


def _has_value(value: str | None) -> bool:
    return _meaningful_value(value) is not None


def _ratio(values: list[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _clamp_confidence(value: float) -> float:
    return round(max(0.05, min(value, 0.99)), 3)


def _date_sequence_is_valid(birth_date: str | None, issue_date: str | None, expiry_date: str | None) -> bool:
    try:
        birth_value = _meaningful_value(birth_date)
        issue_value = _meaningful_value(issue_date)
        expiry_value = _meaningful_value(expiry_date)
        birth = date.fromisoformat(birth_value) if birth_value else None
        issue = date.fromisoformat(issue_value) if issue_value else None
        expiry = date.fromisoformat(expiry_value) if expiry_value else None
    except ValueError:
        return False

    if birth and issue and birth >= issue:
        return False
    if issue and expiry and expiry <= issue:
        return False
    if birth and expiry and expiry <= birth:
        return False
    return any(value is not None for value in (birth, issue, expiry))


def _calculate_certificate_confidence(
    *,
    confidence: float,
    holder_name: str | None,
    issuer: str | None,
    rut: str | None,
    certificate_number: str | None,
    issue_date: str | None,
    account: str | None,
    periods: list[str],
    dates: list[str],
    amounts: list[str],
    contribution_rows: list[dict[str, str | None]],
) -> float:
    evidence_score = 0.34
    if _has_value(holder_name):
        evidence_score += 0.08
    if _has_value(issuer):
        evidence_score += 0.07
    if _has_value(rut):
        evidence_score += 0.07
    if _has_value(certificate_number):
        evidence_score += 0.05
    if _has_value(issue_date):
        evidence_score += 0.04
    if _has_value(account):
        evidence_score += 0.05
    evidence_score += min(0.08, len(periods) * 0.03)
    evidence_score += min(0.06, len(dates) * 0.02)
    evidence_score += min(0.08, len(amounts) * 0.02)
    if contribution_rows:
        evidence_score += min(0.14, 0.08 + (len(contribution_rows) * 0.01))
    return _clamp_confidence(max(confidence, evidence_score))


def _calculate_identity_confidence(
    *,
    country: str,
    holder_name: str | None,
    document_number: str | None,
    run: str | None,
    first_names: str | None,
    last_names: str | None,
    birth_date: str | None,
    issue_date: str | None,
    expiry_date: str | None,
    mrz: str | None,
    back_field_count: int,
    requires_front_fields: bool,
    requires_back_fields: bool,
) -> float:
    critical_checks = [_has_value(holder_name), _has_value(document_number), _has_value(birth_date)]
    if country.upper() == "CL" and requires_front_fields:
        critical_checks.append(_has_value(run))

    date_checks = [_has_value(birth_date), _has_value(issue_date), _has_value(expiry_date)]
    score = 0.34
    score += _ratio(critical_checks) * 0.26
    score += _ratio(date_checks) * 0.1
    if _has_value(first_names) and _has_value(last_names):
        score += 0.06
    elif _has_value(holder_name):
        score += 0.04
    if country.upper() == "CL" and _has_value(run) and validate_chile_run_checksum(run):
        score += 0.1
    if _has_value(mrz):
        score += 0.05
    if _date_sequence_is_valid(birth_date, issue_date, expiry_date):
        score += 0.03
    if country.upper() in {"PE", "CO"} and _has_value(document_number):
        score += 0.03
    if back_field_count > 0:
        score += min(0.06 if requires_back_fields else 0.04, back_field_count * 0.02)
    return _clamp_confidence(score)


def _calculate_passport_confidence(
    *,
    holder_name: str | None,
    document_number: str | None,
    birth_date: str | None,
    issue_date: str | None,
    expiry_date: str | None,
    nationality: str | None,
    sex: str | None,
    place_of_birth: str | None,
    mrz_value: str | None,
) -> float:
    critical_ratio = _ratio([_has_value(holder_name), _has_value(document_number), _has_value(birth_date), _has_value(expiry_date)])
    score = 0.36 + (critical_ratio * 0.28)
    if _has_value(issue_date):
        score += 0.04
    if _has_value(nationality):
        score += 0.03
    if _has_value(sex):
        score += 0.02
    if _has_value(place_of_birth):
        score += 0.02
    if _has_value(mrz_value):
        score += 0.08
    if validate_mrz_check_digits(mrz_value):
        score += 0.1
    if _date_sequence_is_valid(birth_date, issue_date, expiry_date):
        score += 0.03
    return _clamp_confidence(score)


def _calculate_driver_license_confidence(
    *,
    country: str,
    holder_name: str | None,
    document_number: str | None,
    birth_date: str | None,
    issue_date: str | None,
    expiry_date: str | None,
    categories: str | None,
    authority: str | None,
    address: str | None,
    nationality: str | None,
) -> float:
    critical_ratio = _ratio([_has_value(holder_name), _has_value(document_number), _has_value(expiry_date)])
    score = 0.38 + (critical_ratio * 0.27)
    score += _ratio([_has_value(birth_date), _has_value(issue_date), _has_value(expiry_date)]) * 0.1
    if _has_value(categories):
        score += 0.03
    if _has_value(authority):
        score += 0.03
    if _has_value(address):
        score += 0.03
    if _has_value(nationality):
        score += 0.02
    if country.upper() == "CL" and _has_value(document_number) and validate_chile_run_checksum(document_number):
        score += 0.08
    elif _has_value(document_number):
        score += 0.03
    if _date_sequence_is_valid(birth_date, issue_date, expiry_date):
        score += 0.03
    return _clamp_confidence(score)


def _find_first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _find_holder_name(text: str) -> str | None:
    explicit_patterns = [
        re.compile(r"titular[:\s]+([A-ZÁÉÍÓÚÜÑ ]{8,})", re.IGNORECASE),
        re.compile(r"nombre(?: completo)?[:\s]+([A-ZÁÉÍÓÚÜÑ ]{8,})", re.IGNORECASE),
    ]

    for pattern in explicit_patterns:
        match = pattern.search(text)
        if match:
            return _clean(match.group(1))

    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        normalized_candidate = strip_accents(candidate).upper()
        if any(token in normalized_candidate for token in ["CERTIFICADO", "DOCUMENTO", "AFP", "RUT", "CUENTA", "IDENTIDAD"]):
            continue
        if UPPERCASE_LINE_PATTERN.match(candidate) and len(candidate.split()) >= 2:
            return _clean(candidate)

    return None


def _find_issuer(text: str, document_family: str) -> str | None:
    if document_family == "certificate":
        match = re.search(r"(AFP\s+[A-Za-zÁÉÍÓÚÜÑ]+(?:\s+S\.?A\.?)?)", text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))

    issuer_patterns = [
        re.compile(r"emisor[:\s]+([^\n]+)", re.IGNORECASE),
        re.compile(r"issuer[:\s]+([^\n]+)", re.IGNORECASE),
        re.compile(r"registro civil[^\n]*", re.IGNORECASE),
    ]

    for pattern in issuer_patterns:
        match = pattern.search(text)
        if match:
            return _clean(match.group(0 if pattern.pattern.startswith("registro") else 1))

    return None


def _normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", strip_accents(value).upper())


def _lines(text: str) -> list[str]:
    return [cleaned for raw in text.splitlines() if (cleaned := _clean(raw))]


def _is_identity_name_candidate(line: str) -> bool:
    normalized = _normalize_key(line)
    if not normalized or normalized in IDENTITY_STOP_TOKENS:
        return False
    if any(token in normalized for token in {"CEDULA", "IDENTIDAD", "REPUBLICA", "REGISTRO", "SERVICIO", "DOCUMENTO", "FIRMA", "FECHA", "NUMERO", "SEXO"}):
        return False
    if any(char.isdigit() for char in line):
        return False
    if COMPACT_DATE_PATTERN.search(normalized):
        return False
    if len(line.split()) > 4:
        return False
    return bool(re.fullmatch(r"[A-ZÁÉÍÓÚÜÑ ]+", line))


def _find_label_index(lines: list[str], *labels: str) -> int | None:
    normalized_labels = {_normalize_key(label) for label in labels}
    for index, line in enumerate(lines):
        normalized_line = _normalize_key(line)
        if normalized_line in normalized_labels or any(label in normalized_line for label in normalized_labels):
            return index
    return None


def _find_nearby_value(lines: list[str], label_index: int | None, predicate, max_distance: int = 6, prefer_backward: bool = False) -> str | None:
    if label_index is None:
        return None

    for distance in range(1, max_distance + 1):
        candidate_order = (label_index - distance, label_index + distance) if prefer_backward else (label_index + distance, label_index - distance)
        for candidate_index in candidate_order:
            if candidate_index < 0 or candidate_index >= len(lines):
                continue
            candidate = lines[candidate_index]
            if predicate(candidate):
                return candidate
    return None


def _parse_compact_date(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"\s+", "", value.upper())
    match = re.fullmatch(r"(\d{2})([A-Z]{3})(\d{4})", compact)
    if not match:
        return None
    day, month, year = match.groups()
    mapped_month = MONTH_MAP.get(month)
    if not mapped_month:
        return None
    return f"{year}-{mapped_month}-{day}"


def _normalize_date_value(value: str | None) -> str | None:
    return normalize_date_value(value)


def _extract_inline_value(line: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:\-]?\s+(.+)$", line, re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return None


def _find_label_value(lines: list[str], *labels: str, predicate=None, max_distance: int = 3, prefer_backward: bool = False) -> str | None:
    predicate = predicate or (lambda value: bool(_clean(value)))
    label_tuple = tuple(labels)

    for line in lines:
        inline_value = _extract_inline_value(line, label_tuple)
        if inline_value and predicate(inline_value):
            return inline_value

    label_index = _find_label_index(lines, *labels)
    if label_index is None:
        return None

    return _find_nearby_value(lines, label_index, predicate, max_distance=max_distance, prefer_backward=prefer_backward)


def _find_regex_value(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(strip_accents(text).upper())
    return _clean(match.group(0)) if match else None


def _normalize_mrz_nationality(value: str | None, fallback_country: str) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    return {
        "CHL": "CHILENA",
        "CL": "CHILENA",
        "PER": "PERUANA",
        "PE": "PERUANA",
        "COL": "COLOMBIANA",
        "CO": "COLOMBIANA",
    }.get(cleaned.upper(), {"CL": "CHILENA", "PE": "PERUANA", "CO": "COLOMBIANA"}.get(fallback_country.upper(), cleaned.upper()))


def _find_textual_dates(text: str) -> list[str]:
    values: list[str] = []
    for match in TEXTUAL_LONG_DATE_PATTERN.findall(strip_accents(text).upper()):
        normalized = _normalize_date_value(match)
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _split_compact_name_token(token: str) -> tuple[str | None, str | None]:
    normalized = re.sub(r"[^A-Z]", "", strip_accents(token).upper())
    if not normalized:
        return None, None
    for given_name in sorted(COMMON_GIVEN_NAMES, key=len, reverse=True):
        if normalized.startswith(given_name) and len(normalized) > len(given_name) + 2:
            return given_name, normalized[len(given_name) :]
    return None, normalized if len(normalized) >= 4 else None


def _split_compact_surnames(token: str) -> list[str]:
    normalized = re.sub(r"[^A-Z]", "", strip_accents(token).upper())
    if not normalized:
        return []
    parts: list[str] = []
    remaining = normalized
    while remaining:
        match = next((surname for surname in sorted(COMMON_SURNAMES, key=len, reverse=True) if remaining.startswith(surname)), None)
        if match:
            parts.append(match)
            remaining = remaining[len(match) :]
        else:
            parts.append(remaining)
            break
    return [part for part in parts if part]


def _extract_driver_license_name(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    explicit_holder = _find_generic_label_value(
        lines,
        ("NAME", "NOMBRE", "HOLDER"),
        predicate=lambda value: bool(_clean(value)) and len(value) >= 6 and not any(char.isdigit() for char in value),
    )
    explicit_holder_text = _clean(re.sub(r"^(?:NAME|NOMBRE|HOLDER)\s+", "", strip_accents(explicit_holder).upper())) if explicit_holder else None
    if explicit_holder_text:
        parts = explicit_holder_text.split()
        if len(parts) >= 3:
            first_name = _clean(" ".join(parts[:-2]))
            surname = _clean(" ".join(parts[-2:]))
            return first_name, surname, _clean(" ".join(part for part in [first_name, surname] if part))
        if len(parts) >= 2:
            first_name = _clean(parts[0])
            surname = _clean(" ".join(parts[1:]))
            return first_name, surname, _clean(" ".join(part for part in [first_name, surname] if part))
        return None, None, explicit_holder_text

    for index, line in enumerate(lines):
        first_name, remainder = _split_compact_name_token(line)
        if not first_name:
            continue
        surname_parts = _split_compact_surnames(remainder or "")
        candidate_lines = lines[index + 1 : index + 4]
        scored_candidates: list[tuple[int, list[str]]] = []
        for candidate in candidate_lines:
            parts = _split_compact_surnames(candidate)
            score = sum(2 for part in parts if part in COMMON_SURNAMES) - sum(1 for part in parts if part not in COMMON_SURNAMES and len(part) <= 4)
            scored_candidates.append((score, parts))
        for _, parts in sorted(scored_candidates, key=lambda item: item[0], reverse=True):
            surname_parts.extend(parts)
            if len(surname_parts) >= 3:
                break
        surname_parts = [part for part in surname_parts if part and (part in COMMON_SURNAMES or len(part) >= 6)]
        surname = _clean(" ".join(surname_parts[:3]))
        holder_name = _clean(" ".join(part for part in [first_name, surname] if part))
        return _clean(first_name), surname, holder_name
    return None, None, None


def _expand_compact_given_names(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned or " " in cleaned:
        return cleaned
    first_name, remainder = _split_compact_name_token(cleaned)
    if first_name and remainder:
        return _clean(f"{first_name} {remainder}")
    return cleaned


def _find_all_normalized_dates(text: str) -> list[str]:
    raw_dates = [
        *ISO_DATE_PATTERN.findall(text),
        *LATAM_DATE_PATTERN.findall(text),
        *COMPACT_DATE_PATTERN.findall(text),
        *SPACE_DATE_PATTERN.findall(text),
        *LONG_SPANISH_DATE_PATTERN.findall(strip_accents(text).upper()),
    ]
    normalized: list[str] = []
    for candidate in raw_dates:
        value = _normalize_date_value(candidate)
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_period_value(value: str | None) -> str | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    match = MONTH_PERIOD_PATTERN.search(strip_accents(cleaned).upper())
    if not match:
        return None
    month_abbrev, year = re.split(r"[-/]", match.group(0).upper())
    month = MONTH_MAP.get(month_abbrev)
    if not month:
        return None
    return f"{year}-{month}"


def _extract_certificate_number(text: str) -> str | None:
    match = AFP_CERTIFICATE_NUMBER_PATTERN.search(strip_accents(text).upper())
    return _clean(match.group(1)) if match else None


def _extract_certificate_issue_date(text: str) -> str | None:
    match = AFP_ISSUE_DATE_PATTERN.search(strip_accents(text).upper())
    if match:
        return _strict_normalize_date(match.group(1))
    dates = _find_all_normalized_dates(text)
    return dates[0] if dates else None


def _extract_certificate_rut(lines: list[str], text: str) -> str | None:
    afp_match = AFP_RUT_PATTERN.search(strip_accents(text).upper())
    if afp_match:
        return canonicalize_chile_run(afp_match.group(1))

    labelled = _pick_numeric_identifier(lines, ("RUT", "RUT DEL AFILIADO", "RUT AFILIADO", "IDENTIFICACION"), RUT_PATTERN)
    if labelled:
        return canonicalize_chile_run(labelled)

    return canonicalize_chile_run(_find_first(RUT_PATTERN, text))


def _extract_afp_holder(text: str) -> str | None:
    match = AFP_HOLDER_PATTERN.search(text)
    if match:
        return _clean(strip_accents(match.group(1)).upper())
    return None


def _is_afp_table_row_start(line: str) -> bool:
    return _normalize_period_value(line) is not None


def _extract_afp_table_rows(lines: list[str]) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        period = _normalize_period_value(line)
        if not period:
            index += 1
            continue

        normalized_line = strip_accents(line).upper()
        amounts = list(dict.fromkeys(AMOUNT_PATTERN.findall(line)))
        if not amounts and normalized_line.count("$0") >= 2:
            amounts = ["0", "0"]
        raw_period_match = MONTH_PERIOD_PATTERN.search(normalized_line)
        raw_period = raw_period_match.group(0).upper() if raw_period_match else period
        code = None
        if raw_period_match:
            remainder = normalized_line[raw_period_match.end() :]
            for amount in amounts[:2]:
                position = remainder.find(amount.upper())
                if position >= 0:
                    remainder = remainder[position + len(amount) :]
            code = _clean(remainder)

        inline_rut = canonicalize_chile_run(_find_first(RUT_PATTERN, code or ""))
        inline_dates = _find_all_normalized_dates(code or "")
        inline_date = inline_dates[0] if inline_dates else None
        employer = None
        employer_rut = inline_rut
        payment_date = inline_date
        if code and inline_rut:
            employer_candidate = code
            rut_text = _find_first(RUT_PATTERN, code)
            if rut_text:
                employer_candidate = employer_candidate.split(rut_text, 1)[0]
            if inline_date:
                employer_candidate = employer_candidate.replace(inline_date, " ")
            employer_candidate = _clean(employer_candidate)
            if employer_candidate and "PERIODO SIN" not in strip_accents(employer_candidate).upper():
                employer = employer_candidate
                code = None

        detail_parts = [line]
        lookahead = index + 1

        while lookahead < len(lines):
            candidate = lines[lookahead]
            if _is_afp_table_row_start(candidate):
                break

            normalized_candidate = strip_accents(candidate).upper()
            if any(
                token in normalized_candidate
                for token in (
                    "LOS CODIGOS DE COTIZACION",
                    "CORDIALMENTE",
                    "SERVICIO DE INFORMACION",
                    "PUEDES OBTENER EL MISMO CERTIFICADO",
                )
            ):
                break

            detail_parts.append(candidate)
            if employer is None and code and "PERIODO SIN" in strip_accents(code).upper() and not RUT_PATTERN.search(candidate) and not DATE_PATTERN.search(candidate):
                code = _clean(f"{code} {candidate}")
            elif employer is None and not RUT_PATTERN.search(candidate) and not DATE_PATTERN.search(candidate):
                employer = _clean(candidate)

            candidate_rut = canonicalize_chile_run(_find_first(RUT_PATTERN, candidate))
            if candidate_rut and employer_rut is None:
                employer_rut = candidate_rut

            candidate_dates = _find_all_normalized_dates(candidate)
            if candidate_dates and payment_date is None:
                payment_date = candidate_dates[0]

            lookahead += 1

        row = {
            "period": period,
            "period_label": raw_period,
            "date": payment_date,
            "amount": amounts[1] if len(amounts) > 1 else amounts[0] if amounts else None,
            "renta_amount": amounts[0] if amounts else None,
            "pension_amount": amounts[1] if len(amounts) > 1 else None,
            "cotization_code": code,
            "employer": employer,
            "employer_rut": employer_rut,
            "detail": _clean(" ".join(detail_parts)),
        }
        rows.append(row)
        index = lookahead if lookahead > index else index + 1

    return rows


def _strict_normalize_date(value: str | None) -> str | None:
    normalized = _normalize_date_value(value)
    if normalized and re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return normalized
    return None


def _extract_identity_name_from_labels(lines: list[str], first_name_labels: tuple[str, ...], last_name_labels: tuple[str, ...]) -> tuple[str | None, str | None, str | None]:
    first_names = _find_label_value(lines, *first_name_labels, predicate=lambda line: _is_identity_name_candidate(line))
    last_names = _find_label_value(lines, *last_name_labels, predicate=lambda line: _is_identity_name_candidate(line))
    holder_name = " ".join(part for part in [first_names, last_names] if part) or None
    return first_names, last_names, holder_name


def _extract_name_sequence_after_identifier(text: str, country: str) -> tuple[str | None, str | None, str | None]:
    normalized_text = strip_accents(text.upper())
    if country.upper() == "PE":
        match = re.search(r"\d{8}(?:-\d)?\s+([A-Z ]+?)\s+(?:FEMENINO|MASCULINO|F)\b", normalized_text)
        candidate_block = match.group(1) if match else None
    elif country.upper() == "CO":
        match = re.search(r"(?:NUIP|CEDULA|IDENTIFICACION)?\s*[0-9.]{6,14}\s+([A-Z ]+?)\s+(?:COL|COLOMBIANA|COLOMBIANO|M|F|\d)\b", normalized_text)
        candidate_block = match.group(1) if match else None
    else:
        candidate_block = None

    if not candidate_block:
        return None, None, None

    filtered_tokens = [
        token
        for token in candidate_block.split()
        if token not in {"MUESTRA", "SIN", "VALOR", "NO", "SADA", "COL", "COLOMBIANA", "COLOMBIANO", "PERUANA", "PERUANO"}
    ]

    if len(filtered_tokens) < 2:
        return None, None, None

    if len(filtered_tokens) == 2:
        last_names = filtered_tokens[0]
        first_names = filtered_tokens[1]
    else:
        split_index = 2 if len(filtered_tokens) >= 3 else 1
        last_names = " ".join(filtered_tokens[:split_index])
        first_names = " ".join(filtered_tokens[split_index:])

    holder_name = clean_value(f"{first_names} {last_names}")
    return clean_value(first_names), clean_value(last_names), holder_name


def _extract_name_sequence_from_labels(text: str, country: str) -> tuple[str | None, str | None, str | None]:
    normalized_text = strip_accents(text.upper())
    if country.upper() not in {"PE", "CO"}:
        return None, None, None

    surname_match = re.search(r"APELL[A-Z]*\s+([A-Z]{3,}(?:\s+[A-Z]{3,}){0,2})", normalized_text)
    if not surname_match:
        return None, None, None

    last_names = clean_value(surname_match.group(1))
    remaining_text = normalized_text[surname_match.end() :]
    first_match = re.search(r"([A-Z]{3,}(?:\s+[A-Z]{3,}){0,2})\s+(?:SEXO|SESO|NACIONALIDAD|FECHA|ESTADO|SOLTERO|CASADO|PER|COL|M|F)\b", remaining_text)
    if not first_match:
        first_match = re.search(r"([A-Z]{3,}(?:\s+[A-Z]{3,}){0,2})", remaining_text)
    first_names = clean_value(first_match.group(1)) if first_match else None
    holder_name = clean_value(" ".join(part for part in [first_names, last_names] if part))
    return first_names, last_names, holder_name


def _pick_numeric_identifier(lines: list[str], labels: tuple[str, ...], pattern: re.Pattern[str]) -> str | None:
    labelled = _find_label_value(lines, *labels, predicate=lambda value: bool(pattern.search(value)))
    if labelled:
        match = pattern.search(labelled)
        if match:
            return match.group(0)

    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(0)

    return None


def _extract_gender(lines: list[str]) -> str | None:
    value = _find_label_value(lines, "SEXO", "SEX")
    if not value:
        return None

    normalized = _normalize_key(value)
    if normalized in {"M", "MASCULINO"}:
        return "M"
    if normalized in {"F", "FEMENINO"}:
        return "F"
    if normalized in {"X", "OTRO", "NOBINARIO"}:
        return "X"
    return _clean(value)


def _extract_nationality(lines: list[str], *labels: str) -> str | None:
    value = _find_label_value(lines, *labels, predicate=lambda line: len(line) <= 32 and not any(char.isdigit() for char in line))
    return _clean(value.upper()) if value else None


def _extract_country_specific_identity(lines: list[str], text: str, country: str) -> dict[str, str | None]:
    normalized_country = country.upper()

    if normalized_country == "CL":
        return _find_identity_fields(lines)

    if normalized_country == "PE":
        first_names, last_names, holder_name = _extract_identity_name_from_labels(lines, ("NOMBRES",), ("APELLIDOS", "APELLIDO PATERNO", "APELLIDO MATERNO"))
        if not holder_name or is_placeholder_name(holder_name):
            first_names, last_names, holder_name = _extract_name_sequence_from_labels(text, normalized_country)
        if not holder_name or is_placeholder_name(holder_name):
            first_names, last_names, holder_name = _extract_name_sequence_after_identifier(text, normalized_country)
        dates = _find_all_normalized_dates(text)
        document_number = canonicalize_identity_document_number(
            normalized_country,
            _pick_numeric_identifier(lines, ("DNI", "NUMERO DE DOCUMENTO", "NUMERO DOCUMENTO"), PE_DNI_PATTERN),
        )
        return {
            "first_names": first_names,
            "last_names": last_names,
            "holder_name": holder_name or _find_holder_name(text),
            "run": None,
            "document_number": document_number,
            "nationality": _extract_nationality(lines, "NACIONALIDAD") or "PERUANA",
            "sex": _extract_gender(lines),
            "birth_date": _normalize_date_value(_find_label_value(lines, "FECHA DE NACIMIENTO", prefer_backward=True)) or (dates[0] if dates else None),
            "issue_date": _normalize_date_value(_find_label_value(lines, "FECHA DE EMISION", "EMISION")) or (dates[1] if len(dates) > 1 else None),
            "expiry_date": _normalize_date_value(_find_label_value(lines, "FECHA DE CADUCIDAD", "FECHA DE VENCIMIENTO", "CADUCIDAD")) or (dates[2] if len(dates) > 2 else None),
        }

    if normalized_country == "CO":
        first_names, last_names, holder_name = _extract_identity_name_from_labels(lines, ("NOMBRES",), ("APELLIDOS",))
        if not holder_name or is_placeholder_name(holder_name):
            first_names, last_names, holder_name = _extract_name_sequence_from_labels(text, normalized_country)
        if not holder_name or is_placeholder_name(holder_name):
            first_names, last_names, holder_name = _extract_name_sequence_after_identifier(text, normalized_country)
        dates = _find_all_normalized_dates(text)
        document_number = canonicalize_identity_document_number(
            normalized_country,
            _pick_numeric_identifier(lines, ("NUMERO", "NUMERO DE DOCUMENTO", "IDENTIFICACION", "CEDULA", "NUIP", "NIP"), CO_CEDULA_FLEX_PATTERN),
        )
        return {
            "first_names": first_names,
            "last_names": last_names,
            "holder_name": holder_name or _find_holder_name(text),
            "run": None,
            "document_number": document_number,
            "nationality": _extract_nationality(lines, "NACIONALIDAD") or "COLOMBIANA",
            "sex": _extract_gender(lines),
            "birth_date": _normalize_date_value(_find_label_value(lines, "FECHA DE NACIMIENTO", "NACIMIENTO")) or (dates[0] if dates else None),
            "issue_date": _normalize_date_value(_find_label_value(lines, "FECHA DE EXPEDICION", "EXPEDICION", "FECHA DE EMISION")) or (dates[1] if len(dates) > 1 else None),
            "expiry_date": _normalize_date_value(_find_label_value(lines, "FECHA DE VENCIMIENTO", "VENCE", "VENCIMIENTO")) or (dates[2] if len(dates) > 2 else None),
        }

    return {
        "first_names": None,
        "last_names": None,
        "holder_name": _find_holder_name(text),
        "run": None,
        "document_number": _pick_numeric_identifier(lines, ("NUMERO", "DOCUMENTO", "IDENTIFICACION"), CO_CEDULA_PATTERN),
        "nationality": _extract_nationality(lines, "NACIONALIDAD"),
        "sex": _extract_gender(lines),
        "birth_date": None,
        "issue_date": None,
        "expiry_date": None,
    }


def _extract_back_fields(lines: list[str], country: str) -> dict[str, str | None]:
    normalized_country = country.upper()

    if normalized_country == "CL":
        return {
            "address": _find_label_value(lines, "DOMICILIO", "DIRECCION"),
            "commune": _find_label_value(lines, "COMUNA"),
            "profession": _find_label_value(lines, "PROFESION", "PROFESION U OFICIO", "OFICIO"),
            "electoral_circ": _find_label_value(lines, "CIRCUNSCRIPCION", "CIRCUNSCRIPCION ELECTORAL"),
            "birth_place": _find_label_value(
                lines,
                "NACIO EN",
                "NACIDO EN",
                "LUGAR DE NACIMIENTO",
                predicate=lambda value: len(_clean(value) or "") <= 32 and not any(char.isdigit() for char in value),
                max_distance=2,
                prefer_backward=True,
            ),
        }

    if normalized_country == "PE":
        return {
            "address": _find_label_value(lines, "DOMICILIO", "DIRECCION"),
            "civil_status": _find_label_value(lines, "ESTADO CIVIL"),
            "education": _find_label_value(lines, "GRADO DE INSTRUCCION", "INSTRUCCION"),
            "donor": _find_label_value(lines, "DONACION DE ORGANOS", "DONACION ORGANOS"),
            "restriction": _find_label_value(lines, "RESTRICCION", "RESTRICCIONES"),
        }

    if normalized_country == "CO":
        return {
            "birth_place": _find_label_value(lines, "LUGAR DE NACIMIENTO", "MUNICIPIO DE NACIMIENTO"),
            "height": _find_label_value(lines, "ESTATURA"),
            "blood_type": _find_label_value(lines, "G.S. RH", "GRUPO SANGUINEO", "RH"),
            "issue_place": _find_label_value(lines, "FECHA Y LUGAR DE EXPEDICION", "LUGAR DE EXPEDICION", "EXPEDICION"),
        }

    return {}


def _non_empty_back_field_count(back_fields: dict[str, str | None]) -> int:
    return sum(1 for value in back_fields.values() if _clean(value))


def _find_identity_fields(lines: list[str]) -> dict[str, str | None]:
    surnames_index = _find_label_index(lines, "APELLIDOS")
    names_index = _find_label_index(lines, "NOMBRES")
    nationality_index = _find_label_index(lines, "NACIONALIDAD")
    sex_index = _find_label_index(lines, "SEXO")
    document_number_index = _find_label_index(lines, "NUMERO DOCUMENTO", "NUMERO DE DOCUMENTO")
    birth_date_index = _find_label_index(lines, "FECHA DE NACIMIENTO")
    issue_date_index = _find_label_index(lines, "FECHA DE EMISION")
    expiry_date_index = _find_label_index(lines, "FECHA DE VENCIMIENTO")
    run_index = _find_label_index(lines, "RUN")

    def collect_name_candidates(label_index: int | None, *, limit: int = 2, prefer_forward: bool = True) -> list[str]:
        if label_index is None:
            return []

        offsets = list(range(1, 5))
        candidates: list[str] = []
        directions = (1, -1) if prefer_forward else (-1, 1)
        for direction in directions:
            for offset in offsets:
                candidate_index = label_index + (offset * direction)
                if candidate_index < 0 or candidate_index >= len(lines):
                    continue
                candidate = lines[candidate_index]
                if _is_identity_name_candidate(candidate):
                    candidates.append(candidate)
                    if len(candidates) >= limit:
                        return candidates
                elif candidates:
                    break
        return candidates

    surname_parts = collect_name_candidates(surnames_index, limit=2, prefer_forward=True)
    if not surname_parts:
        surname_parts = collect_name_candidates(surnames_index, limit=2, prefer_forward=False)

    first_name_candidates = collect_name_candidates(names_index, limit=1, prefer_forward=True)
    if not first_name_candidates:
        first_name_candidates = collect_name_candidates(names_index, limit=1, prefer_forward=False)
    first_names = _expand_compact_given_names(first_name_candidates[0]) if first_name_candidates else None

    run_line = _find_nearby_value(lines, run_index, lambda line: bool(RUT_PATTERN.search(line))) or next(
        (line for line in lines if RUT_PATTERN.search(line)),
        None,
    )
    run = canonicalize_chile_run(run_line)
    document_number = _find_nearby_value(lines, document_number_index, lambda line: bool(DOCUMENT_NUMBER_PATTERN.search(line))) or next(
        (line for line in lines if DOCUMENT_NUMBER_PATTERN.search(line)),
        None,
    )
    nationality = _find_nearby_value(lines, nationality_index, lambda line: _normalize_key(line) in {"CHILENA", "CHILENO"}) or next(
        (line for line in lines if _normalize_key(line) in {"CHILENA", "CHILENO"}),
        None,
    )
    sex = _find_nearby_value(lines, sex_index, lambda line: _normalize_key(line) in {"M", "F", "X"}, max_distance=2)
    birth_date = _parse_compact_date(_find_nearby_value(lines, birth_date_index, lambda line: bool(COMPACT_DATE_PATTERN.search(line)), max_distance=4))
    issue_date = _parse_compact_date(_find_nearby_value(lines, issue_date_index, lambda line: bool(COMPACT_DATE_PATTERN.search(line)), max_distance=4))
    expiry_date = _parse_compact_date(_find_nearby_value(lines, expiry_date_index, lambda line: bool(COMPACT_DATE_PATTERN.search(line)), max_distance=4))

    compact_dates = []
    for candidate in lines:
        parsed = _parse_compact_date(candidate)
        if parsed and parsed not in compact_dates:
            compact_dates.append(parsed)
    if compact_dates:
        sorted_dates = sorted(compact_dates)
        if birth_date is None:
            birth_date = sorted_dates[0]
        if expiry_date is None and len(sorted_dates) >= 2:
            expiry_date = sorted_dates[-1]
        if issue_date is None and len(sorted_dates) >= 3:
            issue_date = sorted_dates[-2]
        if len(sorted_dates) >= 3:
            if expiry_date == birth_date:
                expiry_date = sorted_dates[-1]
            if issue_date in {birth_date, expiry_date}:
                issue_date = sorted_dates[-2]

    holder_name_parts = [part for part in [first_names, *surname_parts] if part]

    return {
        "first_names": first_names,
        "last_names": " ".join(surname_parts) if surname_parts else None,
        "holder_name": " ".join(holder_name_parts) if holder_name_parts else None,
        "run": run,
        "document_number": document_number,
        "nationality": nationality,
        "sex": sex,
        "birth_date": birth_date,
        "issue_date": issue_date,
        "expiry_date": expiry_date,
    }


def _make_issue(issue_id: str, issue_type: str, field: str, severity: ValidationSeverity, message: str, suggested_action: str) -> ValidationIssue:
    return ValidationIssue(
        id=issue_id,
        type=issue_type,
        field=field,
        severity=severity,
        message=message,
        suggestedAction=suggested_action,
    )


def _extract_certificate_holder(lines: list[str], text: str) -> str | None:
    afp_holder = _extract_afp_holder(strip_accents(text).upper())
    if afp_holder:
        return afp_holder

    return _find_label_value(
        lines,
        "TITULAR",
        "AFILIADO",
        "NOMBRE",
        "NOMBRE COMPLETO",
        predicate=lambda value: len(value) >= 6 and not any(char.isdigit() for char in value),
    ) or _find_holder_name(text)


def _extract_certificate_issuer(lines: list[str], text: str) -> str | None:
    explicit = _find_label_value(
        lines,
        "EMISOR",
        "EMPRESA",
        "RAZON SOCIAL",
        predicate=lambda value: len(value) >= 4,
    )
    if explicit:
        return explicit
    return _find_issuer(text, "certificate")


def _extract_certificate_table_rows(lines: list[str], text: str) -> list[dict[str, str | None]]:
    if "AFP" in strip_accents(text).upper() and "COTIZACIONES" in strip_accents(text).upper():
        afp_rows = _extract_afp_table_rows(lines)
        if afp_rows:
            return afp_rows

    rows: list[dict[str, str | None]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for line in lines:
        normalized_line = line.upper()
        periods = list(dict.fromkeys(PERIOD_PATTERN.findall(line)))
        amounts = list(dict.fromkeys(AMOUNT_PATTERN.findall(line)))
        dates = _find_all_normalized_dates(line)
        account = _find_first(ACCOUNT_PATTERN, line)

        if any(label in normalized_line for label in {"RUT", "CUENTA", "CTA"}) and not periods and not dates:
            continue

        if not periods and not amounts:
            continue

        if not periods and not dates and len(amounts) < 2:
            continue

        detail = _clean(line) or line
        row = {
            "period": periods[0] if periods else None,
            "date": dates[0] if dates else None,
            "amount": amounts[-1] if amounts else None,
            "account": account,
            "detail": detail,
        }
        signature = (
            row["period"] or "-",
            row["date"] or "-",
            row["amount"] or "-",
            row["detail"] or "-",
        )
        if signature in seen:
            continue
        seen.add(signature)
        rows.append(row)

    return rows[:12]


def normalize_certificate_text(text: str, country: str, filename: str, assumptions: list[str]) -> NormalizedDocument:
    pack = resolve_document_pack(document_family="certificate", country=country)
    lines = _lines(text)
    holder_name = _extract_certificate_holder(lines, text) or "NOMBRE POR CONFIRMAR"
    issuer = _extract_certificate_issuer(lines, text) or "Emisor por confirmar"
    rut = _extract_certificate_rut(lines, text)
    account = _pick_numeric_identifier(lines, ("CUENTA", "CUENTA DE COTIZACION", "CTA"), ACCOUNT_PATTERN) or _find_first(ACCOUNT_PATTERN, text)
    certificate_number = _extract_certificate_number(text)
    issue_date = _extract_certificate_issue_date(text)
    contribution_rows = _extract_certificate_table_rows(lines, text)
    normalized_month_periods: list[str] = []
    for match in MONTH_PERIOD_PATTERN.findall(text):
        normalized_period = _normalize_period_value(match)
        if normalized_period:
            normalized_month_periods.append(normalized_period)
    periods = [
        value
        for value in list(
            dict.fromkeys(
                [row["period"] for row in contribution_rows if row["period"]]
                + PERIOD_PATTERN.findall(text)
                + normalized_month_periods
            )
        )[:24]
        if value
    ]
    dates = list(dict.fromkeys([row["date"] for row in contribution_rows if row["date"]] + _find_all_normalized_dates(text)))[:5]
    amounts = list(dict.fromkeys([row["amount"] for row in contribution_rows if row["amount"]] + AMOUNT_PATTERN.findall(text)))[:8]

    issues: list[ValidationIssue] = []
    confidence = 0.62

    if rut:
        confidence += 0.08
    else:
        issues.append(
            _make_issue(
                "issue-missing-rut",
                "MISSING_FIELD",
                "RUT",
                "medium",
                "No se detecto un identificador tipo RUT en el texto extraido.",
                "Validar si el documento requiere OCR visual o revisar otra pagina del archivo.",
            )
        )

    if account:
        confidence += 0.06
    if periods:
        confidence += 0.06
    if amounts:
        confidence += 0.06
    if contribution_rows:
        confidence += 0.05
    else:
        issues.append(
            _make_issue(
                "issue-missing-amounts",
                "LOW_EVIDENCE",
                "montos",
                "low",
                "No se detectaron suficientes montos estructurables en el texto extraido.",
                "Intentar OCR visual o revisar si el PDF contiene solo imagenes.",
            )
        )

    summary_rows = [
        ["Documento", "CERTIFICADO / COMPROBANTE"],
        ["Archivo", filename],
        ["Pais", country],
        ["Emisor", issuer],
        ["Titular", holder_name],
        ["RUT", rut or "NO DETECTADO"],
        ["Numero de certificado", certificate_number or "NO DETECTADO"],
        ["Fecha de emision", issue_date or "NO DETECTADA"],
        ["Cuenta", account or "NO DETECTADA"],
        ["Filas tabulares detectadas", str(len(contribution_rows))],
    ]

    date_rows = [[period, dates[index] if index < len(dates) else "-"] for index, period in enumerate(periods)]
    if not date_rows and dates:
        date_rows = [[f"Fecha {index + 1}", value] for index, value in enumerate(dates)]

    amount_rows = [[f"Monto {index + 1}", value] for index, value in enumerate(amounts)]

    movement_rows = [
        [
            row.get("period_label") or row["period"] or "-",
            row.get("renta_amount") or "-",
            row.get("pension_amount") or row["amount"] or "-",
            row.get("cotization_code") or "-",
            row.get("employer") or "-",
            row.get("employer_rut") or "-",
            row["date"] or "-",
            row["detail"] or "-",
        ]
        for row in contribution_rows
    ]

    identifier_rows = [
        ["RUT", rut or "NO DETECTADO"],
        ["Numero de certificado", certificate_number or "NO DETECTADO"],
        ["Fecha de emision", issue_date or "NO DETECTADA"],
        ["Cuenta", account or "NO DETECTADA"],
    ]

    report_sections = [
        ReportSection(id="summary", title="Resumen", variant="pairs", rows=summary_rows),
        ReportSection(
            id="dates",
            title="Fechas",
            variant="table",
            columns=["Campo", "Valor"],
            rows=date_rows or [["Sin fechas detectadas", "-"]],
        ),
        ReportSection(
            id="amounts",
            title="Montos",
            variant="table",
            columns=["Campo", "Valor"],
            rows=amount_rows or [["Sin montos detectados", "-"]],
        ),
        ReportSection(
            id="movements",
            title="Filas tabulares detectadas",
            variant="table",
            columns=["Periodo", "Renta imponible", "Fondo pensiones", "Codigo", "Empleador", "RUT empleador", "Fecha pago", "Detalle"],
            rows=movement_rows or [["-", "-", "-", "-", "-", "-", "-", "Sin filas tabulares detectadas"]],
        ),
        ReportSection(id="identifiers", title="Identificadores", variant="pairs", rows=identifier_rows),
        ReportSection(
            id="human-summary",
            title="Resumen humano",
            variant="text",
            body="Se normalizo un certificado/comprobante a partir de texto embebido del archivo. La salida es util para una primera revision operativa, pero todavia puede requerir OCR visual si faltan montos o identificadores.",
        ),
    ]

    assumptions = [*assumptions]
    if periods:
        assumptions.append("Los periodos detectados se interpretaron como anio-mes sin inferir informacion faltante.")
    if dates:
        assumptions.append("Las fechas se conservaron con el formato encontrado en el documento cuando fue posible.")
    if contribution_rows:
        assumptions.append("Se detectaron filas tabulares con montos/periodos para enriquecer la extraccion del certificado.")
    if certificate_number:
        assumptions.append("Se detecto un numero de certificado en el encabezado del documento.")

    return NormalizedDocument(
        document_family="certificate",
        country=country,
        variant=pack.variant if pack else "text-certificate",
        issuer=issuer,
        holder_name=holder_name,
        global_confidence=_calculate_certificate_confidence(
            confidence=confidence,
            holder_name=holder_name,
            issuer=issuer,
            rut=rut,
            certificate_number=certificate_number,
            issue_date=issue_date,
            account=account,
            periods=periods,
            dates=dates,
            amounts=amounts,
            contribution_rows=contribution_rows,
        ),
        assumptions=assumptions,
        issues=issues,
        report_sections=report_sections,
        human_summary="Extraccion basada en texto embebido del documento, con normalizacion heuristica y validaciones basicas.",
    )


def normalize_identity_text(
    text: str,
    country: str,
    filename: str,
    assumptions: list[str],
    pack_id: str | None = None,
    document_side: str | None = None,
    supplemental_fields: dict[str, str] | None = None,
) -> NormalizedDocument:
    lines = _lines(text)
    pack = resolve_document_pack(pack_id=pack_id, document_family="identity", country=country)
    identity_fields = _extract_country_specific_identity(lines, text, country)
    identity_card_mrz = parse_identity_card_mrz(text) if country.upper() == "CL" else {}
    supplemental = supplemental_fields or {}
    if supplemental.get("first_names"):
        identity_fields["first_names"] = supplemental["first_names"]
    if supplemental.get("last_names"):
        identity_fields["last_names"] = supplemental["last_names"]
    if supplemental.get("sex"):
        identity_fields["sex"] = supplemental["sex"]
    if supplemental.get("birth_date"):
        identity_fields["birth_date"] = supplemental["birth_date"]
    if supplemental.get("issue_date"):
        identity_fields["issue_date"] = supplemental["issue_date"]
    if supplemental.get("expiry_date"):
        identity_fields["expiry_date"] = supplemental["expiry_date"]
    if supplemental.get("issuer"):
        identity_fields["issuer"] = supplemental["issuer"]
    if supplemental.get("holder_name") and (supplemental.get("first_names") and supplemental.get("last_names")):
        identity_fields["holder_name"] = supplemental["holder_name"]
    elif identity_fields.get("first_names") and identity_fields.get("last_names"):
        identity_fields["holder_name"] = _clean(f"{identity_fields['first_names']} {identity_fields['last_names']}")
    effective_side = document_side or (pack.document_side if pack else None)
    if identity_card_mrz.get("document_number") and (effective_side == "back" or not identity_fields.get("document_number")):
        identity_fields["document_number"] = identity_card_mrz["document_number"]
    if identity_card_mrz.get("run") and (not identity_fields.get("run") or not validate_chile_run_checksum(identity_fields.get("run"))):
        identity_fields["run"] = identity_card_mrz["run"]
    if identity_card_mrz.get("birth_date") and (effective_side == "back" or not identity_fields.get("birth_date")):
        identity_fields["birth_date"] = identity_card_mrz["birth_date"]
    if identity_card_mrz.get("expiry_date") and (effective_side == "back" or not identity_fields.get("expiry_date")):
        identity_fields["expiry_date"] = identity_card_mrz["expiry_date"]
    if identity_card_mrz.get("sex") and not identity_fields.get("sex"):
        identity_fields["sex"] = identity_card_mrz["sex"]
    if identity_card_mrz.get("nationality") and not identity_fields.get("nationality"):
        identity_fields["nationality"] = _normalize_mrz_nationality(identity_card_mrz["nationality"], country)
    if effective_side == "back":
        if identity_card_mrz.get("first_names") and not identity_fields.get("first_names"):
            identity_fields["first_names"] = identity_card_mrz["first_names"]
        if identity_card_mrz.get("last_names") and not identity_fields.get("last_names"):
            identity_fields["last_names"] = identity_card_mrz["last_names"]
        if identity_card_mrz.get("holder_name") and (not identity_fields.get("holder_name") or is_placeholder_name(identity_fields.get("holder_name"))):
            identity_fields["holder_name"] = identity_card_mrz["holder_name"]
    back_fields = _extract_back_fields(lines, country)
    requires_front_fields = effective_side in {None, "front", "front+back"}
    requires_back_fields = effective_side in {"back", "front+back"}
    holder_name = identity_fields["holder_name"] or _find_holder_name(text) or "NOMBRE POR CONFIRMAR"
    issuer = supplemental.get("issuer") or _find_issuer(text, "identity") or "Registro / emisor por confirmar"
    document_number = identity_fields["document_number"]
    nationality = identity_fields["nationality"]
    run = identity_fields["run"]
    first_names = identity_fields["first_names"]
    last_names = identity_fields["last_names"]
    sex = identity_fields["sex"]
    birth_date = identity_fields["birth_date"]
    issue_date = identity_fields["issue_date"]
    expiry_date = identity_fields["expiry_date"]
    mrz = identity_card_mrz.get("mrz") or next((line.strip() for line in text.splitlines() if "<<" in line and len(line.strip()) > 20), None)

    issues: list[ValidationIssue] = []
    confidence = 0.54

    if document_number:
        confidence += 0.12
    else:
        issues.append(
            _make_issue(
                "issue-missing-document-number",
                "MISSING_FIELD",
                "Numero de documento",
                "medium",
                "No se detecto un numero documental claro en el texto disponible.",
                "Aplicar OCR visual o confirmar manualmente el identificador.",
            )
        )

    if birth_date:
        confidence += 0.06
    if issue_date:
        confidence += 0.05
    if expiry_date:
        confidence += 0.05
    if requires_front_fields and not any([birth_date, issue_date, expiry_date]):
        issues.append(
            _make_issue(
                "issue-missing-dates",
                "LOW_EVIDENCE",
                "Fechas",
                "low",
                "No se detectaron fechas suficientes para validar emision y vencimiento.",
                "Revisar visualmente frente y dorso del documento.",
            )
        )

    if run:
        confidence += 0.08
    elif country.upper() == "CL" and requires_front_fields:
        issues.append(
            _make_issue(
                "issue-missing-run",
                "MISSING_FIELD",
                "RUN",
                "medium",
                "No se detecto el RUN del documento en el OCR visual.",
                "Confirmar manualmente el RUN o mejorar la calidad de la imagen.",
            )
        )

    if first_names:
        confidence += 0.04
    if last_names:
        confidence += 0.04

    if mrz:
        confidence += 0.08
    elif country.upper() == "CL" and requires_front_fields:
        issues.append(
            _make_issue(
                "issue-missing-mrz",
                "LOW_EVIDENCE",
                "MRZ",
                "low",
                "No se detecto una linea MRZ o equivalente valida en el texto disponible.",
                "Confirmar manualmente la zona legible por maquina si aplica al tipo documental.",
            )
        )

    back_field_count = _non_empty_back_field_count(back_fields)
    if back_field_count:
        confidence += min(0.1, back_field_count * 0.02)
    elif requires_back_fields:
        issues.append(
            _make_issue(
                "issue-missing-back-fields",
                "LOW_EVIDENCE",
                "reverse_fields",
                "medium",
                "Se esperaba evidencia del dorso del documento, pero no se detectaron campos reversos suficientes.",
                "Confirmar si el archivo incluye dorso o reprocesar el documento con paginas separadas.",
            )
        )

    report_sections = [
        ReportSection(
            id="summary",
            title="Resumen",
            variant="pairs",
            rows=[
                ["Documento", "DOCUMENTO DE IDENTIDAD"],
                ["Archivo", filename],
                ["Pais", country],
                ["Lado", effective_side or "front"],
                ["Titular", holder_name],
                ["Numero", document_number or "NO DETECTADO"],
                ["RUN", run or "NO DETECTADO"],
                ["Emisor", issuer],
            ],
        ),
        ReportSection(
            id="dates",
            title="Fechas",
            variant="table",
            columns=["Campo", "Valor"],
            rows=(
                [["Fecha de nacimiento", birth_date or "-"], ["Fecha de emision", issue_date or "-"], ["Fecha de vencimiento", expiry_date or "-"]]
                if any([birth_date, issue_date, expiry_date])
                else [["Sin fechas detectadas", "-"]]
            ),
        ),
        ReportSection(
            id="identity",
            title="Identidad",
            variant="pairs",
            rows=[
                ["Nombre completo", holder_name],
                ["Nombres", first_names or "NO DETECTADOS"],
                ["Apellidos", last_names or "NO DETECTADOS"],
                ["Numero de documento", document_number or "NO DETECTADO"],
                ["Nacionalidad", nationality or "NO DETECTADA"],
                ["Sexo", sex or "NO DETECTADO"],
                ["RUN", run or "NO DETECTADO"],
                ["MRZ", mrz or "NO DETECTADA"],
            ],
        ),
        ReportSection(
            id="human-summary",
            title="Resumen humano",
            variant="text",
            body="Documento de identidad normalizado a partir de texto disponible. La revision humana sigue siendo recomendada para validar identificadores, fechas y coherencia frente/dorso.",
        ),
    ]

    if requires_back_fields or back_field_count:
        reverse_rows = []
        label_map = {
            "address": "Domicilio",
            "commune": "Comuna",
            "profession": "Profesion",
            "electoral_circ": "Circunscripcion",
            "civil_status": "Estado civil",
            "education": "Grado de instruccion",
            "donor": "Donacion de organos",
            "restriction": "Restriccion",
            "birth_place": "Lugar de nacimiento",
            "height": "Estatura",
            "blood_type": "Grupo sanguineo",
            "issue_place": "Lugar de expedicion",
        }
        for key, label in label_map.items():
            if key in back_fields:
                reverse_rows.append([label, back_fields.get(key) or "NO DETECTADO"])

        report_sections.insert(
            3,
            ReportSection(
                id="reverse",
                title="Dorso / campos reversos",
                variant="pairs",
                rows=reverse_rows or [["Sin campos reversos detectados", "-"]],
            ),
        )

    return NormalizedDocument(
        document_family="identity",
        country=country,
        variant=pack.variant if pack else ("identity-cl-front-text" if country.upper() == "CL" else "identity-text"),
        issuer=issuer,
        holder_name=holder_name,
        global_confidence=_calculate_identity_confidence(
            country=country,
            holder_name=holder_name,
            document_number=document_number,
            run=run,
            first_names=first_names,
            last_names=last_names,
            birth_date=birth_date,
            issue_date=issue_date,
            expiry_date=expiry_date,
            mrz=mrz,
            back_field_count=back_field_count,
            requires_front_fields=requires_front_fields,
            requires_back_fields=requires_back_fields,
        ),
        assumptions=[
            *assumptions,
            "La validacion de identidad permanece conservadora para evitar autoaprobacion agresiva.",
            "Se aplicaron heuristicas por pais para buscar identificadores, fechas y nombres antes de decidir review.",
            f"Contexto de lado documental: {effective_side or 'front'}.",
        ],
        issues=issues,
        report_sections=report_sections,
        human_summary="Extraccion heuristica de identidad basada en texto detectado, con decision orientada a revision humana.",
    )


def _find_generic_label_value(lines: list[str], keywords: tuple[str, ...], predicate=None) -> str | None:
    normalized_keywords = tuple(_normalize_key(keyword) for keyword in keywords)
    for index, line in enumerate(lines):
        normalized_line = _normalize_key(line)
        if not any(keyword in normalized_line for keyword in normalized_keywords):
            continue
        candidates = [line]
        if index + 1 < len(lines):
            candidates.append(lines[index + 1])
        for candidate in candidates:
            cleaned = _clean(candidate)
            if cleaned and (predicate(cleaned) if predicate else True):
                return cleaned
    return None


def normalize_passport_text(text: str, country: str, filename: str, assumptions: list[str], supplemental_fields: dict[str, str] | None = None) -> NormalizedDocument:
    lines = _lines(text)
    mrz_fields = parse_passport_mrz(text)
    supplemental = supplemental_fields or {}
    document_number = canonicalize_passport_number(
        supplemental.get("document_number")
        or supplemental.get("passport_number")
        or mrz_fields.get("document_number")
        or _find_regex_value(PASSPORT_NUMBER_PATTERN, text)
        or _find_label_value(lines, "PASSPORT NUMBER", "NUMERO PASAPORTE", "PASAPORTE", predicate=lambda value: bool(PASSPORT_NUMBER_PATTERN.search(strip_accents(value).upper())), max_distance=4)
    )
    given_index = _find_label_index(lines, "GIVEN NAMES", "NOMBRES/GIVENNAMES", "NOMBRES/GIVEN NAMES", "NOMBRES")
    given_names = _find_nearby_value(lines, given_index, lambda value: bool(_clean(value)) and len(strip_accents(value)) <= 32 and not any(char.isdigit() for char in value), max_distance=2, prefer_backward=True)
    surname_index = _find_label_index(lines, "SURNAME", "SURNAMES", "APELLIDOS/SURNAMES", "APELLIDOS")
    surnames = _find_nearby_value(lines, surname_index, lambda value: bool(_clean(value)) and len(strip_accents(value)) <= 40 and not any(char.isdigit() for char in value), max_distance=3)
    if surname_index is not None:
        surname_candidates = [line for line in lines[surname_index + 1 : surname_index + 3] if UPPERCASE_LINE_PATTERN.match(strip_accents(line).upper())]
        if surname_candidates:
            combined_surnames = _clean(" ".join(surname_candidates))
            if combined_surnames:
                surnames = combined_surnames
    holder_name = supplemental.get("holder_name") or mrz_fields.get("holder_name") or _clean(" ".join(part for part in [given_names, surnames] if part)) or _find_label_value(lines, "NAME", "NOMBRE", predicate=lambda value: bool(_clean(value)))
    if holder_name and (not given_names or not surnames):
        parts = holder_name.split()
        if len(parts) >= 3:
            given_names = given_names or " ".join(parts[:-2])
            surnames = surnames or " ".join(parts[-2:])
    nationality_index = _find_label_index(lines, "NATIONALITY", "NACIONALIDAD")
    nationality = supplemental.get("nationality") or _normalize_mrz_nationality(mrz_fields.get("nationality"), country)
    if not nationality:
        nationality_match = re.search(r"\b(CHILENA|PERUANA|COLOMBIANA)\b", strip_accents(text).upper())
        nationality = _clean(nationality_match.group(1)) if nationality_match else None
    if not nationality:
        nationality = _find_nearby_value(lines, nationality_index, lambda value: bool(_clean(value)) and len(value) <= 20 and not any(char.isdigit() for char in value), max_distance=2)
    if not nationality:
        nationality = {"CL": "CHILENA", "PE": "PERUANA", "CO": "COLOMBIANA"}.get(country.upper(), country)
    textual_dates = _find_textual_dates(text)
    birth_index = _find_label_index(lines, "DATE OF BIRTH", "FECHA DE NACIMIENTO")
    birth_date = supplemental.get("birth_date") or mrz_fields.get("birth_date") or _strict_normalize_date(_find_nearby_value(lines, birth_index, lambda value: bool(_strict_normalize_date(value)), max_distance=2))
    expiry_index = _find_label_index(lines, "DATE OF EXPIRY", "FECHA DE VENCIMIENTO", "EXPIRY")
    expiry_date = supplemental.get("expiry_date") or mrz_fields.get("expiry_date") or _strict_normalize_date(_find_nearby_value(lines, expiry_index, lambda value: bool(_strict_normalize_date(value)), max_distance=2))
    issue_index = _find_label_index(lines, "DATE OF ISSUE", "FECHA DE EMISION")
    issue_date = supplemental.get("issue_date") or _strict_normalize_date(_find_nearby_value(lines, issue_index, lambda value: bool(_strict_normalize_date(value)), max_distance=2))
    if textual_dates:
        sorted_dates = sorted(textual_dates)
        if birth_date is None:
            birth_date = sorted_dates[0]
        if expiry_date is None and len(sorted_dates) >= 2:
            expiry_date = sorted_dates[-1]
        if issue_date is None and len(sorted_dates) >= 3:
            issue_date = sorted_dates[-2]
    sex_index = _find_label_index(lines, "SEXO/SEX", "SEX")
    sex = supplemental.get("sex") or _find_nearby_value(lines, sex_index, lambda value: value.strip().upper() in {"M", "F"}, max_distance=1) or ("F" if re.search(r"\bF\b", strip_accents(text).upper()) else "M" if re.search(r"\bM\b", strip_accents(text).upper()) else None)
    place_index = _find_label_index(lines, "PLACE OF BIRTH", "LUGAR DE NACIMIENTO")
    place_of_birth = supplemental.get("place_of_birth") or _find_nearby_value(lines, place_index, lambda value: bool(_clean(value)) and len(value) <= 30 and not any(char.isdigit() for char in value), max_distance=2)
    if not place_of_birth:
        place_match = re.search(r"LUGAR\s*DE\s*NACIMIENTO[^A-Z0-9]+([A-Z ]{3,30})\s+(?:\d{2}|FECHA)", strip_accents(text).upper())
        if place_match:
            place_of_birth = _clean(place_match.group(1))
    if not place_of_birth and surname_index is not None:
        place_candidates = [line for line in lines[surname_index + 1 : surname_index + 6] if UPPERCASE_LINE_PATTERN.match(strip_accents(line).upper()) and line not in {nationality or '', 'REPUBLICA DE CHILE'} and not any(char.isdigit() for char in line)]
        place_of_birth = _clean(place_candidates[0]) if place_candidates else None
    authority_index = _find_label_index(lines, "ISSUING AUTHORITY", "AUTORIDAD EMISORA")
    issuer_match = re.search(r"SERVICIO\s+DE\s+REGISTRO\s+CIVIL(?:\s+E\s+IDENTIFICACION)?", strip_accents(text).upper())
    issuer = supplemental.get("issuer") or (_clean(issuer_match.group(0).title()) if issuer_match else None)
    if not issuer:
        issuer = _find_nearby_value(lines, authority_index, lambda value: bool(_clean(value)) and len(value) <= 80 and "<" not in value and "AUTORIDAD" not in strip_accents(value).upper(), max_distance=2)
    if not issuer:
        issuer = country
    mrz_value = mrz_fields.get("mrz")

    issues: list[ValidationIssue] = []
    if not document_number:
        issues.append(_make_issue("passport-document-number", "MISSING_FIELD", "document_number", "medium", "No se detecto numero de pasaporte claro.", "Verificar la zona de datos o la MRZ."))
    if not holder_name:
        issues.append(_make_issue("passport-holder-name", "MISSING_FIELD", "holder_name", "medium", "No se detecto nombre completo del pasaporte.", "Reprocesar con mejor OCR o verificar la zona visual."))
    if not expiry_date:
        issues.append(_make_issue("passport-expiry-date", "LOW_EVIDENCE", "expiry_date", "low", "No se detecto fecha de vencimiento clara.", "Usar MRZ o revisar visualmente."))
    if not mrz_value:
        issues.append(_make_issue("passport-mrz-missing", "LOW_EVIDENCE", "mrz", "low", "No se reconstruyo MRZ completa del pasaporte.", "Usar OCR especializado sobre la zona MRZ."))

    report_sections = [
        ReportSection(id="summary", title="Resumen", variant="pairs", rows=[["Documento", "PASAPORTE"], ["Archivo", filename], ["Pais", country], ["Titular", holder_name or "NO DETECTADO"], ["Numero", document_number or "NO DETECTADO"], ["Nacionalidad", nationality or "NO DETECTADA"]]),
        ReportSection(id="dates", title="Fechas", variant="table", columns=["Campo", "Valor"], rows=[["Fecha de nacimiento", birth_date or "NO DETECTADA"], ["Fecha de emision", issue_date or "NO DETECTADA"], ["Fecha de vencimiento", expiry_date or "NO DETECTADA"]]),
        ReportSection(id="passport", title="Pasaporte", variant="pairs", rows=[["Nombre completo", holder_name or "NO DETECTADO"], ["Apellidos", surnames or "NO DETECTADO"], ["Nombres", given_names or "NO DETECTADO"], ["Numero de documento", document_number or "NO DETECTADO"], ["Nacionalidad", nationality or "NO DETECTADA"], ["Sexo", sex or "NO DETECTADO"], ["Lugar de nacimiento", place_of_birth or "NO DETECTADO"], ["Autoridad", issuer or "NO DETECTADA"], ["MRZ", mrz_value or "NO DETECTADA"]]),
    ]

    return NormalizedDocument(
        document_family="passport",
        country=country or nationality or "XX",
        variant="passport-text",
        issuer=issuer,
        holder_name=holder_name,
        global_confidence=_calculate_passport_confidence(
            holder_name=holder_name,
            document_number=document_number,
            birth_date=birth_date,
            issue_date=issue_date,
            expiry_date=expiry_date,
            nationality=nationality,
            sex=sex,
            place_of_birth=place_of_birth,
            mrz_value=mrz_value,
        ),
        assumptions=[*assumptions, "Se aplicaron heuristicas de pasaporte con soporte MRZ cuando estuvo disponible."],
        issues=issues,
        report_sections=report_sections,
        human_summary="Extraccion heuristica de pasaporte basada en zona visual y MRZ.",
    )


def normalize_driver_license_text(text: str, country: str, filename: str, assumptions: list[str], supplemental_fields: dict[str, str] | None = None) -> NormalizedDocument:
    lines = _lines(text)
    supplemental = supplemental_fields or {}
    first_name, last_name, holder_name = _extract_driver_license_name(lines)
    if supplemental.get("holder_name"):
        holder_name = supplemental["holder_name"]
    if supplemental.get("first_name"):
        first_name = supplemental["first_name"]
    if supplemental.get("last_name"):
        last_name = supplemental["last_name"]
    document_number = supplemental.get("document_number") or canonicalize_chile_run(_find_first(RUT_PATTERN, text)) or _find_generic_label_value(lines, ("LICENSE NO", "LICENCE NO", "NUMERO DE LICENCIA", "NRO LICENCIA"), predicate=lambda value: bool(canonicalize_chile_run(value)))
    normalized_dates = _find_all_normalized_dates(text)
    birth_date = supplemental.get("birth_date") or _strict_normalize_date(_find_generic_label_value(lines, ("DATE OF BIRTH", "FECHA DE NACIMIENTO")))
    issue_date = supplemental.get("issue_date") or _strict_normalize_date(_find_generic_label_value(lines, ("ISSUE DATE", "FECHA DE EMISION", "EXPEDICION", "FECHAULTIMOCONTROL")))
    expiry_date = supplemental.get("expiry_date") or _strict_normalize_date(_find_generic_label_value(lines, ("EXPIRY", "VALID UNTIL", "FECHA DE VENCIMIENTO", "FECHADECONTROLD")))
    if normalized_dates:
        sorted_dates = sorted(normalized_dates)
        if issue_date is None:
            issue_date = sorted_dates[0]
        if expiry_date is None and len(sorted_dates) >= 2:
            expiry_date = sorted_dates[-1]
    authority = supplemental.get("authority") or next((line for line in lines if line in {"LA REINA", "SANTIAGO", "PROVIDENCIA", "NUNOA"}), None)
    categories = supplemental.get("categories") or _find_generic_label_value(lines, ("CLASS", "CATEGORIES", "CATEGORIAS", "CAT"), predicate=lambda value: len(value.strip()) <= 6 and value.strip().upper() in {"A", "A1", "A2", "B", "C", "D", "E"})
    address = supplemental.get("address") or _find_label_value(lines, "DIRECCION", "ADDRESS", predicate=lambda value: bool(_clean(value)), max_distance=2)
    nationality = supplemental.get("nationality") or ({"CL": "CHILE", "PE": "PERU", "CO": "COLOMBIA"}.get(country.upper()) if country else None)

    issues: list[ValidationIssue] = []
    if not document_number:
        issues.append(_make_issue("driver-document-number", "MISSING_FIELD", "document_number", "medium", "No se detecto numero de licencia claro.", "Verificar la zona principal del documento."))
    if not holder_name:
        issues.append(_make_issue("driver-holder-name", "MISSING_FIELD", "holder_name", "medium", "No se detecto titular claro de la licencia.", "Reprocesar con mejor recorte o contraste."))
    if not expiry_date:
        issues.append(_make_issue("driver-expiry-missing", "LOW_EVIDENCE", "expiry_date", "low", "No se detecto vencimiento claro en la licencia.", "Revisar fechas o aplicar OCR adicional."))

    report_sections = [
        ReportSection(id="summary", title="Resumen", variant="pairs", rows=[["Documento", "LICENCIA"], ["Archivo", filename], ["Pais", country], ["Titular", holder_name or "NO DETECTADO"], ["Numero", document_number or "NO DETECTADO"], ["Categorias", categories or "NO DETECTADAS"]]),
        ReportSection(id="dates", title="Fechas", variant="table", columns=["Campo", "Valor"], rows=[["Fecha de nacimiento", birth_date or "NO DETECTADA"], ["Fecha de emision", issue_date or "NO DETECTADA"], ["Fecha de vencimiento", expiry_date or "NO DETECTADA"]]),
        ReportSection(id="driver-license", title="Licencia de conducir", variant="pairs", rows=[["Nombre completo", holder_name or "NO DETECTADO"], ["Primer nombre", first_name or "NO DETECTADO"], ["Apellidos", last_name or "NO DETECTADO"], ["Numero de documento", document_number or "NO DETECTADO"], ["Categorias", categories or "NO DETECTADAS"], ["Autoridad emisora", authority or "NO DETECTADA"], ["Direccion", address or "NO DETECTADA"], ["Nacionalidad", nationality or "NO DETECTADA"]]),
    ]

    return NormalizedDocument(
        document_family="driver_license",
        country=country or "XX",
        variant="driver-license-text",
        issuer=authority or "Autoridad de transito / conducir",
        holder_name=holder_name,
        global_confidence=_calculate_driver_license_confidence(
            country=country or "XX",
            holder_name=holder_name,
            document_number=document_number,
            birth_date=birth_date,
            issue_date=issue_date,
            expiry_date=expiry_date,
            categories=categories,
            authority=authority,
            address=address,
            nationality=nationality,
        ),
        assumptions=[*assumptions, "Se aplicaron heuristicas genericas para licencias de conducir."],
        issues=issues,
        report_sections=report_sections,
        human_summary="Extraccion heuristica de licencia de conducir basada en labels comunes.",
    )


def normalize_text_with_heuristics(
    document_family: str,
    country: str,
    filename: str,
    text: str,
    assumptions: list[str],
    variant: str | None = None,
    pack_id: str | None = None,
    document_side: str | None = None,
    supplemental_fields: dict[str, str] | None = None,
) -> NormalizedDocument:
    if document_family == "identity":
        return normalize_identity_text(text, country, filename, assumptions, pack_id=pack_id, document_side=document_side, supplemental_fields=supplemental_fields)
    if document_family == "passport":
        return normalize_passport_text(text, country, filename, assumptions, supplemental_fields=supplemental_fields)
    if document_family == "driver_license":
        return normalize_driver_license_text(text, country, filename, assumptions, supplemental_fields=supplemental_fields)

    return normalize_certificate_text(text, country, filename, assumptions)
