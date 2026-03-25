from __future__ import annotations

from collections.abc import Mapping
import re
import unicodedata


NUMERIC_SPACE_DATE_PATTERN = re.compile(r"\b(\d{2})\s+(\d{2})\s+(\d{4})\b")
PE_DNI_CANONICAL_PATTERN = re.compile(r"(?<!\d)(\d{8})(?!\d)")
CL_DOCUMENT_NUMBER_PATTERN = re.compile(r"\b[A-Z]{1,2}\d{1,3}\.\d{3}\.\d{3}\b", re.IGNORECASE)
CL_RUN_CAPTURE_PATTERN = re.compile(r"(?:RUN|RUT)?\s*(\d{1,2}[.,]?(?:\d{3})[.,]?(?:\d{3})\s*-\s*[\dkK])", re.IGNORECASE)
PASSPORT_NUMBER_PATTERN = re.compile(r"\b[A-Z]{1,2}\d{7,8}\b")
TD1_MRZ_LINE1_PATTERN = re.compile(r"^[IA1][<A-Z0-9][A-Z]{3}[A-Z0-9<]{20,}$")
TD1_MRZ_LINE2_PATTERN = re.compile(r"^\d{6}[0-9<][MFX<]\d{6}[0-9<][A-Z]{3}[A-Z0-9<]{10,}$")
TD1_MRZ_LINE3_PATTERN = re.compile(r"^[A-Z<]{5,}$")

MONTH_MAP = {
    "ENE": "01",
    "FEB": "02",
    "MAR": "03",
    "ABR": "04",
    "MAY": "05",
    "MAYO": "05",
    "JUN": "06",
    "JUL": "07",
    "AGO": "08",
    "SEP": "09",
    "SEPT": "09",
    "SEPTIEMBRE": "09",
    "SET": "09",
    "OCT": "10",
    "OCTUBRE": "10",
    "NOV": "11",
    "NOVIEMBRE": "11",
    "DIC": "12",
    "DICIEMBRE": "12",
    "ENERO": "01",
    "FEBRERO": "02",
    "MARZO": "03",
    "ABRIL": "04",
    "JUNIO": "06",
    "JULIO": "07",
    "AGOSTO": "08",
  }

PLACEHOLDER_NAME_KEYS = {
    "nombre-por-confirmar",
    "no-detectado",
    "no-detectada",
    "documento-de-identidad",
    "cedula-de-identidad",
    "cedula-de",
    "documento-nacional-de-identidad",
}
MISSING_TEXT_VALUES = {"", "-", "NO DETECTADO", "NO DETECTADA", "NO DETECTADOS", "NO DETECTADAS", "PENDING"}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def slugify(value: str) -> str:
    ascii_value = strip_accents(value)
    return "-".join(part for part in "".join(char.lower() if char.isalnum() else "-" for char in ascii_value).split("-") if part)


def compact(value: str | None) -> str:
    return "".join(char.lower() for char in strip_accents(value or "") if char.isalnum())


def clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" :-")
    return cleaned or None


def find_value_by_key_fragments(values: Mapping[str, str], *fragment_groups: tuple[str, ...]) -> str | None:
    compact_items = [(compact(key), clean_value(value)) for key, value in values.items()]
    for fragments in fragment_groups:
        normalized_fragments = tuple(compact(fragment) for fragment in fragments if fragment)
        for key_compact, value in compact_items:
            if not value:
                continue
            if all(fragment in key_compact for fragment in normalized_fragments):
                return value
    return None


def is_placeholder_name(value: str | None) -> bool:
    candidate = slugify(value or "")
    return (
        not candidate
        or candidate in PLACEHOLDER_NAME_KEYS
        or candidate.startswith("no-detect")
        or candidate.startswith("cedula-de")
        or candidate.startswith("documento-de")
    )


def derive_identity_holder_name(values: Mapping[str, str], preferred: str | None = None) -> str | None:
    if preferred and not is_placeholder_name(preferred):
        return preferred

    direct = clean_value(values.get("nombre-completo") or values.get("titular"))
    if not direct:
        direct = clean_value(values.get("nombres-y-apellidos"))
    if not direct:
        direct = find_value_by_key_fragments(values, ("nombre", "completo"), ("nombres", "apellidos"), ("holder", "name"), ("titular",))
    if direct and not is_placeholder_name(direct):
        return direct

    first_names = clean_value(values.get("nombres") or values.get("nombre") or values.get("first-names") or values.get("given-name"))
    if not first_names:
        first_names = find_value_by_key_fragments(values, ("nombres",), ("nombre",), ("given", "name"))
    last_names = clean_value(values.get("apellidos") or values.get("apellido") or values.get("last-names") or values.get("surname"))
    if not last_names:
        last_names = find_value_by_key_fragments(values, ("apellidos",), ("apellido",), ("surname",), ("last", "name"))

    if first_names and last_names:
        return clean_value(f"{first_names} {last_names}")
    if direct:
        return direct
    if preferred:
        return preferred
    return first_names or last_names


