from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.document_packs import DOCUMENT_PACKS, normalize_requested_country, normalize_requested_family
from app.services.field_value_utils import parse_identity_card_mrz


@dataclass
class DocumentClassification:
    document_family: str
    country: str
    variant: str | None
    pack_id: str | None
    pack_version: str | None
    document_side: str | None
    confidence: float
    reasons: list[str]
    supported: bool


def _normalize_text(text: str) -> str:
    return " ".join((text or "").upper().split())


def _compact_text(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def _keyword_present(text: str, compact_text: str, keyword: str) -> bool:
    normalized_keyword = " ".join(keyword.upper().split())
    compact_keyword = _compact_text(normalized_keyword)
    return normalized_keyword in text or compact_keyword in compact_text


def _contains_any(text: str, compact_text: str, keywords: tuple[str, ...]) -> bool:
    return any(_keyword_present(text, compact_text, keyword) for keyword in keywords)


def _has_mrz_pattern(text: str) -> bool:
    return bool(re.search(r"<{4,}", text))


def _mrz_country_hint(text: str) -> str | None:
    match = re.search(r"P<([A-Z]{3})", text)
    if not match:
        return None
    country = match.group(1)
    return {"CHL": "CL", "PER": "PE", "COL": "CO"}.get(country)


def _detect_family_hint(text: str) -> tuple[str, list[str]]:
    normalized_text = _normalize_text(text)
    reasons: list[str] = []
    compact_text = _compact_text(normalized_text)
    identity_card_mrz = parse_identity_card_mrz(text)

    if identity_card_mrz.get("mrz"):
        reasons.append("Detected identity-card style MRZ content.")
        return "identity", reasons

    if _contains_any(normalized_text, compact_text, ("NACIO EN", "DOMICILIO", "COMUNA", "PROFESION", "INCHL", "I<CHL", "NACICAN")):
        reasons.append("Detected identity-card back-side wording or Chilean TD1 fragments.")
        return "identity", reasons

    if _contains_any(normalized_text, compact_text, ("PASSPORT", "PASAPORTE")) or _has_mrz_pattern(normalized_text):
        reasons.append("Detected passport-like wording or strong MRZ content.")
        return "passport", reasons

    if _contains_any(normalized_text, compact_text, ("LICENCIA", "CONDUC", "DRIVER LICENSE", "DRIVING LICENCE", "BREVETE", "PERMISO DE CONDUCIR")):
        reasons.append("Detected driving-license wording.")
        return "driver_license", reasons

    if _contains_any(normalized_text, compact_text, ("FACTURA", "INVOICE", "RUC", "COMPROBANTE DE PAGO")):
        reasons.append("Detected invoice wording.")
        return "invoice", reasons

    if _contains_any(
        normalized_text,
        compact_text,
        (
            "CEDULA DE IDENTIDAD",
            "DOCUMENTO NACIONAL DE IDENTIDAD",
            "CEDULA DE CIUDADANIA",
            "DNI",
            "CUI",
            "NUIP",
        ),
    ):
        reasons.append("Detected identity-document wording.")
        return "identity", reasons

    if _contains_any(normalized_text, compact_text, ("CERTIFICADO", "CONSTANCIA LABORAL", "CERTIFICACION LABORAL", "COTIZACIONES", "AFP")):
        reasons.append("Detected certificate wording.")
        return "certificate", reasons

    return "unclassified", reasons


def _detect_country_hint(text: str) -> tuple[str, list[str]]:
    normalized_text = _normalize_text(text)
    reasons: list[str] = []
    compact_text = _compact_text(normalized_text)
    identity_card_mrz = parse_identity_card_mrz(text)
    issuing_country = (identity_card_mrz.get("issuing_country") or "").upper()
    if issuing_country in {"CL", "PE", "CO"}:
        reasons.append("Detected ICAO-style identity-card MRZ country code.")
        return issuing_country, reasons

    if _contains_any(normalized_text, compact_text, ("INCHL", "I<CHL", "NACICAN", "REPUBLICA DE CHILE", "REGISTRO CIVIL E IDENTIFICACION")):
        reasons.append("Detected Chilean identity-card wording or TD1 fragments.")
        return "CL", reasons

    mrz_country = _mrz_country_hint(normalized_text)
    if mrz_country:
        reasons.append("Detected ICAO-style MRZ country code.")
        return mrz_country, reasons

    if _contains_any(normalized_text, compact_text, ("REPUBLICA DE CHILE", "REGISTRO CIVIL E IDENTIFICACION", "RUN")):
        reasons.append("Detected Chilean authority or identifier wording.")
        return "CL", reasons

    if _contains_any(
        normalized_text,
        compact_text,
        (
            "REPUBLICA DEL PERU",
            "REPUBLICA DEL PERO",
            "DOCUMENTO NACIONAL DE IDENTIDAD",
            "RENIEC",
            "CUI",
            "MIGRACIONES",
        ),
    ):
        reasons.append("Detected Peruvian DNI wording.")
        return "PE", reasons

    if _contains_any(
        normalized_text,
        compact_text,
        (
            "REPUBLICA DE COLOMBIA",
            "REGISTRADURIA",
            "CEDULA DE CIUDADANIA",
            "NUIP",
            "COLOMBIA",
        ),
    ):
        reasons.append("Detected Colombian identity wording.")
        return "CO", reasons

    return "XX", reasons


def _detect_side_hint(text: str, family_hint: str, country_hint: str) -> str | None:
    normalized_text = _normalize_text(text)
    compact_text = _compact_text(normalized_text)

    if family_hint != "identity":
        return None

    if country_hint == "CL":
        if _contains_any(normalized_text, compact_text, ("NACIO EN", "DOMICILIO", "COMUNA", "PROFESION", "CIRCUNSCRIPCION", "HUELLA")):
            return "back"
        if _contains_any(normalized_text, compact_text, ("NOMBRES", "APELLIDOS", "RUN", "SEXO", "FECHA DE NACIMIENTO")):
            return "front"

    if country_hint == "PE":
        if _contains_any(normalized_text, compact_text, ("DOMICILIO", "ESTADO CIVIL", "GRADO DE INSTRUCCION", "DONACION DE ORGANOS", "RESTRICCION")):
            return "back"
        if _contains_any(normalized_text, compact_text, ("NOMBRES", "APELLIDOS", "DNI", "FECHA DE NACIMIENTO")):
            return "front"

    if country_hint == "CO":
        if _contains_any(normalized_text, compact_text, ("LUGAR DE NACIMIENTO", "ESTATURA", "G.S. RH", "EXPEDICION")):
            return "back"
        if _contains_any(normalized_text, compact_text, ("NOMBRES", "APELLIDOS", "CEDULA", "NUIP")):
            return "front"

    return None


def _score_pack(normalized_text: str, requested_family: str, requested_country: str, family_hint: str, country_hint: str, side_hint: str | None, pack) -> tuple[float, list[str]]:
    score = 0.22
    reasons: list[str] = []
    compact_text = _compact_text(normalized_text)

    if requested_family != "unclassified":
        if requested_family == pack.document_family:
            score += 0.2
            reasons.append("Requested family aligned with candidate pack.")
        else:
            score -= 0.18

    if requested_country != "XX":
        if requested_country == pack.country:
            score += 0.16
            reasons.append("Requested country aligned exactly with candidate pack.")
        elif pack.country == "XX":
            score += 0.08
            reasons.append("Requested country aligned with generic candidate pack.")
        else:
            score -= 0.12

    if family_hint != "unclassified" and family_hint == pack.document_family:
        score += 0.22
        reasons.append("Textual family hint matched candidate pack.")
    elif family_hint != "unclassified" and family_hint != pack.document_family:
        score -= 0.18

    if country_hint != "XX":
        if country_hint == pack.country:
            score += 0.16
            reasons.append("Textual country hint matched candidate pack.")
        elif pack.country == "XX":
            score += 0.08
            reasons.append("Textual country hint matched generic candidate pack.")

    keyword_matches = [keyword for keyword in pack.classification_keywords if _keyword_present(normalized_text, compact_text, keyword)]
    if keyword_matches:
        score += min(0.4, 0.08 * len(keyword_matches))
        reasons.append(f"Matched keywords: {', '.join(keyword_matches[:4])}.")

    if family_hint == "unclassified" and pack.document_family == "identity" and country_hint == pack.country and keyword_matches:
        score += 0.08
        reasons.append("Boosted identity pack because country-specific identity hints were present.")

    if side_hint and pack.document_side:
        if side_hint == pack.document_side:
            score += 0.12
            reasons.append("Document-side hint matched candidate pack.")
        else:
            score -= 0.08

    return score, reasons


def classify_document(text: str, requested_family: str, requested_country: str) -> DocumentClassification:
    normalized_text = _normalize_text(text)
    requested_family_normalized = normalize_requested_family(requested_family)
    requested_country_normalized = normalize_requested_country(requested_country)

    family_hint, family_reasons = _detect_family_hint(text)
    country_hint, country_reasons = _detect_country_hint(text)
    side_hint = _detect_side_hint(text, family_hint, country_hint)

    best_pack = None
    best_score = -1.0
    best_reasons: list[str] = []

    for pack in DOCUMENT_PACKS:
        score, reasons = _score_pack(
            normalized_text,
            requested_family_normalized,
            requested_country_normalized,
            family_hint,
            country_hint,
            side_hint,
            pack,
        )
        if score > best_score:
            best_pack = pack
            best_score = score
            best_reasons = reasons

    reasons = [*family_reasons, *country_reasons, *best_reasons]

    if best_pack and best_score >= 0.48:
        detected_country = best_pack.country if best_pack.country != "XX" else (requested_country_normalized if requested_country_normalized != "XX" else country_hint)
        return DocumentClassification(
            document_family=best_pack.document_family,
            country=detected_country if detected_country != "XX" else requested_country_normalized,
            variant=best_pack.variant,
            pack_id=best_pack.pack_id,
            pack_version=best_pack.version,
            document_side=best_pack.document_side,
            confidence=min(best_score, 0.97),
            reasons=reasons or ["Classification matched a registered document pack."],
            supported=best_pack.supported,
        )

    detected_family = family_hint if family_hint != "unclassified" else requested_family_normalized
    detected_country = country_hint if country_hint != "XX" else requested_country_normalized

    if detected_family == "unclassified" and requested_family_normalized != "unclassified":
        detected_family = requested_family_normalized
        reasons.append("Fell back to requested family because no pack scored high enough.")

    if detected_country == "XX" and requested_country_normalized != "XX":
        detected_country = requested_country_normalized
        reasons.append("Fell back to requested country because no country hint was found.")

    return DocumentClassification(
        document_family=detected_family,
        country=detected_country,
        variant=None,
        pack_id=None,
        pack_version=None,
        document_side=None,
        confidence=0.34 if normalized_text else 0.18,
        reasons=reasons or ["Document remained unclassified after pack scoring."],
        supported=False,
    )
