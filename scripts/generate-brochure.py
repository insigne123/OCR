from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "marketing" / "ocr-master-brochure.pdf"

A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842
CANVAS_WIDTH = 2480
CANVAS_HEIGHT = 3508

BG = "#f4f8fb"
BG_SOFT = "#eaf2f7"
TEXT = "#0d2238"
MUTED = "#5e7185"
LINE = "#d8e5ef"
NAVY = "#0b1f33"
NAVY_DEEP = "#081827"
BLUE = "#0f6cbd"
CYAN = "#1aa2c9"
TEAL = "#0c7c86"
WHITE = "#ffffff"
SOFT_BLUE = "#edf5ff"
SOFT_CYAN = "#e8f7fb"
SOFT_TEAL = "#e8f6f2"


def hex_color(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return red, green, blue, alpha


def font_candidates(*names: str) -> list[str]:
    windows_fonts = Path("C:/Windows/Fonts")
    candidates = [str(windows_fonts / name) for name in names]
    candidates.extend(names)
    return candidates


def load_font(size: int, role: str = "body", weight: str = "regular") -> Any:
    families: dict[tuple[str, str], list[str]] = {
        ("display", "bold"): font_candidates("bahnschrift.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"),
        ("display", "regular"): font_candidates("bahnschrift.ttf", "arial.ttf", "DejaVuSans.ttf"),
        ("body", "bold"): font_candidates("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"),
        ("body", "regular"): font_candidates("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"),
        ("body", "light"): font_candidates("segoeuil.ttf", "arial.ttf", "DejaVuSans.ttf"),
    }
    for candidate in families.get((role, weight), []):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_box(draw: Any, text: str, font: Any) -> tuple[int, int, int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return int(left), int(top), int(right), int(bottom)


def text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    left, top, right, bottom = text_box(draw, text, font)
    return right - left, bottom - top


def wrap_text(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_paragraph(
    draw: Any,
    xy: tuple[int, int],
    text: str,
    font: Any,
    fill: tuple[int, int, int, int],
    max_width: int,
    line_gap: int,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += text_size(draw, line, font)[1] + line_gap
    return y


def add_blur_blob(
    image: Image.Image,
    bounds: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    blur: int,
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.ellipse(bounds, fill=fill)
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def add_shadow(
    image: Image.Image,
    rect: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    offset: tuple[int, int] = (0, 22),
    blur: int = 28,
) -> None:
    x0, y0, x1, y1 = rect
    width = x1 - x0
    height = y1 - y0
    ox, oy = offset
    pad = blur + max(abs(ox), abs(oy)) + 12
    shadow = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (pad + ox, pad + oy, pad + ox + width, pad + oy + height),
        radius=radius,
        fill=fill,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    image.alpha_composite(shadow, (x0 - pad, y0 - pad))


def draw_chip(
    draw: Any,
    rect: tuple[int, int, int, int],
    text: str,
    font: Any,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    text_fill: tuple[int, int, int, int],
) -> None:
    draw.rounded_rectangle(rect, radius=(rect[3] - rect[1]) // 2, fill=fill, outline=outline, width=2)
    width, height = text_size(draw, text, font)
    x0, y0, x1, y1 = rect
    draw.text((x0 + ((x1 - x0 - width) / 2), y0 + ((y1 - y0 - height) / 2) - 2), text, font=font, fill=text_fill)


def build_brand_block(size: tuple[int, int], logo_path: Path | None) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=32, fill=hex_color(WHITE, 220), outline=hex_color(LINE, 255), width=2)

    display_small = load_font(46, role="display", weight="bold")
    body = load_font(26, role="body", weight="regular")
    body_bold = load_font(28, role="body", weight="bold")

    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        max_w = 150
        max_h = 72
        logo.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        logo_x = 28
        logo_y = (size[1] - logo.height) // 2
        panel.alpha_composite(logo, (logo_x, logo_y))
        text_x = 204
    else:
        draw.rounded_rectangle((28, 18, 42, size[1] - 18), radius=7, fill=hex_color(CYAN, 255))
        draw.text((74, 28), "YAGO SPA", font=display_small, fill=hex_color(NAVY, 255))
        draw.text((74, 74), "Solucion comercial", font=body, fill=hex_color(MUTED, 255))
        return panel

    draw.text((text_x, 26), "YAGO SPA", font=display_small, fill=hex_color(NAVY, 255))
    draw.text((text_x, 72), "Solucion comercial", font=body_bold, fill=hex_color(MUTED, 255))
    return panel


def build_api_panel(size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, hex_color(NAVY, 255))
    draw = ImageDraw.Draw(panel)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=42, fill=255)

    for x in range(80, size[0], 92):
        draw.line((x, 0, x, size[1]), fill=hex_color("#22425f", 34), width=1)
    for y in range(70, size[1], 92):
        draw.line((0, y, size[0], y), fill=hex_color("#22425f", 34), width=1)

    add_blur_blob(panel, (size[0] - 420, -120, size[0] + 90, 260), hex_color(CYAN, 62), 42)
    add_blur_blob(panel, (size[0] - 360, size[1] - 260, size[0] + 120, size[1] + 160), hex_color(BLUE, 46), 50)

    label_font = load_font(24, role="body", weight="bold")
    title_font = load_font(38, role="display", weight="bold")
    code_font = load_font(30, role="body", weight="bold")
    row_label = load_font(22, role="body", weight="bold")
    row_value = load_font(28, role="body", weight="bold")
    row_note = load_font(25, role="body", weight="regular")

    draw_chip(
        draw,
        (48, 48, 282, 102),
        "API FLOW",
        label_font,
        hex_color("#0d314e", 230),
        hex_color("#356f9d", 200),
        hex_color("#d8f5ff", 255),
    )
    draw.text((48, 148), "OCR listo para integrar", font=title_font, fill=hex_color(WHITE, 255))
    draw_paragraph(
        draw,
        (48, 208),
        "Uso principal mediante API para sistemas, portales y automatizacion documental.",
        row_note,
        hex_color("#bdd0e1", 255),
        size[0] - 96,
        6,
    )

    call_rect = (48, 300, size[0] - 48, 382)
    draw.rounded_rectangle(call_rect, radius=26, fill=hex_color(WHITE, 28), outline=hex_color("#4d7597", 160), width=2)
    draw.text((76, 327), "POST /v1/process", font=code_font, fill=hex_color(NAVY, 255))

    rows = [
        ("AUTH", "x-api-key"),
        ("INPUT", "PDF | JPG | PNG | HEIC"),
        ("OUTPUT", "JSON estructurado"),
    ]

    y = 406
    for label, value in rows:
        row_rect = (48, y, size[0] - 48, y + 74)
        draw.rounded_rectangle(row_rect, radius=24, fill=hex_color(WHITE, 18), outline=hex_color("#365778", 155), width=2)
        draw.text((76, y + 23), label, font=row_label, fill=hex_color("#8fb4d3", 255))
        draw.text((238, y + 18), value, font=row_value, fill=hex_color(NAVY, 255))
        y += 86

    footer_rect = (48, size[1] - 96, size[0] - 48, size[1] - 38)
    draw.rounded_rectangle(footer_rect, radius=24, fill=hex_color("#071523", 170), outline=hex_color("#2c4e6f", 160), width=2)
    draw.text((76, size[1] - 77), "Integracion B2B, salida JSON, consumo escalable.", font=row_note, fill=hex_color("#e5f5ff", 255))

    panel.putalpha(mask)
    return panel


def build_benefit_card(size: tuple[int, int], title: str, body: str, accent: str) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=34, fill=hex_color(WHITE, 234), outline=hex_color(LINE, 255), width=2)
    draw.rounded_rectangle((22, 22, 74, 74), radius=16, fill=hex_color(accent, 255))

    title_font = load_font(38, role="display", weight="bold")
    body_font = load_font(27, role="body", weight="regular")

    draw.text((104, 30), title, font=title_font, fill=hex_color(NAVY, 255))
    draw_paragraph(draw, (104, 88), body, body_font, hex_color(MUTED, 255), size[0] - 144, 8)
    return panel


def build_price_box(size: tuple[int, int], title: str, price: str, note: str, accent: str) -> Image.Image:
    box = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(box)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=26, fill=hex_color(WHITE, 196), outline=hex_color(LINE, 255), width=2)

    label_font = load_font(22, role="body", weight="bold")
    price_font = load_font(48, role="display", weight="bold")
    note_font = load_font(24, role="body", weight="regular")

    draw.text((28, 22), title.upper(), font=label_font, fill=hex_color(accent, 255))
    draw.text((28, 64), price, font=price_font, fill=hex_color(NAVY, 255))
    draw_paragraph(draw, (28, 132), note, note_font, hex_color(MUTED, 255), size[0] - 56, 6)
    return box


def build_plan_card(
    size: tuple[int, int],
    title: str,
    volume: str,
    description: str,
    annual_price: str,
    annual_note: str,
    monthly_price: str,
    monthly_note: str,
    footer_note: str,
    accent: str,
    tint: str,
) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=42, fill=hex_color(tint, 250), outline=hex_color(LINE, 255), width=2)
    draw.rounded_rectangle((0, 0, size[0] - 1, 16), radius=42, fill=hex_color(accent, 255))
    draw.rounded_rectangle((36, 44, 176, 96), radius=22, fill=hex_color(accent, 34), outline=hex_color(accent, 70), width=2)

    label_font = load_font(24, role="body", weight="bold")
    title_font = load_font(56, role="display", weight="bold")
    volume_font = load_font(58, role="display", weight="bold")
    suffix_font = load_font(27, role="body", weight="regular")
    body_font = load_font(28, role="body", weight="regular")
    footer_font = load_font(27, role="body", weight="bold")
    micro_font = load_font(23, role="body", weight="regular")

    draw.text((70, 57), "PLAN", font=label_font, fill=hex_color(accent, 255))
    draw.text((70, 132), title, font=title_font, fill=hex_color(NAVY, 255))
    draw.text((70, 240), volume, font=volume_font, fill=hex_color(NAVY, 255))
    draw.text((70, 320), "documentos / mes", font=suffix_font, fill=hex_color(MUTED, 255))
    body_end = draw_paragraph(draw, (70, 390), description, body_font, hex_color(MUTED, 255), size[0] - 140, 8)

    box_w = (size[0] - 70 * 2 - 22) // 2
    price_y = body_end + 42
    annual_box = build_price_box((box_w, 226), "Pago anual", annual_price, annual_note, accent)
    monthly_box = build_price_box((box_w, 226), "Pago mensual", monthly_price, monthly_note, accent)
    panel.alpha_composite(annual_box, (70, price_y))
    panel.alpha_composite(monthly_box, (70 + box_w + 22, price_y))

    note_rect = (70, price_y + 294, size[0] - 70, price_y + 408)
    draw.rounded_rectangle(note_rect, radius=28, fill=hex_color(accent, 28), outline=hex_color(accent, 64), width=2)
    draw_paragraph(draw, (98, price_y + 328), footer_note, footer_font, hex_color(NAVY, 255), size[0] - 196, 6)

    draw.text((70, size[1] - 88), "Uso comercial via API", font=micro_font, fill=hex_color(MUTED, 255))
    return panel


def build_brochure(logo_path: Path | None) -> Image.Image:
    image = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), hex_color(BG, 255))
    draw = ImageDraw.Draw(image)

    add_blur_blob(image, (1460, -220, 2520, 760), hex_color(CYAN, 54), 90)
    add_blur_blob(image, (-180, 2580, 860, 3600), hex_color(BLUE, 28), 110)
    add_blur_blob(image, (1620, 2520, 2560, 3400), hex_color(TEAL, 24), 120)

    grid_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid_layer)
    for x in range(1540, CANVAS_WIDTH, 104):
        grid_draw.line((x, 110, x, 1380), fill=hex_color("#c9dceb", 110), width=1)
    for y in range(110, 1380, 104):
        grid_draw.line((1540, y, CANVAS_WIDTH - 90, y), fill=hex_color("#c9dceb", 110), width=1)
    image.alpha_composite(grid_layer)

    draw.rounded_rectangle((150, 150, CANVAS_WIDTH - 150, CANVAS_HEIGHT - 150), radius=52, outline=hex_color(LINE, 220), width=2)

    display_xl = load_font(126, role="display", weight="bold")
    display_md = load_font(54, role="display", weight="bold")
    body_md = load_font(33, role="body", weight="regular")
    body_sm = load_font(27, role="body", weight="regular")
    body_bold = load_font(24, role="body", weight="bold")
    section_font = load_font(30, role="body", weight="bold")
    footer_title = load_font(34, role="display", weight="bold")

    draw_chip(
        draw,
        (150, 168, 472, 228),
        "OCR DOCUMENTAL VIA API",
        body_bold,
        hex_color(SOFT_CYAN, 255),
        hex_color("#b7dfe9", 255),
        hex_color(TEAL, 255),
    )

    brand = build_brand_block((560, 118), logo_path)
    image.alpha_composite(brand, (1770, 150))

    draw.text((150, 302), "OCR Master", font=display_xl, fill=hex_color(TEXT, 255))
    draw.text((150, 448), "OCR documental para integracion via API.", font=display_md, fill=hex_color(NAVY, 255))
    draw_paragraph(
        draw,
        (150, 554),
        "Procesa PDF e imagenes y devuelve JSON estructurado listo para integrar en flujos, portales o sistemas internos. Su uso principal es mediante API, con una propuesta simple, moderna y escalable.",
        body_md,
        hex_color(MUTED, 255),
        1100,
        12,
    )

    draw.text((150, 820), "Ideal para integracion B2B, onboarding, validacion y operaciones documentales.", font=body_sm, fill=hex_color(NAVY, 255))

    chip_y = 900
    chip_w = 300
    chip_gap = 24
    left_chips = [
        "PDF e imagenes",
        "JSON estructurado",
        "Escalable por volumen",
    ]
    for index, chip in enumerate(left_chips):
        x0 = 150 + index * (chip_w + chip_gap)
        draw_chip(
            draw,
            (x0, chip_y, x0 + chip_w, chip_y + 64),
            chip,
            body_bold,
            hex_color(WHITE, 215),
            hex_color(LINE, 255),
            hex_color(NAVY, 255),
        )

    api_rect = (1400, 306, 2330, 1060)
    add_shadow(image, api_rect, radius=42, fill=hex_color(NAVY_DEEP, 58), offset=(0, 28), blur=40)
    api_panel = build_api_panel((api_rect[2] - api_rect[0], api_rect[3] - api_rect[1]))
    image.alpha_composite(api_panel, (api_rect[0], api_rect[1]))

    draw.text((150, 1210), "Propuesta breve", font=section_font, fill=hex_color(TEAL, 255))
    draw.text((150, 1260), "Una sola hoja para explicar producto, consumo via API y planes comerciales.", font=body_sm, fill=hex_color(MUTED, 255))

    benefit_y = 1335
    benefit_w = 690
    benefit_h = 224
    benefit_gap = 55
    benefit_specs = [
        ("Consumo simple", "Una app pensada para integrarse rapido mediante API.", BLUE),
        ("Respuesta util", "Entrega salida estructurada para procesos y sistemas.", TEAL),
        ("Escala comercial", "Planes mensuales desde 2,500 hasta 20,000 documentos.", CYAN),
    ]
    for index, (title, body, accent) in enumerate(benefit_specs):
        x = 150 + index * (benefit_w + benefit_gap)
        rect = (x, benefit_y, x + benefit_w, benefit_y + benefit_h)
        add_shadow(image, rect, radius=34, fill=hex_color("#7f98ae", 24), offset=(0, 14), blur=24)
        benefit = build_benefit_card((benefit_w, benefit_h), title, body, accent)
        image.alpha_composite(benefit, (x, benefit_y))

    draw.text((150, 1660), "Planes y precios", font=load_font(72, role="display", weight="bold"), fill=hex_color(TEXT, 255))
    draw.text((150, 1750), "Valores mensuales en USD. Facturacion anual o mensual segun el plan.", font=body_sm, fill=hex_color(MUTED, 255))

    plan_y = 1838
    plan_w = 690
    plan_h = 1120
    plan_gap = 55
    plans = [
        {
            "title": "Standard",
            "volume": "2,500",
            "description": "Base comercial para flujos estables con volumen mensual incluido.",
            "annual_price": "USD 170",
            "annual_note": "por mes con pago anual",
            "monthly_price": "USD 190",
            "monthly_note": "por mes con pago mensual",
            "footer_note": "Volumen mensual incluido.",
            "accent": BLUE,
            "tint": SOFT_BLUE,
        },
        {
            "title": "Pro",
            "volume": "10,000",
            "description": "Mayor capacidad para equipos con mas carga y crecimiento por documento extra.",
            "annual_price": "USD 500",
            "annual_note": "por mes con pago anual",
            "monthly_price": "USD 570",
            "monthly_note": "por mes con pago mensual",
            "footer_note": "Documentos extra: USD 0.04 por documento.",
            "accent": TEAL,
            "tint": SOFT_TEAL,
        },
        {
            "title": "Premium",
            "volume": "20,000",
            "description": "Alto volumen con mejor valor para documentos adicionales.",
            "annual_price": "USD 850",
            "annual_note": "por mes con pago anual",
            "monthly_price": "USD 969",
            "monthly_note": "por mes con pago mensual",
            "footer_note": "Documentos extra: USD 0.03 por documento.",
            "accent": NAVY,
            "tint": BG_SOFT,
        },
    ]

    for index, plan in enumerate(plans):
        x = 150 + index * (plan_w + plan_gap)
        rect = (x, plan_y, x + plan_w, plan_y + plan_h)
        add_shadow(image, rect, radius=42, fill=hex_color("#68839d", 28), offset=(0, 22), blur=28)
        card = build_plan_card(
            (plan_w, plan_h),
            title=plan["title"],
            volume=plan["volume"],
            description=plan["description"],
            annual_price=plan["annual_price"],
            annual_note=plan["annual_note"],
            monthly_price=plan["monthly_price"],
            monthly_note=plan["monthly_note"],
            footer_note=plan["footer_note"],
            accent=plan["accent"],
            tint=plan["tint"],
        )
        image.alpha_composite(card, (x, plan_y))

    footer_rect = (150, 3075, CANVAS_WIDTH - 150, 3330)
    add_shadow(image, footer_rect, radius=38, fill=hex_color("#7a93aa", 20), offset=(0, 14), blur=22)
    draw.rounded_rectangle(footer_rect, radius=38, fill=hex_color(WHITE, 220), outline=hex_color(LINE, 255), width=2)
    draw.text((200, 3142), "YAGO SPA", font=footer_title, fill=hex_color(TEXT, 255))
    draw.text((200, 3194), "OCR Master es una propuesta comercial API-first para automatizacion documental y consumo escalable.", font=body_sm, fill=hex_color(MUTED, 255))
    draw.text((200, 3244), "Precios en USD. Disponible para piloto, demo e integracion.", font=body_sm, fill=hex_color(NAVY, 255))

    draw_chip(
        draw,
        (1812, 3140, 2280, 3202),
        "PDF / JPG / PNG / HEIC",
        body_bold,
        hex_color(SOFT_CYAN, 255),
        hex_color("#b7dfe9", 255),
        hex_color(TEAL, 255),
    )
    draw_chip(
        draw,
        (1812, 3222, 2280, 3284),
        "POST /v1/process -> JSON",
        body_bold,
        hex_color(SOFT_BLUE, 255),
        hex_color("#c7d9f0", 255),
        hex_color(BLUE, 255),
    )

    return image.convert("RGB")


def export_pdf(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    png_stream = BytesIO()
    image.save(png_stream, format="PNG", optimize=True)

    document = fitz.open()
    page = document.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    page.insert_image(page.rect, stream=png_stream.getvalue())
    document.set_metadata(
        {
            "title": "OCR Master - brochure comercial",
            "author": "YAGO SPA",
            "subject": "OCR documental via API",
            "keywords": "ocr, api, brochure, pricing",
            "creator": "scripts/generate-brochure.py",
        }
    )
    document.save(output, deflate=True, garbage=4)
    document.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generates a one-page commercial brochure PDF.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PDF path.")
    parser.add_argument("--logo", type=Path, default=None, help="Optional logo image path.")
    parser.add_argument("--preview", type=Path, default=None, help="Optional PNG preview path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logo_path = args.logo.resolve() if args.logo else None
    brochure = build_brochure(logo_path)
    export_pdf(brochure, args.output.resolve())
    if args.preview:
        preview_path = args.preview.resolve()
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        brochure.save(preview_path, format="PNG", optimize=True)
    print(f"Created brochure PDF: {args.output.resolve()}")
    if args.preview:
        print(f"Created brochure preview: {args.preview.resolve()}")


if __name__ == "__main__":
    main()
