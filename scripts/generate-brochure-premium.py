from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "marketing" / "ocr-master-brochure-premium.pdf"

A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842
CANVAS_WIDTH = 2480
CANVAS_HEIGHT = 3508

BG_TOP = "#07111d"
BG_BOTTOM = "#0f1f33"
TEXT = "#f5f1e8"
TEXT_SOFT = "#c8d4e2"
TEXT_MUTED = "#8ea0b5"
LINE = "#2b445e"
CARD = "#0d1827"
CARD_SOFT = "#111f31"
CARD_GLOW = "#13283f"
BLUE = "#58b7ff"
CYAN = "#2fd4ff"
GOLD = "#d8b36c"
GOLD_SOFT = "#7d6232"
WHITE = "#ffffff"
MINT = "#7fe6cf"


def hex_color(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = value.lstrip("#")
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return red, green, blue, alpha


def blend(a: str, b: str, factor: float) -> tuple[int, int, int, int]:
    ar, ag, ab, _ = hex_color(a)
    br, bg, bb, _ = hex_color(b)
    red = int(ar + (br - ar) * factor)
    green = int(ag + (bg - ag) * factor)
    blue = int(ab + (bb - ab) * factor)
    return red, green, blue, 255


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


def draw_paragraph(draw: Any, xy: tuple[int, int], text: str, font: Any, fill: tuple[int, int, int, int], max_width: int, line_gap: int) -> int:
    x, y = xy
    for line in wrap_text(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += text_size(draw, line, font)[1] + line_gap
    return y


def draw_centered_text(draw: Any, center_x: int, y: int, text: str, font: Any, fill: tuple[int, int, int, int]) -> int:
    width, height = text_size(draw, text, font)
    draw.text((center_x - (width / 2), y), text, font=font, fill=fill)
    return y + height


def draw_paragraph_center(draw: Any, center_x: int, y: int, text: str, font: Any, fill: tuple[int, int, int, int], max_width: int, line_gap: int) -> int:
    for line in wrap_text(draw, text, font, max_width):
        width, height = text_size(draw, line, font)
        draw.text((center_x - (width / 2), y), line, font=font, fill=fill)
        y += height + line_gap
    return y


def add_glow(image: Image.Image, bounds: tuple[int, int, int, int], fill: tuple[int, int, int, int], blur: int) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.ellipse(bounds, fill=fill)
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def add_shadow(image: Image.Image, rect: tuple[int, int, int, int], radius: int, fill: tuple[int, int, int, int], blur: int = 30, offset: tuple[int, int] = (0, 22)) -> None:
    x0, y0, x1, y1 = rect
    width = x1 - x0
    height = y1 - y0
    ox, oy = offset
    pad = blur + max(abs(ox), abs(oy)) + 12
    shadow = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((pad + ox, pad + oy, pad + ox + width, pad + oy + height), radius=radius, fill=fill)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    image.alpha_composite(shadow, (x0 - pad, y0 - pad))


def vertical_gradient(image: Image.Image, top: str, bottom: str) -> None:
    draw = ImageDraw.Draw(image)
    for y in range(CANVAS_HEIGHT):
        color = blend(top, bottom, y / max(1, CANVAS_HEIGHT - 1))
        draw.line((0, y, CANVAS_WIDTH, y), fill=color, width=1)


def draw_chip(draw: Any, rect: tuple[int, int, int, int], text: str, font: Any, fill: tuple[int, int, int, int], outline: tuple[int, int, int, int], text_fill: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(rect, radius=(rect[3] - rect[1]) // 2, fill=fill, outline=outline, width=2)
    width, height = text_size(draw, text, font)
    x0, y0, x1, y1 = rect
    draw.text((x0 + ((x1 - x0 - width) / 2), y0 + ((y1 - y0 - height) / 2) - 2), text, font=font, fill=text_fill)


def build_brand_panel(size: tuple[int, int], logo_path: Path | None) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=34, fill=hex_color(WHITE, 18), outline=hex_color(LINE, 240), width=2)

    display = load_font(46, role="display", weight="bold")
    body = load_font(26, role="body", weight="regular")

    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((92, 92), Image.Resampling.LANCZOS)
        panel.alpha_composite(logo, (26, (size[1] - logo.height) // 2))
        text_x = 146
    else:
        draw.rounded_rectangle((28, 22, 42, size[1] - 22), radius=6, fill=hex_color(CYAN, 255))
        text_x = 72

    draw.text((text_x, 26), "YAGO SPA", font=display, fill=hex_color(TEXT, 255))
    draw.text((text_x, 76), "Version premium comercial", font=body, fill=hex_color(TEXT_MUTED, 255))
    return panel


def build_api_panel(size: tuple[int, int]) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)

    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=44, fill=hex_color(CARD, 228), outline=hex_color("#33506d", 255), width=2)
    draw.rounded_rectangle((0, 0, size[0] - 1, 12), radius=44, fill=hex_color(GOLD, 255))

    grid = Image.new("RGBA", size, (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(50, size[0], 86):
        grid_draw.line((x, 0, x, size[1]), fill=hex_color("#30506f", 52), width=1)
    for y in range(50, size[1], 86):
        grid_draw.line((0, y, size[0], y), fill=hex_color("#30506f", 52), width=1)
    panel.alpha_composite(grid)

    add_glow(panel, (size[0] - 260, -80, size[0] + 120, 280), hex_color(CYAN, 62), 42)
    add_glow(panel, (-180, size[1] - 240, 220, size[1] + 110), hex_color(GOLD, 36), 54)

    chip_font = load_font(24, role="body", weight="bold")
    title_font = load_font(48, role="display", weight="bold")
    body_font = load_font(28, role="body", weight="regular")
    value_font = load_font(30, role="body", weight="bold")
    label_font = load_font(22, role="body", weight="bold")
    note_font = load_font(23, role="body", weight="regular")

    draw_chip(draw, (54, 48, 332, 104), "API-FIRST PREMIUM", chip_font, hex_color("#12253a", 255), hex_color("#35607a", 255), hex_color(CYAN, 255))
    draw.text((54, 148), "Integracion lista", font=title_font, fill=hex_color(TEXT, 255))
    y = draw_paragraph(draw, (54, 218), "Endpoint central para integrar OCR Master con sistemas, portales y automatizacion documental.", body_font, hex_color(TEXT_SOFT, 255), size[0] - 108, 8)

    value_rows = [
        ("ENDPOINT", "POST /v1/process"),
        ("AUTH", "x-api-key"),
        ("FORMATOS", "PDF | JPG | PNG | HEIC"),
        ("SALIDA", "JSON estructurado"),
    ]

    row_y = y + 36
    for label, value in value_rows:
        row_rect = (54, row_y, size[0] - 54, row_y + 86)
        draw.rounded_rectangle(row_rect, radius=24, fill=hex_color(WHITE, 240), outline=hex_color("#c4d4e4", 255), width=2)
        draw.text((80, row_y + 17), label, font=label_font, fill=hex_color("#799dc0", 255))
        draw.text((252, row_y + 14), value, font=value_font, fill=hex_color(BG_TOP, 255))
        row_y += 102

    metric_rect = (54, size[1] - 254, size[0] - 54, size[1] - 54)
    draw.rounded_rectangle(metric_rect, radius=28, fill=hex_color("#101d2c", 255), outline=hex_color(GOLD_SOFT, 255), width=2)
    draw.text((84, size[1] - 228), "META OPERATIVA", font=label_font, fill=hex_color(GOLD, 255))
    draw.text((84, size[1] - 178), "Hasta 95% de confianza de datos", font=load_font(40, role="display", weight="bold"), fill=hex_color(TEXT, 255))
    draw_paragraph(draw, (84, size[1] - 122), "Segun calidad del archivo, tipo documental y configuracion del flujo.", note_font, hex_color(TEXT_MUTED, 255), size[0] - 168, 6)
    return panel


def build_feature_panel(size: tuple[int, int], title: str, body: str, accent: str) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=34, fill=hex_color(WHITE, 14), outline=hex_color(LINE, 240), width=2)
    draw.rounded_rectangle((24, 24, 86, 86), radius=18, fill=hex_color(accent, 255))
    draw.text((120, 30), title, font=load_font(40, role="display", weight="bold"), fill=hex_color(TEXT, 255))
    draw_paragraph(draw, (120, 92), body, load_font(27, role="body", weight="regular"), hex_color(TEXT_SOFT, 255), size[0] - 150, 8)
    return panel


def build_price_block(size: tuple[int, int], title: str, price: str, note: str, accent: str) -> Image.Image:
    block = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=26, fill=hex_color(WHITE, 245), outline=hex_color("#d7e0ea", 255), width=2)
    center_x = size[0] // 2
    draw.rounded_rectangle((26, 18, size[0] - 26, 26), radius=4, fill=hex_color(accent, 110))
    label_font = load_font(22, role="body", weight="bold")
    price_font = load_font(46, role="display", weight="bold")
    note_font = load_font(22, role="body", weight="regular")
    draw_centered_text(draw, center_x, 36, title.upper(), label_font, hex_color(accent, 255))
    price_end = draw_centered_text(draw, center_x, 78, price, price_font, hex_color(BG_TOP, 255))
    draw_paragraph_center(draw, center_x, price_end + 18, note, note_font, hex_color("#61758a", 255), size[0] - 56, 4)
    return block


def build_plan_card(size: tuple[int, int], title: str, volume: str, description: str, annual_price: str, monthly_price: str, extra_note: str, accent: str, highlight: bool = False) -> Image.Image:
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    fill = hex_color(CARD_SOFT if highlight else CARD, 238)
    outline = hex_color(GOLD if highlight else LINE, 255)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=42, fill=fill, outline=outline, width=2)
    draw.rounded_rectangle((0, 0, size[0] - 1, 16), radius=42, fill=hex_color(accent, 255))
    add_glow(panel, (size[0] - 240, -60, size[0] + 80, 260), hex_color(accent, 28 if highlight else 18), 40)
    add_glow(panel, (-120, size[1] - 250, 220, size[1] + 80), hex_color(accent, 12), 52)

    chip_fill = hex_color(GOLD, 44) if highlight else hex_color(WHITE, 16)
    chip_outline = hex_color(GOLD_SOFT if highlight else LINE, 255)
    chip_w = 162
    chip_x0 = (size[0] - chip_w) // 2
    draw.rounded_rectangle((chip_x0, 46, chip_x0 + chip_w, 100), radius=24, fill=chip_fill, outline=chip_outline, width=2)
    draw_centered_text(draw, size[0] // 2, 61, "PLAN", load_font(24, role="body", weight="bold"), hex_color(accent, 255))

    draw_centered_text(draw, size[0] // 2, 138, title, load_font(58, role="display", weight="bold"), hex_color(TEXT, 255))
    draw_centered_text(draw, size[0] // 2, 242, volume, load_font(64, role="display", weight="bold"), hex_color(TEXT, 255))
    draw_centered_text(draw, size[0] // 2, 326, "documentos / mes", load_font(28, role="body", weight="regular"), hex_color(TEXT_MUTED, 255))
    after = draw_paragraph_center(draw, size[0] // 2, 392, description, load_font(28, role="body", weight="regular"), hex_color(TEXT_SOFT, 255), size[0] - 164, 8)

    block_y = after + 40
    block_w = (size[0] - 70 * 2 - 24) // 2
    annual = build_price_block((block_w, 216), "Pago anual", annual_price, "por mes con pago anual", accent)
    monthly = build_price_block((block_w, 216), "Pago mensual", monthly_price, "por mes con pago mensual", accent)
    panel.alpha_composite(annual, (70, block_y))
    panel.alpha_composite(monthly, (70 + block_w + 24, block_y))

    footer_rect = (70, block_y + 268, size[0] - 70, block_y + 390)
    footer_fill = hex_color(GOLD, 34) if highlight else hex_color(WHITE, 14)
    footer_outline = hex_color(GOLD_SOFT if highlight else LINE, 255)
    draw.rounded_rectangle(footer_rect, radius=28, fill=footer_fill, outline=footer_outline, width=2)
    draw_paragraph_center(draw, size[0] // 2, block_y + 306, extra_note, load_font(28, role="body", weight="bold"), hex_color(TEXT, 255), size[0] - 192, 6)

    bottom_y = size[1] - 184
    draw_chip(draw, (70, bottom_y, size[0] - 70, bottom_y + 58), "Uso comercial via API", load_font(22, role="body", weight="bold"), hex_color(WHITE, 12), hex_color(LINE, 255), hex_color(TEXT_SOFT, 255))
    draw_chip(draw, (70, bottom_y + 78, size[0] - 70, bottom_y + 136), "Meta operativa: hasta 95% de confianza", load_font(22, role="body", weight="bold"), hex_color(WHITE, 12), hex_color(LINE, 255), hex_color(TEXT_SOFT, 255))
    return panel


def build_brochure(logo_path: Path | None) -> Image.Image:
    image = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 255))
    vertical_gradient(image, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(image)

    add_glow(image, (-180, -180, 1120, 760), hex_color(CYAN, 34), 120)
    add_glow(image, (1640, -120, 2580, 660), hex_color(BLUE, 26), 120)
    add_glow(image, (1760, 2560, 2560, 3440), hex_color(GOLD, 20), 140)
    add_glow(image, (-220, 2480, 860, 3500), hex_color(CYAN, 20), 140)

    lines = Image.new("RGBA", image.size, (0, 0, 0, 0))
    lines_draw = ImageDraw.Draw(lines)
    for x in range(120, CANVAS_WIDTH - 120, 140):
        lines_draw.line((x, 120, x, CANVAS_HEIGHT - 120), fill=hex_color("#28425d", 38), width=1)
    for y in range(120, CANVAS_HEIGHT - 120, 140):
        lines_draw.line((120, y, CANVAS_WIDTH - 120, y), fill=hex_color("#28425d", 24), width=1)
    image.alpha_composite(lines)

    outer = (110, 110, CANVAS_WIDTH - 110, CANVAS_HEIGHT - 110)
    draw.rounded_rectangle(outer, radius=52, outline=hex_color("#26405a", 160), width=2)

    brand = build_brand_panel((600, 122), logo_path)
    image.alpha_composite(brand, (1760, 146))

    label_font = load_font(24, role="body", weight="bold")
    display_xl = load_font(132, role="display", weight="bold")
    display_md = load_font(58, role="display", weight="bold")
    body_lg = load_font(33, role="body", weight="regular")
    body_md = load_font(28, role="body", weight="regular")
    body_bold = load_font(24, role="body", weight="bold")

    draw_chip(draw, (150, 162, 488, 220), "OCR PREMIUM VIA API", label_font, hex_color("#12253a", 255), hex_color("#335775", 255), hex_color(GOLD, 255))
    draw.text((150, 298), "OCR Master", font=display_xl, fill=hex_color(TEXT, 255))
    draw.text((150, 454), "OCR premium para integracion API.", font=display_md, fill=hex_color(TEXT, 255))

    para_end = draw_paragraph(
        draw,
        (150, 570),
        "Procesa PDF e imagenes y entrega JSON estructurado listo para sistemas, onboarding y operaciones documentales. Pensado para uso comercial B2B con una meta operativa de hasta 95% de confianza de datos en flujos compatibles.",
        body_lg,
        hex_color(TEXT_SOFT, 255),
        940,
        10,
    )
    draw.text((150, para_end + 44), "Tecnologia, presentacion comercial clara y propuesta lista para demo o piloto.", font=body_md, fill=hex_color(TEXT, 255))

    chip_y = para_end + 112
    chips = [
        "Integracion simple",
        "Salida JSON",
        "Escalable por volumen",
    ]
    for index, text in enumerate(chips):
        x0 = 150 + index * 334
        draw_chip(draw, (x0, chip_y, x0 + 300, chip_y + 62), text, body_bold, hex_color(CARD_GLOW, 230), hex_color(LINE, 255), hex_color(TEXT, 255))

    api_rect = (1400, 304, 2336, 1280)
    add_shadow(image, api_rect, radius=44, fill=hex_color("#02060b", 170), blur=46, offset=(0, 28))
    api_panel = build_api_panel((api_rect[2] - api_rect[0], api_rect[3] - api_rect[1]))
    image.alpha_composite(api_panel, (api_rect[0], api_rect[1]))

    draw.text((150, 1216), "Propuesta comercial", font=load_font(32, role="body", weight="bold"), fill=hex_color(CYAN, 255))
    draw.text((150, 1272), "Brochure premium de una hoja para explicar producto, API, precision objetivo y precios.", font=body_md, fill=hex_color(TEXT_MUTED, 255))

    features = [
        ("Integracion simple", "Implementacion rapida sobre un endpoint central, autenticado y listo para flujos B2B.", CYAN),
        ("Precision objetivo", "Meta operativa de hasta 95% de confianza de datos en escenarios compatibles.", GOLD),
        ("Escala comercial", "Planes mensuales desde 2,500 hasta 20,000 documentos, con extras en Pro y Premium.", MINT),
    ]
    feature_y = 1360
    feature_w = 690
    feature_h = 228
    for index, (title, body, accent) in enumerate(features):
        x = 150 + index * 745
        rect = (x, feature_y, x + feature_w, feature_y + feature_h)
        add_shadow(image, rect, radius=34, fill=hex_color("#010406", 140), blur=28, offset=(0, 16))
        panel = build_feature_panel((feature_w, feature_h), title, body, accent)
        image.alpha_composite(panel, (x, feature_y))

    draw.text((150, 1708), "Planes y precios", font=load_font(78, role="display", weight="bold"), fill=hex_color(TEXT, 255))
    draw.text((150, 1802), "Valores mensuales en USD. Pago anual o mensual segun el plan.", font=body_md, fill=hex_color(TEXT_MUTED, 255))

    plan_y = 1898
    plan_w = 690
    plan_h = 1180
    cards = [
        {
            "title": "Standard",
            "volume": "2,500",
            "description": "Base comercial para equipos que necesitan una propuesta clara, moderna y lista para empezar.",
            "annual_price": "USD 170",
            "monthly_price": "USD 190",
            "extra_note": "Volumen mensual incluido.",
            "accent": CYAN,
            "highlight": False,
        },
        {
            "title": "Pro",
            "volume": "10,000",
            "description": "Mayor capacidad para operaciones con mas carga y crecimiento controlado por documento adicional.",
            "annual_price": "USD 500",
            "monthly_price": "USD 570",
            "extra_note": "Documentos extra: USD 0.04 por documento.",
            "accent": MINT,
            "highlight": False,
        },
        {
            "title": "Premium",
            "volume": "20,000",
            "description": "Version de mayor volumen, mejor valor para extras y posicionamiento mas premium para cuentas exigentes.",
            "annual_price": "USD 850",
            "monthly_price": "USD 969",
            "extra_note": "Documentos extra: USD 0.03 por documento.",
            "accent": GOLD,
            "highlight": True,
        },
    ]

    for index, card_data in enumerate(cards):
        x = 150 + index * 745
        rect = (x, plan_y, x + plan_w, plan_y + plan_h)
        add_shadow(image, rect, radius=42, fill=hex_color("#02060b", 170), blur=34, offset=(0, 24))
        card = build_plan_card(
            (plan_w, plan_h),
            title=card_data["title"],
            volume=card_data["volume"],
            description=card_data["description"],
            annual_price=card_data["annual_price"],
            monthly_price=card_data["monthly_price"],
            extra_note=card_data["extra_note"],
            accent=card_data["accent"],
            highlight=card_data["highlight"],
        )
        image.alpha_composite(card, (x, plan_y))

    footer_rect = (150, 3196, CANVAS_WIDTH - 150, 3378)
    add_shadow(image, footer_rect, radius=38, fill=hex_color("#02060b", 140), blur=24, offset=(0, 18))
    draw.rounded_rectangle(footer_rect, radius=38, fill=hex_color(CARD_GLOW, 236), outline=hex_color(LINE, 255), width=2)
    draw.text((194, 3248), "YAGO SPA", font=load_font(36, role="display", weight="bold"), fill=hex_color(TEXT, 255))
    draw.text((194, 3298), "OCR Master se presenta como propuesta premium para automatizacion documental mediante API.", font=load_font(28, role="body", weight="regular"), fill=hex_color(TEXT_SOFT, 255))
    draw.text((194, 3338), "Brochure refinado para propuesta comercial, demo o presentacion ejecutiva.", font=load_font(24, role="body", weight="regular"), fill=hex_color(TEXT_MUTED, 255))

    draw_chip(draw, (1700, 3240, 2280, 3300), "Hasta 95% de confianza de datos", load_font(23, role="body", weight="bold"), hex_color("#1a2533", 255), hex_color(GOLD_SOFT, 255), hex_color(GOLD, 255))
    draw_chip(draw, (1700, 3314, 2280, 3374), "POST /v1/process -> JSON", load_font(23, role="body", weight="bold"), hex_color("#11253a", 255), hex_color("#2f5672", 255), hex_color(CYAN, 255))

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
            "title": "OCR Master - brochure premium comercial",
            "author": "YAGO SPA",
            "subject": "OCR premium via API",
            "keywords": "ocr, premium, api, brochure, pricing",
            "creator": "scripts/generate-brochure-premium.py",
        }
    )
    document.save(output, deflate=True, garbage=4)
    document.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generates the premium commercial OCR brochure PDF.")
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
    print(f"Created premium brochure PDF: {args.output.resolve()}")
    if args.preview:
        print(f"Created premium brochure preview: {args.preview.resolve()}")


if __name__ == "__main__":
    main()
