from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO
from random import Random
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


SyntheticFamily = Literal["identity", "passport", "driver_license", "certificate"]


FIRST_NAMES = [
    "SOFIA",
    "MATEO",
    "VALENTINA",
    "MARCELA",
    "JOAQUIN",
    "DANIELA",
    "JUAN",
    "CAMILA",
    "GERONIMO",
    "MARTIN",
]

LAST_NAMES = [
    "PEREZ",
    "GONZALEZ",
    "MARTINEZ",
    "RAMOS",
    "MATURANA",
    "FREDEZ",
    "LOPEZ",
    "VELEZ",
    "RUIZ",
    "VIDAL",
]

STREETS = [
    "AV LIBERTAD 123",
    "JR CENTRAL 456",
    "CL PRIMAVERA 789",
    "PSJ ANDES 18",
    "AV OCEANO 220",
]

AFP_ISSUERS = [
    "AFP PROVIDA S.A.",
    "AFP HABITAT S.A.",
    "AFP CUPRUM S.A.",
    "AFP MODELO S.A.",
]

EMPLOYERS = [
    "BACK OFFICE SOUTH AMERICA SPA",
    "CAJA LOS ANDES",
    "SERVICIOS CORPORATIVOS DEL PACIFICO SPA",
    "CONSULTORA DIGITAL ANDES LIMITADA",
    "TRANSPORTES CENTRAL SUR SPA",
]

COTIZATION_CODES = [
    "COTIZACION OBLIGATORIA",
    "APORTE VOLUNTARIO",
    "DEPOSITO CONVENIDO",
    "APV",
]

MONTH_ABBREVIATIONS = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

COMMON_CONDITIONS = ("clean", "low_light", "glare", "shadow", "tilt", "perspective", "blur", "jpeg")


@dataclass(frozen=True)
class SyntheticDocumentRecord:
    family: SyntheticFamily
    country: str
    pack_id: str
    variant: str
    filename_stem: str
    expected_fields: dict[str, str | None]
    capture_condition: str
    side: str | None = None
    split: str = "train"
    source_dataset: str = "synthetic-latam"
    benchmark_profile: str = "clean"
    expected_tables: dict[str, list[dict[str, str | None]]] | None = None


def _person_name(rng: Random) -> tuple[str, str, str]:
    first = rng.choice(FIRST_NAMES)
    middle = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    second_last = rng.choice(LAST_NAMES)
    full = f"{first} {middle} {last} {second_last}"
    return full, f"{first} {middle}", f"{last} {second_last}"


def _date_between(rng: Random, start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=rng.randint(0, max(delta_days, 1)))


def _format_iso(value: date) -> str:
    return value.isoformat()


def _document_number(country: str, rng: Random) -> str:
    if country == "CL":
        return f"{rng.choice('ABCDEFGHJK')}{rng.randint(10, 999)}.{rng.randint(100, 999)}.{rng.randint(100, 999)}"
    if country == "PE":
        return f"{rng.randint(10000000, 99999999)}"
    return f"{rng.randint(100000000, 999999999)}"


def _run_value(rng: Random) -> str:
    base = rng.randint(10000000, 25999999)
    digits = f"{base:,}".replace(",", ".")
    return f"{digits}-{rng.choice('0123456789K')}"


def _passport_number(rng: Random) -> str:
    return f"{rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{rng.randint(1000000, 9999999)}"


def _check_digit(value: str) -> str:
    weights = [7, 3, 1]
    alphabet = {str(index): index for index in range(10)}
    alphabet.update({chr(ord('A') + index): 10 + index for index in range(26)})
    alphabet['<'] = 0
    total = 0
    for index, char in enumerate(value):
        total += alphabet.get(char, 0) * weights[index % 3]
    return str(total % 10)