def canonicalize_identity_document_number(country: str, value: str | None) -> str | None:
    cleaned = clean_value(value)
    if not cleaned:
        return None
    if cleaned.upper() in MISSING_TEXT_VALUES:
        return None

    normalized_country = (country or "").upper()
    ascii_value = strip_accents(cleaned)

    if normalized_country == "PE":
        match = PE_DNI_CANONICAL_PATTERN.search(ascii_value)
        if match:
            return match.group(1)
        compact_digits = re.sub(r"\D", "", ascii_value)
        if len(compact_digits) == 8:
            return compact_digits

    if normalized_country == "CO":
        compact_digits = re.sub(r"\D", "", ascii_value)
        if 6 <= len(compact_digits) <= 10:
            return compact_digits

    if normalized_country == "CL":
        match = CL_DOCUMENT_NUMBER_PATTERN.search(ascii_value)
        if match:
            return match.group(0).upper()
        compact_candidate = re.sub(r"[^A-Z0-9]", "", ascii_value).upper()
        if re.fullmatch(r"[A-Z]\d{8}", compact_candidate):
            return f"{compact_candidate[:3]}.{compact_candidate[3:6]}.{compact_candidate[6:]}"
        if re.fullmatch(r"[A-Z]{2}\d{7}", compact_candidate):
            return f"{compact_candidate[:4]}.{compact_candidate[4:7]}.{compact_candidate[7:]}"

    return cleaned


def normalize_date_value(value: str | None) -> str | None:
    cleaned = clean_value(value)
    if not cleaned:
        return None

    ascii_value = strip_accents(cleaned.upper())
    if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", ascii_value):
        return ascii_value.replace("/", "-")

    if re.fullmatch(r"\d{2}[-/]\d{2}[-/]\d{4}", ascii_value):
        day, month, year = re.split(r"[-/]", ascii_value)
        return f"{year}-{month}-{day}"

    spaced_numeric = NUMERIC_SPACE_DATE_PATTERN.search(ascii_value)
    if spaced_numeric:
        day, month, year = spaced_numeric.groups()
        return f"{year}-{month}-{day}"

    compact_date = re.sub(r"\s+", "", ascii_value)
    textual_match = re.fullmatch(r"(\d{2})([A-Z]{3,5})(\d{4})", compact_date)
    if textual_match:
        day, month, year = textual_match.groups()
        mapped_month = MONTH_MAP.get(month)
        if mapped_month:
            return f"{year}-{mapped_month}-{day}"

    long_textual_match = re.search(r"(\d{1,2})\s+DE\s+([A-Z]{3,12})\s+DE\s+(\d{4})", ascii_value)
    if long_textual_match:
        day, month, year = long_textual_match.groups()
        mapped_month = MONTH_MAP.get(month)
        if mapped_month:
            return f"{year}-{mapped_month}-{day.zfill(2)}"

    return cleaned


def canonicalize_chile_run(value: str | None) -> str | None:
    cleaned = clean_value(value)
    if not cleaned or cleaned.upper() in MISSING_TEXT_VALUES:
        return None
    match = CL_RUN_CAPTURE_PATTERN.search(strip_accents(cleaned))
    if not match:
        return cleaned
    normalized = re.sub(r"\s+", "", match.group(1)).upper().replace(",", ".")
    if "-" not in normalized:
        return normalized

    digits, verifier = normalized.split("-", 1)
    clean_digits = re.sub(r"\D", "", digits)
    if not clean_digits:
        return normalized

    groups: list[str] = []
    while len(clean_digits) > 3:
        groups.append(clean_digits[-3:])
        clean_digits = clean_digits[:-3]
    groups.append(clean_digits)
    formatted_digits = ".".join(reversed(groups))
    return f"{formatted_digits}-{verifier}"


