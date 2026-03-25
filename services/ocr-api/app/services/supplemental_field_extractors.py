from __future__ import annotations

from io import BytesIO
import re

from PIL import Image, ImageEnhance, ImageOps

from app.engines.azure_document_intelligence import has_azure_document_intelligence_config
from app.engines.factory import get_visual_ocr_engine
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
            if token.isdigit()
            and len(token) <= 5
            and int(token) < 1900
            and index >= 2
            and all(tokens[index - offset].isalpha() for offset in (1, 2))
        ),
        None,
    )
    if number_index is not None:
        start_index = max(0, number_index - 2)
        address_tokens = tokens[start_index : number_index + 1]
        suffix_index = number_index + 1
        while suffix_index < len(tokens) and tokens[suffix_index] in {"CASA", "DEPTO", "DEPARTAMENTO", "OF", "J", "A", "B", "C"}:
            address_tokens.append(tokens[suffix_index])
            suffix_index += 1
        candidate = _normalize_spaces(" ".join(address_tokens))
        if len(address_tokens) < 3:
            return None
    else:
        return None
    if len(candidate) < 8:
        return None
    return candidate


def extract_driver_license_chile_fields(prepared_pages: list[PreprocessedPage]) -> dict[str, str]:
    if not prepared_pages:
        return {}

    image = Image.open(BytesIO(prepared_pages[0].image_bytes)).convert("RGB")
    address_text = _ocr_crop(image, (0.46, 0.62, 0.90, 0.69), engine_name="rapidocr")
    category_text = _ocr_crop(image, (0.46, 0.48, 0.52, 0.55), engine_name="rapidocr")
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
    return supplemental


def _normalize_identity_compact_name(token: str) -> str | None:
    compact = re.sub(r"[^A-Z]", "", token.upper())
    for given_name in sorted(COMMON_GIVEN_NAMES, key=len, reverse=True):
        if compact.startswith(given_name) and len(compact) > len(given_name) + 2:
            return _normalize_spaces(f"{given_name} {compact[len(given_name):]}")
    return _normalize_spaces(token) if token else None


def extract_identity_chile_fields(prepared_pages: list[PreprocessedPage]) -> dict[str, str]:
    if not prepared_pages or not has_azure_document_intelligence_config():
        return {}

    image = Image.open(BytesIO(prepared_pages[0].image_bytes)).convert("RGB")
    combined = _ocr_crop(image, (0.24, 0.30, 0.72, 0.56), engine_name="azure-document-intelligence")
    normalized = re.sub(r"\s+", " ", combined.upper())
    supplemental: dict[str, str] = {}

    first_name_match = re.search(r"NOMBRES\s+([A-Z ]{3,30}?)\s+(?:SEXO|NACIONALIDAD|FECHA|NUMERO|RUN)\b", normalized)
    if first_name_match:
        expanded = _normalize_identity_compact_name(first_name_match.group(1))
        if expanded:
            supplemental["first_names"] = expanded

    surname_match = re.search(r"APELLIDOS\s+([A-Z ]{3,40})\s+NOMBRES", normalized)
    if surname_match:
        supplemental["last_names"] = _normalize_spaces(surname_match.group(1))

    if supplemental.get("first_names") or supplemental.get("last_names"):
        supplemental["holder_name"] = _normalize_spaces(" ".join(part for part in [supplemental.get("first_names"), supplemental.get("last_names")] if part))

    sex_match = re.search(r"SEXO\s+([MFX])\b", normalized)
    if sex_match:
        supplemental["sex"] = sex_match.group(1)

    issuer_match = re.search(r"SERVICIO DE REGISTRO CIVIL E IDENTIFICACI[OÓ]N", normalized)
    if issuer_match:
        supplemental["issuer"] = "SERVICIO DE REGISTRO CIVIL E IDENTIFICACION"

    date_matches = re.findall(r"\b\d{2}\s*[A-Z]{3}\s*\d{4}\b", normalized)
    normalized_dates = []
    for candidate in date_matches:
        value = candidate.replace(" ", "")
        month_map = {"ENE": "01", "FEB": "02", "MAR": "03", "ABR": "04", "MAY": "05", "JUN": "06", "JUL": "07", "AGO": "08", "SEP": "09", "SET": "09", "OCT": "10", "NOV": "11", "DIC": "12"}
        match = re.match(r"(\d{2})([A-Z]{3})(\d{4})", value)
        if match and match.group(2) in month_map:
            normalized_dates.append(f"{match.group(3)}-{month_map[match.group(2)]}-{match.group(1)}")
    normalized_dates = sorted(dict.fromkeys(normalized_dates))
    if normalized_dates:
        supplemental.setdefault("birth_date", normalized_dates[0])
        if len(normalized_dates) >= 2:
            supplemental.setdefault("expiry_date", normalized_dates[-1])
        if len(normalized_dates) >= 3:
            supplemental.setdefault("issue_date", normalized_dates[-2])

    return supplemental


def extract_supplemental_fields(
    prepared_pages: list[PreprocessedPage],
    *,
    document_family: str,
    country: str,
    pack_id: str | None,
) -> dict[str, str]:
    if document_family == "identity" and country.upper() == "CL":
        return extract_identity_chile_fields(prepared_pages)
    if document_family == "driver_license" and country.upper() == "CL":
        return extract_driver_license_chile_fields(prepared_pages)
    return {}
