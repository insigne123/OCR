from __future__ import annotations

from io import BytesIO
import re

from PIL import Image, ImageEnhance, ImageOps

from app.engines.azure_document_intelligence import has_azure_document_intelligence_config
from app.engines.factory import get_visual_ocr_engine
from app.services.field_value_utils import canonicalize_chile_run, canonicalize_identity_document_number, normalize_date_value, parse_identity_card_mrz
from app.services.page_preprocessing import PreprocessedPage

CHILE_ADDRESS_WORDS = (
    "ALVARO",
    "CASANOVA",
    "AV",
    "AVENIDA",
    "PASAJE",
    "CALLE",
    "CASA",
    "DEPTO",
    "DEPARTAMENTO",
)
COMMON_GIVEN_NAMES = ("NICOLAS", "PAOLA", "ANDREA", "SOFIA", "MATEO", "JUAN", "MARIA", "JOSE")
TEXTUAL_DATE_PATTERN = re.compile(r"\b\d{2}\s*[A-Z]{3}\s*\d{4}\b")
LABELLED_DATE_PATTERN = re.compile(
    r"(FECHA\s+DE\s+NACIMIENTO|FECHA\s+DE\s+EMISION|FECHA\s+DE\s+VENCIMIENTO)\s*([0-9A-Z ]{7,16})",
    re.IGNORECASE,
)


def _crop_image(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    return image.crop((int(width * box[0]), int(height * box[1]), int(width * box[2]), int(height * box[3]))).convert("RGB")


def _ocr_crop(image: Image.Image, box: tuple[float, float, float, float], engine_name: str = "rapidocr") -> str:
    crop = _crop_image(image, box)
    crop = ImageOps.autocontrast(crop, cutoff=1)
    crop = ImageEnhance.Contrast(crop).enhance(1.25)
    if crop.width < 600 or crop.height < 200:
        crop = crop.resize((crop.width * 2, crop.height * 2))
    output = BytesIO()
    crop.save(output, format="PNG")
    result = get_visual_ocr_engine(engine_name).run([output.getvalue()])
    return (result.text or "") if result else ""


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _cleanup_driver_address(text: str) -> str | None:
    candidate = re.sub(r"[^A-Z0-9 ]+", " ", text.upper())
    candidate = candidate.replace("DIRECCION", " ").replace("DIRECOKON", " ")
    candidate = re.sub(r"([A-Z])([0-9])", r"\1 \2", candidate)
    candidate = re.sub(r"([0-9])([A-Z])", r"\1 \2", candidate)
    candidate = _normalize_spaces(candidate)
    if not candidate:
        return None

    for word in CHILE_ADDRESS_WORDS:
        compact_word = word.replace(" ", "")
        candidate = re.sub(compact_word, word, candidate)
    candidate = candidate.replace("CASAJ", "CASA J")
    candidate = _normalize_spaces(candidate)
    if not any(char.isdigit() for char in candidate):
        return None
    tokens = candidate.split()
    number_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if token.isdigit() and len(token) <= 5 and int(token) < 1900 and index >= 2 and all(tokens[index - offset].isalpha() for offset in (1, 2))
        ),
        None,
    )
    if number_index is None:
        return None
    start_index = max(0, number_index - 2)
    address_tokens = tokens[start_index : number_index + 1]
    suffix_index = number_index + 1
    while suffix_index < len(tokens) and tokens[suffix_index] in {"CASA", "DEPTO", "DEPARTAMENTO", "OF", "J", "A", "B", "C"}:
        address_tokens.append(tokens[suffix_index])
        suffix_index += 1
    candidate = _normalize_spaces(" ".join(address_tokens))
    return candidate if len(candidate) >= 8 else None


def _extract_normalized_dates(text: str) -> list[str]:
    values: list[str] = []
    for match in TEXTUAL_DATE_PATTERN.findall(text.upper()):
        normalized = normalize_date_value(match)
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _normalize_identity_compact_name(token: str) -> str | None:
    compact = re.sub(r"[^A-Z]", "", token.upper())
    for given_name in sorted(COMMON_GIVEN_NAMES, key=len, reverse=True):
        if compact.startswith(given_name) and len(compact) > len(given_name) + 2:
            return _normalize_spaces(f"{given_name} {compact[len(given_name):]}")
    return _normalize_spaces(token) if token else None


def _extract_identity_front_dates(text: str) -> dict[str, str]:
    normalized = _normalize_spaces(text.upper())
    values: dict[str, str] = {}

    for label, raw_value in LABELLED_DATE_PATTERN.findall(normalized):
        parsed = normalize_date_value(raw_value)
        if not parsed:
            continue
        upper_label = label.upper()
        if "NACIMIENTO" in upper_label:
            values["birth_date"] = parsed
        elif "EMISION" in upper_label:
            values["issue_date"] = parsed
        elif "VENCIMIENTO" in upper_label:
            values["expiry_date"] = parsed

    dates = sorted(dict.fromkeys(_extract_normalized_dates(normalized)))
    if dates:
        values.setdefault("birth_date", dates[0])
        if len(dates) >= 2:
            values.setdefault("expiry_date", dates[-1])
        if len(dates) >= 3:
            values.setdefault("issue_date", dates[-2])
    return values