def validate_chile_run_checksum(value: str | None) -> bool:
    normalized = canonicalize_chile_run(value)
    if not normalized or "-" not in normalized:
        return False
    digits, verifier = normalized.split("-", 1)
    clean_digits = re.sub(r"\D", "", digits)
    if not clean_digits or not verifier:
        return False
    factors = [2, 3, 4, 5, 6, 7]
    total = 0
    for index, digit in enumerate(reversed(clean_digits)):
        total += int(digit) * factors[index % len(factors)]
    remainder = 11 - (total % 11)
    expected = "0" if remainder == 11 else "K" if remainder == 10 else str(remainder)
    return verifier.upper() == expected


def canonicalize_passport_number(value: str | None) -> str | None:
    cleaned = clean_value(value)
    if not cleaned or cleaned.upper() in MISSING_TEXT_VALUES:
        return None
    match = PASSPORT_NUMBER_PATTERN.search(strip_accents(cleaned).upper())
    if not match:
        return cleaned.upper()
    return match.group(0).upper()


def mrz_char_value(char: str) -> int:
    if char.isdigit():
        return int(char)
    if char == "<":
        return 0
    return ord(char.upper()) - 55 if char.isalpha() else 0


def mrz_check_digit(value: str) -> str:
    weights = [7, 3, 1]
    total = sum(mrz_char_value(char) * weights[index % len(weights)] for index, char in enumerate(value))
    return str(total % 10)


def validate_mrz_check_digits(mrz_text: str | None) -> bool:
    parsed = parse_passport_mrz(mrz_text or "")
    mrz = parsed.get("mrz")
    if not mrz:
        return False
    lines = mrz.splitlines()
    if len(lines) < 2:
        return False
    line2 = lines[1].ljust(44, "<")[:44]
    document_number = line2[0:9]
    document_digit = line2[9]
    birth = line2[13:19]
    birth_digit = line2[19]
    expiry = line2[21:27]
    expiry_digit = line2[27]
    optional = line2[28:42]
    optional_digit = line2[42]
    final_digit = line2[43]
    composite = document_number + document_digit + line2[10:13] + birth + birth_digit + line2[20] + expiry + expiry_digit + optional + optional_digit
    return (
        mrz_check_digit(document_number) == document_digit
        and mrz_check_digit(birth) == birth_digit
        and mrz_check_digit(expiry) == expiry_digit
        and mrz_check_digit(optional) == optional_digit
        and mrz_check_digit(composite) == final_digit
    )


def _normalize_td1_line(line: str) -> str:
    compact_line = re.sub(r"\s+", "", strip_accents(line).upper())
    compact_line = compact_line.replace("«", "<")
    compact_line = compact_line.replace("K<", "<<") if compact_line.count("<") == 0 and "<" in compact_line else compact_line
    if len(compact_line) >= 5 and compact_line[0] in {"I", "1", "A"} and compact_line[1] != "<" and compact_line[2:5].isalpha():
        compact_line = f"{('I' if compact_line[0] == '1' else compact_line[0])}<{compact_line[2:]}"
    return compact_line


def extract_identity_card_mrz_lines(text: str) -> list[str]:
    normalized_lines = [_normalize_td1_line(raw_line) for raw_line in text.splitlines()]
    candidates = [line for line in normalized_lines if len(line) >= 24]

    for index in range(max(0, len(candidates) - 2)):
        line1, line2, line3 = candidates[index : index + 3]
        if not TD1_MRZ_LINE1_PATTERN.match(line1):
            continue
        if not TD1_MRZ_LINE2_PATTERN.match(line2):
            continue
        if not TD1_MRZ_LINE3_PATTERN.match(line3):
            continue
        return [line1.ljust(30, "<")[:30], line2.ljust(30, "<")[:30], line3.ljust(30, "<")[:30]]

    compact_text = _normalize_td1_line(text)
    line1_match = re.search(r"[IA1][<A-Z0-9][A-Z]{3}[A-Z0-9<]{25}", compact_text)
    line2_match = re.search(r"\d{6}[0-9<][MFX<]\d{6}[0-9<][A-Z]{3}[A-Z0-9<]{11}", compact_text)
    line3_match = re.search(r"[A-Z<]{5,}<<[A-Z<]{5,}", compact_text)
    if line1_match and line2_match and line3_match:
        return [
            _normalize_td1_line(line1_match.group(0)).ljust(30, "<")[:30],
            line2_match.group(0).ljust(30, "<")[:30],
            line3_match.group(0).ljust(30, "<")[:30],
        ]

    return []