def _mrz_td3(surname: str, given_names: str, passport_number: str, country: str, birth_date: date, expiry_date: date, sex: str) -> str:
    normalized_surname = surname.replace(" ", "<")[:39]
    normalized_given = given_names.replace(" ", "<")[:39]
    line1 = f"P<{country}{normalized_surname}<<{normalized_given}".ljust(44, "<")[:44]
    passport_field = passport_number.ljust(9, "<")[:9]
    birth = birth_date.strftime("%y%m%d")
    expiry = expiry_date.strftime("%y%m%d")
    optional = "<" * 14
    optional_check = _check_digit(optional)
    composite = passport_field + _check_digit(passport_field) + country + birth + _check_digit(birth) + sex + expiry + _check_digit(expiry) + optional + optional_check
    line2 = (composite + _check_digit(composite)).ljust(44, "<")[:44]
    return f"{line1}\n{line2}"


def _driver_categories(rng: Random) -> str:
    categories = ["A-I", "A-II", "B", "C", "D"]
    return ", ".join(sorted(rng.sample(categories, k=rng.randint(1, 3))))


def _format_amount(value: int) -> str:
    return f"{value:,}"


def _period_label(value: date) -> str:
    return f"{MONTH_ABBREVIATIONS[value.month - 1]}-{value.year}"


def _issue_date_from_period(period: date) -> date:
    return period + timedelta(days=35)


def _certificate_number(rng: Random) -> str:
    return f"{rng.randint(10000000, 99999999):,}"


def _generate_certificate_rows(rng: Random, issuer: str) -> list[dict[str, str | None]]:
    base_period = date(2025, 8, 1)
    rows: list[dict[str, str | None]] = []
    for month_offset in range(12):
        period_date = date(base_period.year, base_period.month, 1) - timedelta(days=month_offset * 31)
        period_date = date(period_date.year, period_date.month, 1)
        renta_amount = rng.randint(850000, 3200000)
        pension_amount = max(0, int(renta_amount * rng.uniform(0.08, 0.14)))
        employer = rng.choice(EMPLOYERS)
        employer_rut = _run_value(rng)
        payment_date = _issue_date_from_period(period_date)
        code = rng.choice(COTIZATION_CODES)
        rows.append(
            {
                "period": f"{period_date.year}-{period_date.month:02d}",
                "period_label": _period_label(period_date),
                "renta_amount": _format_amount(renta_amount),
                "pension_amount": _format_amount(pension_amount),
                "cotization_code": code,
                "employer": employer,
                "employer_rut": employer_rut,
                "date": payment_date.isoformat(),
                "detail": f"{_period_label(period_date)} ${_format_amount(renta_amount)} ${_format_amount(pension_amount)} {employer} {employer_rut} {payment_date.isoformat()} {issuer}",
                "amount": _format_amount(pension_amount),
            }
        )
    return rows


