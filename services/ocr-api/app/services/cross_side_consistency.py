from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.page_analysis import PageAnalysisResult
from app.services.field_value_utils import (
    canonicalize_chile_run,
    canonicalize_identity_document_number,
    parse_identity_card_mrz,
    parse_identity_card_td1_fallback,
    validate_chile_run_checksum,
)

CL_RUT_PATTERN = re.compile(r"\b(?:\d{1,2}\.?\d{3}\.?\d{3}|\d{7,8})-[\dkK]\b")
PE_DNI_PATTERN = re.compile(r"\b\d{8}\b")
CO_CEDULA_PATTERN = re.compile(r"\b\d{6,10}\b")


@dataclass(frozen=True)
class CrossSideConsistencySignal:
    front_present: bool
    back_present: bool
    front_identifier: str | None
    back_identifier: str | None
    identifier_match: bool | None
    assumptions: list[str]


def _identifier_pattern(country: str) -> re.Pattern[str]:
    normalized_country = country.upper()
    if normalized_country == "CL":
        return CL_RUT_PATTERN
    if normalized_country == "PE":
        return PE_DNI_PATTERN
    return CO_CEDULA_PATTERN


def _label_hints(country: str) -> tuple[str, ...]:
    normalized_country = country.upper()
    if normalized_country == "CL":
        return ("RUN", "RUT", "NUMERO", "DOCUMENTO")
    if normalized_country == "PE":
        return ("DNI", "NUMERO", "DOCUMENTO")
    return ("CEDULA", "IDENTIFICACION", "NUMERO", "DOCUMENTO")


def _extract_identifiers(side_text: str, country: str) -> list[str]:
    text = side_text or ""
    if not text.strip():
        return []

    normalized_country = country.upper()
    pattern = _identifier_pattern(normalized_country)
    hints = _label_hints(country)
    values: list[str] = []

    def canonicalize(value: str) -> str | None:
        if normalized_country == "CL":
            normalized = canonicalize_chile_run(value)
            if normalized and "-" in normalized and validate_chile_run_checksum(normalized):
                return re.sub(r"[.\s]", "", normalized).upper()
            document_number = canonicalize_identity_document_number(normalized_country, value)
            if document_number and re.fullmatch(r"[A-Z]{1,2}\d{1,3}\.\d{3}\.\d{3}", document_number):
                return re.sub(r"[.\s]", "", document_number).upper()
            return None
        normalized = canonicalize_identity_document_number(normalized_country, value)
        if not normalized or not any(char.isdigit() for char in normalized):
            return None
        return normalized

    def add(value: str | None) -> None:
        if not value:
            return
        if value not in values:
            values.append(value)

    if normalized_country == "CL":
        td1 = parse_identity_card_mrz(text)
        add(canonicalize(td1.get("run") or ""))
        doc_value = canonicalize_identity_document_number(normalized_country, td1.get("document_number"))
        add(re.sub(r"[.\s]", "", doc_value).upper() if doc_value else None)
        td1_fallback = parse_identity_card_td1_fallback(text)
        add(canonicalize(td1_fallback.get("run") or ""))
        fallback_doc_value = canonicalize_identity_document_number(normalized_country, td1_fallback.get("document_number"))
        add(re.sub(r"[.\s]", "", fallback_doc_value).upper() if fallback_doc_value else None)

    for line in text.splitlines():
        normalized_line = line.upper()
        if not any(hint in normalized_line for hint in hints):
            continue
        match = pattern.search(line)
        if match:
            add(canonicalize(match.group(0)) or match.group(0))
        normalized_line_value = canonicalize(line)
        if normalized_line_value:
            add(normalized_line_value)

    if normalized_country == "CL":
        for line in text.splitlines():
            doc_value = canonicalize_identity_document_number(normalized_country, line)
            if doc_value:
                add(re.sub(r"[.\s]", "", doc_value).upper())

    distinct_matches = list(dict.fromkeys(pattern.findall(text)))
    for match in distinct_matches:
        add(canonicalize(match) or match)
    return values


def build_cross_side_consistency_signal(page_analysis: PageAnalysisResult, page_texts: list[str], country: str) -> CrossSideConsistencySignal | None:
    if not page_analysis.cross_side_detected:
        return None

    front_pages = [result.page_number for result in page_analysis.pages if result.classification.document_side == "front"]
    back_pages = [result.page_number for result in page_analysis.pages if result.classification.document_side == "back"]
    front_text = "\n".join(page_texts[page_number - 1] for page_number in front_pages if 0 < page_number <= len(page_texts))
    back_text = "\n".join(page_texts[page_number - 1] for page_number in back_pages if 0 < page_number <= len(page_texts))
    front_identifiers = _extract_identifiers(front_text, country)
    back_identifiers = _extract_identifiers(back_text, country)
    shared_identifier = next((identifier for identifier in front_identifiers if identifier in back_identifiers), None)
    front_identifier = shared_identifier or (front_identifiers[0] if front_identifiers else None)
    back_identifier = shared_identifier or (back_identifiers[0] if back_identifiers else None)
    assumptions = ["Se evaluo consistencia cross-side a partir de paginas clasificadas como frente/dorso."]

    if shared_identifier:
        assumptions.append("Se encontro al menos un identificador coincidente entre frente y dorso.")
        return CrossSideConsistencySignal(
            front_present=bool(front_pages),
            back_present=bool(back_pages),
            front_identifier=shared_identifier,
            back_identifier=shared_identifier,
            identifier_match=True,
            assumptions=assumptions,
        )

    if front_identifier and back_identifier:
        assumptions.append("Se detectaron identificadores tanto en frente como en dorso para comparacion.")
        return CrossSideConsistencySignal(
            front_present=bool(front_pages),
            back_present=bool(back_pages),
            front_identifier=front_identifier,
            back_identifier=back_identifier,
            identifier_match=False,
            assumptions=assumptions,
        )

    if front_identifier or back_identifier:
        assumptions.append("Solo uno de los lados contiene identificador utilizable para comparacion cross-side.")
    else:
        assumptions.append("No se detectaron identificadores comparables en frente/dorso.")

    return CrossSideConsistencySignal(
        front_present=bool(front_pages),
        back_present=bool(back_pages),
        front_identifier=front_identifier,
        back_identifier=back_identifier,
        identifier_match=None,
        assumptions=assumptions,
    )