def parse_identity_card_mrz(text: str) -> dict[str, str | None]:
    lines = extract_identity_card_mrz_lines(text)
    if len(lines) < 3:
        return {
            "mrz": None,
            "holder_name": None,
            "first_names": None,
            "last_names": None,
            "document_number": None,
            "birth_date": None,
            "expiry_date": None,
            "nationality": None,
            "sex": None,
            "run": None,
            "issuing_country": None,
        }

    line1, line2, line3 = lines[:3]
    issuing_country = clean_value(line1[2:5].replace("<", ""))
    normalized_country = {"CHL": "CL", "PER": "PE", "COL": "CO"}.get((issuing_country or "").upper(), issuing_country)
    document_number = canonicalize_identity_document_number(normalized_country or "", line1[5:14].replace("<", ""))

    def extract_td1_chile_run(optional_data: str) -> str | None:
        compact = re.sub(r"[^0-9K<]", "", optional_data.upper())
        condensed = compact.replace("<", "")
        for start in range(max(0, len(condensed) - 9)):
            for digits_length in (8, 7):
                end = start + digits_length
                if end >= len(condensed):
                    continue
                candidate = canonicalize_chile_run(f"{condensed[start:end]}-{condensed[end]}")
                if validate_chile_run_checksum(candidate):
                    return candidate
        match = re.search(r"(\d{7,8})<([\dK<])", compact)
        raw_value = f"{match.group(1)}-{match.group(2)}" if match and match.group(2) != "<" else None
        return canonicalize_chile_run(raw_value)

    def normalize_mrz_date(value: str) -> str | None:
        if not re.fullmatch(r"\d{6}", value):
            return None
        year = int(value[:2])
        century = 1900 if year >= 40 else 2000
        return f"{century + year:04d}-{value[2:4]}-{value[4:6]}"

    if normalized_country == "CL" and line3.count("<") < 2 and "K" in line3:
        line3 = line3.replace("K<", "<<").replace("K", "<")

    surname, given_names = (line3.split("<<", 1) + [""])[:2]
    last_names = clean_value(surname.replace("<", " "))
    first_names = clean_value(given_names.replace("<", " "))
    holder_name = clean_value(" ".join(part for part in [first_names, last_names] if part))

    optional_data = line2[18:30]
    raw_run = extract_td1_chile_run(optional_data) if normalized_country == "CL" else None

    return {
        "mrz": "\n".join(lines[:3]),
        "holder_name": holder_name,
        "first_names": first_names,
        "last_names": last_names,
        "document_number": document_number,
        "birth_date": normalize_mrz_date(line2[0:6]),
        "expiry_date": normalize_mrz_date(line2[8:14]),
        "nationality": clean_value(line2[15:18].replace("<", "")),
        "sex": clean_value(line2[7].replace("<", "")),
        "run": raw_run,
        "issuing_country": normalized_country,
    }


def parse_identity_card_td1_fallback(text: str) -> dict[str, str | None]:
    compact_text = _normalize_td1_line(text)

    def normalize_mrz_date(value: str | None) -> str | None:
        if not value or not re.fullmatch(r"\d{6}", value):
            return None
        year = int(value[:2])
        century = 1900 if year >= 40 else 2000
        return f"{century + year:04d}-{value[2:4]}-{value[4:6]}"

    line1_match = re.search(r"(?:I<|IN)CHL([A-Z0-9<]{9})", compact_text)
    line2_match = re.search(r"(\d{6})[0-9<][MFX<](\d{6})[0-9<]CHL", compact_text)
    run_match = re.search(r"CHL(\d{7,8})<([\dK])", compact_text)
    name_line = next(
        (
            _normalize_td1_line(line)
            for line in text.splitlines()
            if "<<" in line and sum(char.isalpha() for char in line) >= 6 and len(line.strip()) >= 12
        ),
        None,
    )
    first_names = None
    last_names = None
    holder_name = None
    if name_line:
        surname, given_names = (name_line.split("<<", 1) + [""])[:2]
        last_names = clean_value(surname.replace("<", " "))
        first_names = clean_value(given_names.replace("<", " "))
        holder_name = clean_value(" ".join(part for part in [first_names, last_names] if part))

    birth_place = None
    raw_lines: list[str] = [clean_value(strip_accents(line).upper()) or "" for line in text.splitlines() if clean_value(line)]
    for index, line in enumerate(raw_lines):
        normalized_line = re.sub(r"[^A-Z ]", "", line)
        if "NACIO EN" not in normalized_line:
            continue
        candidate_indices = [index - 1, index + 1, index - 2, index + 2, index - 3, index + 3]
        for candidate_index in candidate_indices:
            if candidate_index < 0 or candidate_index >= len(raw_lines):
                continue
            candidate = raw_lines[candidate_index]
            if any(char.isdigit() for char in candidate):
                continue
            if any(marker in candidate for marker in ("NACIO", "NACICAN", "CHL", "INCHL")):
                continue
            if len(candidate) > 32:
                continue
            birth_place = candidate
            break
        if birth_place:
            break

    document_number = canonicalize_identity_document_number("CL", line1_match.group(1)) if line1_match else None
    raw_run = f"{run_match.group(1)}-{run_match.group(2)}" if run_match else None
    return {
        "document_number": document_number,
        "run": canonicalize_chile_run(raw_run),
        "birth_date": normalize_mrz_date(line2_match.group(1) if line2_match else None),
        "expiry_date": normalize_mrz_date(line2_match.group(2) if line2_match else None),
        "sex": line2_match.group(0)[7] if line2_match else None,
        "holder_name": holder_name,
        "first_names": first_names,
        "last_names": last_names,
        "birth_place": birth_place,
        "mrz": name_line,
    }