def generate_synthetic_record(family: SyntheticFamily, country: str, index: int, condition: str | None = None, seed: int = 42) -> SyntheticDocumentRecord:
    rng = Random(seed + index + hash((family, country)))
    holder_name, given_names, surnames = _person_name(rng)
    birth_date = _date_between(rng, date(1965, 1, 1), date(2002, 12, 31))
    issue_date = _date_between(rng, date(2014, 1, 1), date(2023, 12, 31))
    expiry_date = _date_between(rng, date(2026, 1, 1), date(2036, 12, 31))
    condition_name = condition or COMMON_CONDITIONS[index % len(COMMON_CONDITIONS)]
    benchmark_profile = "clean" if condition_name == "clean" else "mobile-hard"
    split = "train" if index % 10 < 7 else "validation" if index % 10 < 9 else "test"
    expected_fields: dict[str, str | None]
    expected_tables: dict[str, list[dict[str, str | None]]] | None = None

    if family == "identity":
        expected_fields = {
            "holder_name": holder_name,
            "document_number": _document_number(country, rng),
            "birth_date": _format_iso(birth_date),
            "issue_date": _format_iso(issue_date),
            "expiry_date": _format_iso(expiry_date),
            "sex": rng.choice(["M", "F"]),
            "nationality": {"CL": "CHILENA", "PE": "PERUANA", "CO": "COLOMBIANA"}.get(country, country),
            "run": _run_value(rng) if country == "CL" else None,
            "address": rng.choice(STREETS),
        }
        pack_id = {
            "CL": "identity-cl-front",
            "PE": "identity-pe-front",
            "CO": "identity-co-front",
        }.get(country, "identity-generic")
        variant = {
            "CL": "identity-cl-front-text",
            "PE": "identity-pe-front-text",
            "CO": "identity-co-front-text",
        }.get(country, "identity-text")
        side = "front"
    elif family == "passport":
        passport_number = _passport_number(rng)
        sex = rng.choice(["M", "F"])
        expected_fields = {
            "holder_name": holder_name,
            "document_number": passport_number,
            "birth_date": _format_iso(birth_date),
            "expiry_date": _format_iso(expiry_date),
            "nationality": country,
            "mrz": _mrz_td3(surnames, given_names, passport_number, country, birth_date, expiry_date, sex),
            "sex": sex,
        }
        pack_id = "passport-generic"
        variant = "passport-text"
        side = "front"
    else:
        if family == "driver_license":
            expected_fields = {
                "holder_name": holder_name,
                "document_number": _document_number(country if country != "XX" else "CO", rng),
                "birth_date": _format_iso(birth_date),
                "issue_date": _format_iso(issue_date),
                "expiry_date": _format_iso(expiry_date),
                "categories": _driver_categories(rng),
                "address": rng.choice(STREETS),
            }
            pack_id = "driver-license-generic"
            variant = "driver-license-text"
            side = "front"
            expected_tables = None
        else:
            issuer = rng.choice(AFP_ISSUERS)
            account = f"1008-{rng.randint(1000, 9999)}-{rng.randint(1000000000, 9999999999)}"
            rows = _generate_certificate_rows(rng, issuer)
            certificate_number = _certificate_number(rng)
            issue_date = rows[0]["date"] or _format_iso(_date_between(rng, date(2025, 1, 1), date(2025, 12, 31)))
            expected_fields = {
                "holder_name": holder_name,
                "rut": _run_value(rng),
                "certificate_number": certificate_number,
                "issue_date": issue_date,
                "account": account,
                "issuer": issuer,
            }
            pack_id = "certificate-cl-previsional"
            variant = "certificate-cl-previsional-text"
            side = None
            expected_tables = {"movements": rows}

    return SyntheticDocumentRecord(
        family=family,
        country=country,
        pack_id=pack_id,
        variant=variant,
        filename_stem=f"synthetic-{family}-{country.lower()}-{index:05d}",
        expected_fields=expected_fields,
        capture_condition=condition_name,
        side=side,
        split=split,
        benchmark_profile=benchmark_profile,
        expected_tables=expected_tables,
    )


def _canvas_size(record: SyntheticDocumentRecord) -> tuple[int, int]:
    if record.family == "passport":
        return 1500, 1050
    if record.family == "driver_license":
        return 1500, 900
    if record.family == "certificate":
        return 1680, 1320
    return 1600, 980


def _background_color(record: SyntheticDocumentRecord) -> tuple[int, int, int]:
    if record.family == "passport":
        return 232, 239, 245
    if record.family == "driver_license":
        return 239, 246, 234
    if record.family == "certificate":
        return 245, 246, 242
    return 245, 243, 237


def _draw_field_block(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str | None, font, value_font) -> int:
    draw.text((x, y), label, fill=(48, 58, 70), font=font)
    draw.text((x, y + 28), value or "-", fill=(12, 18, 26), font=value_font)
    return y + 86


def _load_fonts() -> tuple[Any, Any, Any]:
    try:
        title = ImageFont.truetype("arial.ttf", 34)
        label = ImageFont.truetype("arial.ttf", 18)
        value = ImageFont.truetype("arial.ttf", 26)
        return title, label, value
    except Exception:  # noqa: BLE001
        default = ImageFont.load_default()
        return default, default, default