def _extract_gender_from_text(text: str) -> str | None:
    normalized = _normalize_spaces(text.upper())
    match = re.search(r"SEXO\s*([MFX])\b", normalized)
    if match:
        return match.group(1)
    standalone = re.findall(r"\b([MF])\b", normalized)
    return standalone[0] if standalone else None


def extract_driver_license_chile_fields(prepared_pages: list[PreprocessedPage]) -> dict[str, str]:
    if not prepared_pages:
        return {}

    image = Image.open(BytesIO(prepared_pages[0].image_bytes)).convert("RGB")
    address_text = _ocr_crop(image, (0.46, 0.62, 0.90, 0.69), engine_name="rapidocr")
    category_text = _ocr_crop(image, (0.46, 0.48, 0.52, 0.55), engine_name="rapidocr")
    dates_text = _ocr_crop(image, (0.38, 0.32, 0.90, 0.60), engine_name="rapidocr")
    name_text = _ocr_crop(image, (0.30, 0.12, 0.88, 0.36), engine_name="rapidocr")
    authority_text = _ocr_crop(image, (0.06, 0.06, 0.42, 0.20), engine_name="rapidocr")
    category_match = re.search(r"\b([A-E])\b", category_text.upper())
    address = _cleanup_driver_address(address_text)

    if (not address or not category_match) and has_azure_document_intelligence_config():
        if not address:
            azure_combined = _ocr_crop(image, (0.44, 0.47, 0.90, 0.69), engine_name="azure-document-intelligence")
            address = _cleanup_driver_address(azure_combined) or address
        if not category_match:
            azure_category = _ocr_crop(image, (0.47, 0.40, 0.60, 0.52), engine_name="azure-document-intelligence")
            category_match = re.search(r"\b([A-E])\b", azure_category.upper())

    supplemental: dict[str, str] = {"nationality": "CHILE"}
    if address:
        supplemental["address"] = address
    if category_match:
        supplemental["categories"] = category_match.group(1)
    normalized_dates = _extract_normalized_dates(dates_text)
    if normalized_dates:
        supplemental.setdefault("birth_date", normalized_dates[0])
        if len(normalized_dates) >= 2:
            supplemental.setdefault("expiry_date", normalized_dates[-1])
        if len(normalized_dates) >= 3:
            supplemental.setdefault("issue_date", normalized_dates[-2])
    authority_match = re.search(r"\b(LA REINA|SANTIAGO|PROVIDENCIA|NUNOA|LAS CONDES)\b", authority_text.upper())
    if authority_match:
        supplemental["authority"] = authority_match.group(1)
    if name_text.strip() and "NOMBRES" in name_text.upper():
        names = re.sub(r"\s+", " ", name_text.upper())
        first_match = re.search(r"NOMBRES?\s+([A-Z ]{3,30})", names)
        last_match = re.search(r"APELLIDOS?\s+([A-Z ]{3,40})", names)
        if first_match:
            supplemental["first_name"] = _normalize_spaces(first_match.group(1))
        if last_match:
            supplemental["last_name"] = _normalize_spaces(last_match.group(1))
        if supplemental.get("first_name") or supplemental.get("last_name"):
            supplemental["holder_name"] = _normalize_spaces(" ".join(part for part in [supplemental.get("first_name"), supplemental.get("last_name")] if part))
    return supplemental