def extract_mrz_lines(text: str) -> list[str]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        compact_line = re.sub(r"\s+", "", strip_accents(raw_line).upper())
        if compact_line.count("<") >= 2 and len(compact_line) >= 24:
            candidates.append(compact_line)

    compact_text = re.sub(r"\s+", "", strip_accents(text).upper())
    if not candidates or any(len(candidate) > 60 for candidate in candidates):
        line1_matches = re.findall(r"P[<A-Z][A-Z]{3}[A-Z<]{5,}<<[A-Z<]{5,}", compact_text)
        line2_matches = re.findall(r"[A-Z0-9<]{9}[0-9<][A-Z]{3}[0-9<]{6}[0-9<][MFX<][0-9<]{6}[0-9<][A-Z0-9<]{14}[0-9<]", compact_text)
        best_line1 = max(line1_matches, key=lambda candidate: (candidate.count("<"), len(candidate)), default=None)
        best_line2 = max(line2_matches, key=lambda candidate: (candidate.count("<"), len(candidate)), default=None)
        synthetic_candidates = [candidate for candidate in [best_line1, best_line2] if candidate]
        if synthetic_candidates:
            candidates = synthetic_candidates

    if not candidates:
        return []

    line1 = next((candidate for candidate in candidates if candidate.startswith("P<")), None)
    if line1:
        remaining = [candidate for candidate in candidates if candidate != line1]
        line2 = next((candidate for candidate in remaining if sum(char.isdigit() for char in candidate) >= 8 and candidate.count("<") >= 2), None)
        return [line for line in [line1, line2] if line]

    ranked = sorted(candidates, key=lambda candidate: (candidate.count("<"), len(candidate)), reverse=True)
    return ranked[:2]


def parse_passport_mrz(text: str) -> dict[str, str | None]:
    lines = extract_mrz_lines(text)
    if not lines:
        return {
            "mrz": None,
            "holder_name": None,
            "document_number": None,
            "birth_date": None,
            "expiry_date": None,
            "nationality": None,
        }

    line1 = lines[0]
    if line1.startswith("PP") and len(line1) >= 5:
        line1 = f"P<{line1[2:]}"
    elif line1.startswith("P") and len(line1) >= 4 and line1[1] != "<":
        line1 = f"P<{line1[1:]}"
    line1 = line1.ljust(44, "<")[:44]
    names = line1[5:].split("<<", 1)
    surname = names[0].replace("<", " ").strip()
    given_names = names[1].replace("<", " ").strip() if len(names) > 1 else ""
    holder_name = clean_value(f"{given_names} {surname}")
    line2 = lines[1].ljust(44, "<")[:44] if len(lines) > 1 else None
    document_number = clean_value(line2[:9].replace("<", "")) if line2 else None
    nationality = clean_value(line2[10:13].replace("<", "")) if line2 else None
    birth_raw = line2[13:19] if line2 else None
    expiry_raw = line2[21:27] if line2 else None

    def normalize_mrz_date(value: str) -> str | None:
        if not re.fullmatch(r"\d{6}", value):
            return None
        year = int(value[:2])
        century = 1900 if year >= 40 else 2000
        return f"{century + year:04d}-{value[2:4]}-{value[4:6]}"

    return {
        "mrz": f"{line1}\n{line2}" if line2 else line1,
        "holder_name": holder_name,
        "document_number": canonicalize_passport_number(document_number),
        "birth_date": normalize_mrz_date(birth_raw or ""),
        "expiry_date": normalize_mrz_date(expiry_raw or ""),
        "nationality": nationality,
    }