def render_synthetic_document(record: SyntheticDocumentRecord) -> Image.Image:
    width, height = _canvas_size(record)
    image = Image.new("RGB", (width, height), _background_color(record))
    draw = ImageDraw.Draw(image)
    title_font, label_font, value_font = _load_fonts()

    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=28, outline=(55, 82, 118), width=4, fill=(252, 252, 248))
    draw.text((56, 56), f"{record.family.upper()} {record.country}", fill=(24, 42, 68), font=title_font)
    draw.text((width - 360, 64), record.pack_id, fill=(76, 92, 116), font=label_font)

    y = 140
    left_x = 72
    right_x = width // 2 + 24

    if record.family == "identity":
        ordered_fields = [
            ("Nombre completo", record.expected_fields.get("holder_name")),
            ("Numero de documento", record.expected_fields.get("document_number")),
            ("RUN", record.expected_fields.get("run")),
            ("Fecha de nacimiento", record.expected_fields.get("birth_date")),
            ("Fecha de emision", record.expected_fields.get("issue_date")),
            ("Fecha de vencimiento", record.expected_fields.get("expiry_date")),
            ("Direccion", record.expected_fields.get("address")),
        ]
    elif record.family == "passport":
        ordered_fields = [
            ("Passport number", record.expected_fields.get("document_number")),
            ("Holder", record.expected_fields.get("holder_name")),
            ("Nationality", record.expected_fields.get("nationality")),
            ("Birth date", record.expected_fields.get("birth_date")),
            ("Expiry date", record.expected_fields.get("expiry_date")),
            ("MRZ", record.expected_fields.get("mrz")),
        ]
    elif record.family == "driver_license":
        ordered_fields = [
            ("Holder", record.expected_fields.get("holder_name")),
            ("License number", record.expected_fields.get("document_number")),
            ("Birth date", record.expected_fields.get("birth_date")),
            ("Issue date", record.expected_fields.get("issue_date")),
            ("Expiry date", record.expected_fields.get("expiry_date")),
            ("Categories", record.expected_fields.get("categories")),
            ("Address", record.expected_fields.get("address")),
        ]
    else:
        ordered_fields = [
            ("Emisor", record.expected_fields.get("issuer")),
            ("Titular", record.expected_fields.get("holder_name")),
            ("RUT", record.expected_fields.get("rut")),
            ("Numero de certificado", record.expected_fields.get("certificate_number")),
            ("Fecha de emision", record.expected_fields.get("issue_date")),
            ("Cuenta", record.expected_fields.get("account")),
        ]

    for index, (label, value) in enumerate(ordered_fields):
        column_x = left_x if index < (len(ordered_fields) + 1) // 2 else right_x
        column_y = y + (index if index < (len(ordered_fields) + 1) // 2 else index - ((len(ordered_fields) + 1) // 2)) * 90
        _draw_field_block(draw, column_x, column_y, label, value, label_font, value_font)

    if record.family == "passport":
        mrz = (record.expected_fields.get("mrz") or "").splitlines()
        mrz_box = (64, height - 220, width - 64, height - 70)
        draw.rounded_rectangle(mrz_box, radius=18, fill=(236, 240, 224), outline=(66, 80, 60), width=2)
        if mrz:
            draw.text((mrz_box[0] + 30, mrz_box[1] + 32), mrz[0], fill=(20, 20, 20), font=value_font)
            if len(mrz) > 1:
                draw.text((mrz_box[0] + 30, mrz_box[1] + 84), mrz[1], fill=(20, 20, 20), font=value_font)

    if record.family == "certificate":
        table_top = 620
        table_left = 64
        table_right = width - 64
        row_height = 48
        columns = [
            ("Periodo", 120),
            ("Renta", 180),
            ("Fondo", 160),
            ("Codigo", 220),
            ("Empleador", 340),
            ("RUT empleador", 170),
            ("Fecha pago", 160),
        ]
        draw.rounded_rectangle((table_left, table_top - 50, table_right, table_top + (row_height * 13)), radius=18, fill=(252, 252, 248), outline=(74, 92, 118), width=2)
        draw.text((table_left + 18, table_top - 40), "CERTIFICADO DE COTIZACIONES AFP", fill=(24, 42, 68), font=label_font)

        x = table_left + 12
        for label, width_value in columns:
            draw.text((x, table_top - 4), label, fill=(40, 56, 78), font=label_font)
            x += width_value

        movements = (record.expected_tables or {}).get("movements", [])[:12]
        for row_index, movement in enumerate(movements, start=1):
            y_offset = table_top + (row_index * row_height)
            if row_index % 2 == 0:
                draw.rectangle((table_left + 8, y_offset - 6, table_right - 8, y_offset + row_height - 14), fill=(244, 247, 250))
            values = [
                movement.get("period_label"),
                movement.get("renta_amount"),
                movement.get("pension_amount"),
                movement.get("cotization_code"),
                movement.get("employer"),
                movement.get("employer_rut"),
                movement.get("date"),
            ]
            x = table_left + 12
            for (column_label, width_value), value in zip(columns, values, strict=False):
                draw.text((x, y_offset), str(value or "-"), fill=(18, 24, 32), font=label_font)
                x += width_value

    return image


def apply_capture_condition(image: Image.Image, condition: str) -> Image.Image:
    conditioned = image.convert("RGB")
    if condition == "clean":
        return conditioned
    if condition == "low_light":
        conditioned = ImageEnhance.Brightness(conditioned).enhance(0.68)
        return ImageEnhance.Contrast(conditioned).enhance(0.9)
    if condition == "glare":
        glare = Image.new("RGBA", conditioned.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(glare)
        width, height = conditioned.size
        draw.ellipse((width * 0.45, height * 0.08, width * 0.95, height * 0.58), fill=(255, 255, 255, 120))
        draw.rectangle((width * 0.05, height * 0.75, width * 0.95, height * 0.95), fill=(255, 255, 255, 32))
        return Image.alpha_composite(conditioned.convert("RGBA"), glare).convert("RGB")
    if condition == "shadow":
        shadow = Image.new("RGBA", conditioned.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow)
        width, height = conditioned.size
        draw.polygon([(0, 0), (width * 0.55, 0), (width * 0.35, height), (0, height)], fill=(0, 0, 0, 72))
        return Image.alpha_composite(conditioned.convert("RGBA"), shadow).convert("RGB")
    if condition == "tilt":
        return conditioned.rotate(4, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(248, 248, 248))
    if condition == "perspective":
        width, height = conditioned.size
        quad = (
            width * 0.04,
            height * 0.08,
            width * 0.98,
            0,
            width * 0.92,
            height,
            0,
            height * 0.94,
        )
        return conditioned.transform((width, height), Image.Transform.QUAD, quad, resample=Image.Resampling.BICUBIC, fillcolor=(248, 248, 248))
    if condition == "blur":
        return conditioned.filter(ImageFilter.GaussianBlur(radius=1.6))
    if condition == "jpeg":
        buffer = BytesIO()
        conditioned.save(buffer, format="JPEG", quality=38, optimize=False)
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")
    return conditioned


def render_synthetic_document_bytes(record: SyntheticDocumentRecord) -> bytes:
    conditioned = apply_capture_condition(render_synthetic_document(record), record.capture_condition)
    output = BytesIO()
    conditioned.save(output, format="PNG")
    return output.getvalue()


def build_manifest_entry(record: SyntheticDocumentRecord, filename: str) -> dict[str, object]:
    payload = {
        "filename": filename,
        "family": record.family,
        "country": record.country,
        "pack_id": record.pack_id,
        "variant": record.variant,
        "side": record.side,
        "capture_condition": record.capture_condition,
        "condition_tags": [record.capture_condition, record.benchmark_profile],
        "split": record.split,
        "source_dataset": record.source_dataset,
        "benchmark_profile": record.benchmark_profile,
        "expected_fields": record.expected_fields,
    }
    if record.expected_tables:
        payload["expected_tables"] = record.expected_tables
    return payload