def extract_identity_chile_front_fields(prepared_pages: list[PreprocessedPage]) -> dict[str, str]:
    if not prepared_pages:
        return {}

    image = Image.open(BytesIO(prepared_pages[0].image_bytes)).convert("RGB")
    supplemental: dict[str, str] = {}

    names_text = _ocr_crop(image, (0.22, 0.20, 0.76, 0.50), engine_name="rapidocr")
    normalized_names = _normalize_spaces(names_text.upper())
    first_name_match = re.search(r"NOMBRES\s+([A-Z ]{3,30}?)\s+(?:SEXO|NACIONALIDAD|FECHA|NUMERO|RUN)\b", normalized_names)
    if first_name_match:
        expanded = _normalize_identity_compact_name(first_name_match.group(1))
        if expanded:
            supplemental["first_names"] = expanded
    surname_match = re.search(r"APELLIDOS\s+([A-Z ]{3,40})\s+NOMBRES", normalized_names)
    if surname_match:
        supplemental["last_names"] = _normalize_spaces(surname_match.group(1))
    if supplemental.get("first_names") or supplemental.get("last_names"):
        supplemental["holder_name"] = _normalize_spaces(" ".join(part for part in [supplemental.get("first_names"), supplemental.get("last_names")] if part))

    sex_text = _ocr_crop(image, (0.52, 0.26, 0.77, 0.49), engine_name="rapidocr")
    sex_value = _extract_gender_from_text(sex_text)
    if sex_value:
        supplemental["sex"] = sex_value

    document_number_text = _ocr_crop(image, (0.60, 0.34, 0.95, 0.60), engine_name="rapidocr")
    document_number = canonicalize_identity_document_number("CL", document_number_text)
    if document_number:
        supplemental["document_number"] = document_number

    run_text = _ocr_crop(image, (0.02, 0.72, 0.36, 0.95), engine_name="rapidocr")
    run_value = canonicalize_chile_run(run_text)
    if run_value:
        supplemental["run"] = run_value

    dates_text = _ocr_crop(image, (0.30, 0.42, 0.96, 0.74), engine_name="rapidocr")
    supplemental.update(_extract_identity_front_dates(dates_text))

    issuer_text = _ocr_crop(image, (0.23, 0.10, 0.80, 0.24), engine_name="rapidocr")
    if "REGISTRO CIVIL" in issuer_text.upper():
        supplemental["issuer"] = "REGISTRO CIVIL E IDENTIFICACION"

    if has_azure_document_intelligence_config():
        combined = _ocr_crop(image, (0.24, 0.30, 0.72, 0.56), engine_name="azure-document-intelligence")
        normalized = re.sub(r"\s+", " ", combined.upper())
        if not supplemental.get("first_names"):
            first_name_match = re.search(r"NOMBRES\s+([A-Z ]{3,30}?)\s+(?:SEXO|NACIONALIDAD|FECHA|NUMERO|RUN)\b", normalized)
            if first_name_match:
                expanded = _normalize_identity_compact_name(first_name_match.group(1))
                if expanded:
                    supplemental["first_names"] = expanded
        if not supplemental.get("last_names"):
            surname_match = re.search(r"APELLIDOS\s+([A-Z ]{3,40})\s+NOMBRES", normalized)
            if surname_match:
                supplemental["last_names"] = _normalize_spaces(surname_match.group(1))
        if not supplemental.get("holder_name") and (supplemental.get("first_names") or supplemental.get("last_names")):
            supplemental["holder_name"] = _normalize_spaces(" ".join(part for part in [supplemental.get("first_names"), supplemental.get("last_names")] if part))
        if not supplemental.get("sex"):
            sex_match = re.search(r"SEXO\s+([MFX])\b", normalized)
            sex_value = sex_match.group(1) if sex_match else None
            if sex_value:
                supplemental["sex"] = sex_value
        if "REGISTRO CIVIL" in normalized:
            supplemental.setdefault("issuer", "REGISTRO CIVIL E IDENTIFICACION")
        supplemental.update({key: value for key, value in _extract_identity_front_dates(normalized).items() if key not in supplemental})

    return supplemental


def extract_identity_chile_back_fields(prepared_pages: list[PreprocessedPage]) -> dict[str, str]:
    if not prepared_pages:
        return {}

    image = Image.open(BytesIO(prepared_pages[0].image_bytes)).convert("RGB")
    supplemental: dict[str, str] = {}
    mrz_text = _ocr_crop(image, (0.03, 0.70, 0.98, 0.98), engine_name="rapidocr")
    parsed = parse_identity_card_mrz(mrz_text)
    mrz_value = parsed.get("mrz")
    if isinstance(mrz_value, str) and mrz_value:
        supplemental["mrz"] = mrz_value
    for key in ("document_number", "run", "birth_date", "expiry_date", "sex", "first_names", "last_names", "holder_name"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            supplemental[key] = value

    birth_place_text = _ocr_crop(image, (0.22, 0.36, 0.80, 0.60), engine_name="rapidocr")
    normalized = _normalize_spaces(birth_place_text.upper())
    match = re.search(r"NACIO\s+EN[:\s]+([A-Z ]{4,30})", normalized)
    if match:
        supplemental["birth_place"] = _normalize_spaces(match.group(1))
    elif "NACIO EN" in normalized:
        parts = [part.strip() for part in normalized.split("NACIO EN", 1)[-1].split() if part.strip()]
        if parts:
            supplemental["birth_place"] = _normalize_spaces(" ".join(parts[:3]))

    return supplemental


def extract_identity_chile_fields(prepared_pages: list[PreprocessedPage], document_side: str | None = None, pack_id: str | None = None) -> dict[str, str]:
    if document_side == "back" or (pack_id and "back" in pack_id):
        return extract_identity_chile_back_fields(prepared_pages)
    return extract_identity_chile_front_fields(prepared_pages)


def extract_supplemental_fields(
    prepared_pages: list[PreprocessedPage],
    *,
    document_family: str,
    country: str,
    pack_id: str | None,
    document_side: str | None = None,
) -> dict[str, str]:
    if document_family == "identity" and country.upper() == "CL":
        return extract_identity_chile_fields(prepared_pages, document_side=document_side, pack_id=pack_id)
    if document_family == "driver_license" and country.upper() == "CL":
        return extract_driver_license_chile_fields(prepared_pages)
    return {}
