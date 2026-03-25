from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, ListFlowable, ListItem, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Informe_OCR_Premium_Deluxe.pdf"


PALETTE = {
    "ink": colors.HexColor("#0F172A"),
    "text": colors.HexColor("#1E293B"),
    "muted": colors.HexColor("#475569"),
    "line": colors.HexColor("#CBD5E1"),
    "soft": colors.HexColor("#F8FAFC"),
    "soft_blue": colors.HexColor("#EEF6FF"),
    "soft_green": colors.HexColor("#ECFDF3"),
    "soft_amber": colors.HexColor("#FFF7ED"),
    "blue": colors.HexColor("#2563EB"),
    "green": colors.HexColor("#16A34A"),
    "amber": colors.HexColor("#D97706"),
    "red": colors.HexColor("#DC2626"),
    "hero": colors.HexColor("#0B1220"),
}


@dataclass(frozen=True)
class VmOption:
    name: str
    vm_total: float
    description: str
    use_case: str


@dataclass(frozen=True)
class RouteCost:
    level: str
    route_name: str
    percent: float
    unit_cost: float
    detail: str
    trigger: str


@dataclass(frozen=True)
class VariableScenario:
    name: str
    shares: tuple[float, float, float, float]
    comment: str


SUPABASE_PRO_COST = 25.00

VM_OPTIONS = {
    "Opcion 1": VmOption(
        name="Opcion 1",
        vm_total=98.40,
        description="1 VM 4 vCPU / 8 GB / 80 GB SSD",
        use_case="Entrada economica. Sirve para arrancar con 5.000 OCR/mes y trafico moderado.",
    ),
    "Opcion 2": VmOption(
        name="Opcion 2",
        vm_total=147.60,
        description="VM API 2 vCPU / 4 GB / 40 GB SSD + VM OCR 4 vCPU / 8 GB / 80 GB SSD",
        use_case="La mejor relacion costo / estabilidad. Recomendacion general para 10.000 a 20.000 OCR/mes.",
    ),
    "Opcion 3": VmOption(
        name="Opcion 3",
        vm_total=234.10,
        description="VM API 2 vCPU / 4 GB / 50 GB SSD + VM OCR 8 vCPU / 16 GB / 80 GB SSD",
        use_case="Mas holgura para picos, PDFs pesados o mas concurrencia simultanea.",
    ),
}

ROUTE_COSTS = (
    RouteCost("Nivel 1", "Barato", 0.70, 0.0015, "RapidOCR local", "Fotos buenas y campos criticos correctos"),
    RouteCost("Nivel 2", "Local reforzado", 0.15, 0.0040, "RapidOCR + segundo intento local", "Calidad media o falta un campo importante"),
    RouteCost("Nivel 3", "Premium controlado", 0.12, 0.0465, "RapidOCR + Azure", "Persisten dudas o faltan campos criticos"),
    RouteCost("Nivel 4", "Premium maximo puntual", 0.03, 0.0965, "RapidOCR + Azure + Google", "Casos muy dificiles o conflicto fuerte"),
)

VARIABLE_SCENARIOS = (
    VariableScenario("Optimista", (0.80, 0.12, 0.07, 0.01), "La mayoria de las capturas viene limpia y bien encuadrada."),
    VariableScenario("Base", (0.70, 0.15, 0.12, 0.03), "Escenario recomendado para presupuestar hoy."),
    VariableScenario("Exigente", (0.55, 0.20, 0.18, 0.07), "Mas fotos dudosas y mas documentos que escalan a Azure y Google."),
)

VOLUMES = (5000, 10000, 20000)

RECOMMENDED = {
    5000: "Opcion 1",
    10000: "Opcion 2",
    20000: "Opcion 2",
}


def money(value: float) -> str:
    return f"USD {Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def rate(value: float) -> str:
    precision = "0.0001" if value < 1 else "0.01"
    rounded = Decimal(str(value)).quantize(Decimal(precision), rounding=ROUND_HALF_UP)
    if value < 1:
        return f"USD {rounded:,.4f}"
    return f"USD {rounded:,.2f}"


def volume_label(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def pct(value: float) -> str:
    return f"{round(value * 100)}%"


def fixed_cost(option_name: str) -> float:
    value = Decimal(str(VM_OPTIONS[option_name].vm_total)) + Decimal(str(SUPABASE_PRO_COST))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def route_qty(volume: int, share: float) -> int:
    return int(round(volume * share))


def variable_cost(volume: int, shares: tuple[float, float, float, float] | None = None) -> float:
    active_shares = shares or tuple(route.percent for route in ROUTE_COSTS)
    total = sum((Decimal(str(route_qty(volume, share))) * Decimal(str(route.unit_cost)) for route, share in zip(ROUTE_COSTS, active_shares, strict=True)), Decimal("0"))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def total_cost(option_name: str, volume: int) -> float:
    total = Decimal(str(fixed_cost(option_name))) + Decimal(str(variable_cost(volume)))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def cost_per_doc(option_name: str, volume: int) -> float:
    value = Decimal(str(total_cost(option_name, volume))) / Decimal(str(volume))
    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def fixed_share(option_name: str, volume: int) -> float:
    value = Decimal(str(fixed_cost(option_name))) / Decimal(str(total_cost(option_name, volume)))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def variable_share(option_name: str, volume: int) -> float:
    value = Decimal(str(variable_cost(volume))) / Decimal(str(total_cost(option_name, volume)))
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def average_variable_cost(shares: tuple[float, float, float, float] | None = None) -> float:
    active_shares = shares or tuple(route.percent for route in ROUTE_COSTS)
    value = sum((Decimal(str(route.unit_cost)) * Decimal(str(share)) for route, share in zip(ROUTE_COSTS, active_shares, strict=True)), Decimal("0"))
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}
    styles["HeroTitle"] = ParagraphStyle(
        "HeroTitle",
        parent=sample["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        textColor=colors.white,
        spaceAfter=6,
    )
    styles["HeroSubtitle"] = ParagraphStyle(
        "HeroSubtitle",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=10.2,
        leading=14,
        textColor=colors.HexColor("#D7E3F4"),
        spaceAfter=4,
    )
    styles["Kicker"] = ParagraphStyle(
        "Kicker",
        parent=sample["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#93C5FD"),
        spaceAfter=4,
    )
    styles["Title"] = ParagraphStyle(
        "Title",
        parent=sample["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=PALETTE["ink"],
        spaceBefore=10,
        spaceAfter=6,
    )
    styles["Subtitle"] = ParagraphStyle(
        "Subtitle",
        parent=sample["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=PALETTE["ink"],
        spaceBefore=6,
        spaceAfter=4,
    )
    styles["Body"] = ParagraphStyle(
        "Body",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=9.4,
        leading=13,
        textColor=PALETTE["text"],
        spaceAfter=5,
    )
    styles["Small"] = ParagraphStyle(
        "Small",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10,
        textColor=PALETTE["muted"],
        spaceAfter=3,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=12.5,
        leftIndent=12,
        textColor=PALETTE["text"],
        spaceAfter=2,
    )
    styles["CardLabel"] = ParagraphStyle(
        "CardLabel",
        parent=sample["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=PALETTE["muted"],
        spaceAfter=3,
    )
    styles["CardValue"] = ParagraphStyle(
        "CardValue",
        parent=sample["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=PALETTE["ink"],
        spaceAfter=2,
    )
    styles["CardNote"] = ParagraphStyle(
        "CardNote",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10,
        textColor=PALETTE["muted"],
    )
    styles["CardValueInverse"] = ParagraphStyle(
        "CardValueInverse",
        parent=sample["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.white,
        spaceAfter=2,
    )
    styles["CardNoteInverse"] = ParagraphStyle(
        "CardNoteInverse",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10,
        textColor=colors.HexColor("#D7E3F4"),
    )
    styles["TableHead"] = ParagraphStyle(
        "TableHead",
        parent=sample["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8.1,
        leading=10,
        textColor=colors.white,
        alignment=1,
    )
    styles["TableCell"] = ParagraphStyle(
        "TableCell",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=10.3,
        textColor=PALETTE["text"],
    )
    styles["TableCellCenter"] = ParagraphStyle(
        "TableCellCenter",
        parent=styles["TableCell"],
        alignment=1,
    )
    styles["TableCellRight"] = ParagraphStyle(
        "TableCellRight",
        parent=styles["TableCell"],
        alignment=2,
    )
    return styles


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def bullets(lines: list[str], styles: dict[str, ParagraphStyle]) -> ListFlowable:
    return ListFlowable([p(line, styles["Bullet"]) for line in lines], bulletType="bullet", leftIndent=14)


def make_table(
    rows: list[list],
    col_widths: list[float],
    *,
    repeat_rows: int = 1,
    row_highlights: dict[int, colors.Color] | None = None,
) -> LongTable:
    table = LongTable(rows, colWidths=col_widths, repeatRows=repeat_rows)
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), PALETTE["ink"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, PALETTE["line"]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALETTE["soft"]]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )
    for row_index, color in (row_highlights or {}).items():
        style.add("BACKGROUND", (0, row_index), (-1, row_index), color)
        style.add("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold")
    table.setStyle(style)
    return table


def metric_card(label: str, value: str, note: str, *, accent: colors.Color, inverse: bool = False) -> Table:
    value_style = "CardValueInverse" if inverse else "CardValue"
    note_style = "CardNoteInverse" if inverse else "CardNote"
    background = PALETTE["hero"] if inverse else colors.white
    text_rows = [
        [p(label, styles["CardLabel"] if not inverse else styles["Kicker"])],
        [p(value, styles[value_style])],
        [p(note, styles[note_style])],
    ]
    card = Table(text_rows, colWidths=[54 * mm])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                ("BOX", (0, 0), (-1, -1), 0.6, accent if inverse else PALETTE["line"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return card


def info_box(title: str, lines: list[str], *, tone: str) -> Table:
    tone_map = {
        "blue": (PALETTE["soft_blue"], PALETTE["blue"]),
        "green": (PALETTE["soft_green"], PALETTE["green"]),
        "amber": (PALETTE["soft_amber"], PALETTE["amber"]),
    }
    background, accent = tone_map[tone]
    body = [p(title, styles["Subtitle"])]
    for line in lines:
        body.append(p(f"- {line}", styles["Body"]))
    table = Table([[body]], colWidths=[178 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                ("BOX", (0, 0), (-1, -1), 0.4, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def hero_block() -> Table:
    rows = [
        [p("OCR Premium Deluxe", styles["Kicker"])],
        [p("Informe para decidir infraestructura, costos y ruta de implementacion", styles["HeroTitle"])],
        [
            p(
                "Documento enfocado en una sola pregunta: cuanto te cuesta operar la app y que configuracion conviene segun el volumen mensual de OCR.",
                styles["HeroSubtitle"],
            )
        ],
        [p(f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["CardNoteInverse"])],
    ]
    hero = Table(rows, colWidths=[178 * mm])
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALETTE["hero"]),
                ("BOX", (0, 0), (-1, -1), 0.6, PALETTE["hero"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return hero


def first_page_cards() -> Table:
    cards = [
        metric_card("5.000 OCR/mes", money(total_cost("Opcion 1", 5000)), "Recomendado: Opcion 1 + Supabase Pro", accent=PALETTE["green"]),
        metric_card("10.000 OCR/mes", money(total_cost("Opcion 2", 10000)), "Recomendado: Opcion 2 + Supabase Pro", accent=PALETTE["blue"]),
        metric_card("20.000 OCR/mes", money(total_cost("Opcion 2", 20000)), "Recomendado: Opcion 2 + Supabase Pro", accent=PALETTE["amber"]),
    ]
    row = Table([cards], colWidths=[58 * mm, 58 * mm, 58 * mm])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return row


def decision_matrix_table() -> LongTable:
    rows = [[
        p("Volumen", styles["TableHead"]),
        p("Infra recomendada", styles["TableHead"]),
        p("Costo fijo", styles["TableHead"]),
        p("Costo variable", styles["TableHead"]),
        p("Total mensual", styles["TableHead"]),
        p("Costo / doc", styles["TableHead"]),
        p("Lectura", styles["TableHead"]),
    ]]
    entries = [
        (5000, "Opcion 1", "La entrada mas barata y razonable para arrancar."),
        (10000, "Opcion 2", "El mejor equilibrio entre costo y estabilidad."),
        (20000, "Opcion 2", "Sigue siendo la mejor opcion si el trafico viene repartido."),
        (20000, "Opcion 3", "Conviene solo si esperas picos fuertes o PDFs pesados."),
    ]
    for volume, option_name, note in entries:
        rows.append([
            p(volume_label(volume), styles["TableCellCenter"]),
            p(f"<b>{option_name}</b><br/>{VM_OPTIONS[option_name].description}", styles["TableCell"]),
            p(money(fixed_cost(option_name)), styles["TableCellRight"]),
            p(money(variable_cost(volume)), styles["TableCellRight"]),
            p(money(total_cost(option_name, volume)), styles["TableCellRight"]),
            p(f"USD {cost_per_doc(option_name, volume):.4f}", styles["TableCellRight"]),
            p(note, styles["TableCell"]),
        ])
    return make_table(
        rows,
        [18 * mm, 58 * mm, 22 * mm, 24 * mm, 24 * mm, 22 * mm, 36 * mm],
        row_highlights={2: PALETTE["soft_blue"], 3: PALETTE["soft_green"]},
    )


def fixed_cost_table() -> LongTable:
    rows = [[
        p("Opcion", styles["TableHead"]),
        p("VMs", styles["TableHead"]),
        p("Supabase", styles["TableHead"]),
        p("Fijo mensual", styles["TableHead"]),
        p("Cuando conviene", styles["TableHead"]),
    ]]
    for option in VM_OPTIONS.values():
        rows.append([
            p(option.name, styles["TableCellCenter"]),
            p(money(option.vm_total), styles["TableCellRight"]),
            p(money(SUPABASE_PRO_COST), styles["TableCellRight"]),
            p(money(fixed_cost(option.name)), styles["TableCellRight"]),
            p(option.use_case, styles["TableCell"]),
        ])
    return make_table(rows, [20 * mm, 22 * mm, 22 * mm, 24 * mm, 90 * mm], row_highlights={2: PALETTE["soft_green"]})


def variable_cost_table() -> LongTable:
    rows = [[
        p("Ruta", styles["TableHead"]),
        p("Mezcla", styles["TableHead"]),
        p("Costo / doc", styles["TableHead"]),
        p("5.000 OCR", styles["TableHead"]),
        p("10.000 OCR", styles["TableHead"]),
        p("20.000 OCR", styles["TableHead"]),
        p("Cuando entra", styles["TableHead"]),
    ]]
    for route in ROUTE_COSTS:
        rows.append([
            p(f"<b>{route.level}</b><br/>{route.route_name}", styles["TableCell"]),
            p(pct(route.percent), styles["TableCellCenter"]),
            p(rate(route.unit_cost), styles["TableCellRight"]),
            p(f"{volume_label(route_qty(5000, route.percent))} docs<br/>{money(route_qty(5000, route.percent) * route.unit_cost)}", styles["TableCell"]),
            p(f"{volume_label(route_qty(10000, route.percent))} docs<br/>{money(route_qty(10000, route.percent) * route.unit_cost)}", styles["TableCell"]),
            p(f"{volume_label(route_qty(20000, route.percent))} docs<br/>{money(route_qty(20000, route.percent) * route.unit_cost)}", styles["TableCell"]),
            p(route.trigger, styles["TableCell"]),
        ])
    rows.append([
        p("<b>Total variable OCR</b>", styles["TableCell"]),
        p("100%", styles["TableCellCenter"]),
        p(rate(average_variable_cost()), styles["TableCellRight"]),
        p(money(variable_cost(5000)), styles["TableCellRight"]),
        p(money(variable_cost(10000)), styles["TableCellRight"]),
        p(money(variable_cost(20000)), styles["TableCellRight"]),
        p("Escenario base del flujo inteligente", styles["TableCell"]),
    ])
    return make_table(rows, [24 * mm, 16 * mm, 22 * mm, 28 * mm, 28 * mm, 28 * mm, 34 * mm], row_highlights={5: PALETTE["soft_blue"]})


def sensitivity_table() -> LongTable:
    rows = [[
        p("Escenario", styles["TableHead"]),
        p("Costo variable medio / doc", styles["TableHead"]),
        p("5.000 OCR", styles["TableHead"]),
        p("10.000 OCR", styles["TableHead"]),
        p("20.000 OCR", styles["TableHead"]),
        p("Lectura", styles["TableHead"]),
    ]]
    highlights = {}
    for index, scenario in enumerate(VARIABLE_SCENARIOS, start=1):
        rows.append([
            p(scenario.name, styles["TableCellCenter"]),
            p(rate(average_variable_cost(scenario.shares)), styles["TableCellRight"]),
            p(money(variable_cost(5000, scenario.shares)), styles["TableCellRight"]),
            p(money(variable_cost(10000, scenario.shares)), styles["TableCellRight"]),
            p(money(variable_cost(20000, scenario.shares)), styles["TableCellRight"]),
            p(scenario.comment, styles["TableCell"]),
        ])
        if scenario.name == "Base":
            highlights[index] = PALETTE["soft_green"]
    return make_table(rows, [24 * mm, 30 * mm, 24 * mm, 24 * mm, 24 * mm, 54 * mm], row_highlights=highlights)


def fixed_vs_variable_table() -> LongTable:
    rows = [[
        p("Escenario recomendado", styles["TableHead"]),
        p("Costo fijo", styles["TableHead"]),
        p("Costo variable", styles["TableHead"]),
        p("Peso del fijo", styles["TableHead"]),
        p("Peso del variable", styles["TableHead"]),
    ]]
    for volume, option_name in RECOMMENDED.items():
        rows.append([
            p(f"{volume_label(volume)} con {option_name}", styles["TableCell"]),
            p(money(fixed_cost(option_name)), styles["TableCellRight"]),
            p(money(variable_cost(volume)), styles["TableCellRight"]),
            p(pct(fixed_share(option_name, volume)), styles["TableCellCenter"]),
            p(pct(variable_share(option_name, volume)), styles["TableCellCenter"]),
        ])
    return make_table(rows, [48 * mm, 30 * mm, 30 * mm, 28 * mm, 28 * mm], row_highlights={2: PALETTE["soft_blue"]})


def route_cards() -> Table:
    cards = []
    accents = [PALETTE["green"], PALETTE["blue"], PALETTE["amber"], PALETTE["red"]]
    for route, accent in zip(ROUTE_COSTS, accents, strict=True):
        cards.append(
            metric_card(
                f"{route.level} - {route.route_name}",
                rate(route.unit_cost),
                f"Objetivo: {pct(route.percent)} del volumen<br/>{route.detail}<br/>{route.trigger}",
                accent=accent,
            )
        )
    grid = Table([[cards[0], cards[1]], [cards[2], cards[3]]], colWidths=[88 * mm, 88 * mm])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return grid


def infra_table() -> LongTable:
    rows = [[
        p("Componente", styles["TableHead"]),
        p("5.000 OCR/mes", styles["TableHead"]),
        p("10.000 OCR/mes", styles["TableHead"]),
        p("20.000 OCR/mes", styles["TableHead"]),
        p("Nota", styles["TableHead"]),
    ]]
    data = [
        ("VM API", "Integrada en una sola VM 4 vCPU / 8 GB", "Separada 2 vCPU / 4 GB", "Separada 2-4 vCPU / 4-8 GB", "La API no necesita ser enorme; lo pesado esta en OCR."),
        ("Worker OCR", "Misma VM", "4 vCPU / 8 GB", "4-8 vCPU / 8-16 GB", "Conviene separarlo apenas el volumen sube."),
        ("DB + Storage", "Supabase Pro", "Supabase Pro", "Supabase Pro", "El plan Pro es suficiente para esta fase."),
        ("Backups", "Basicos", "Basicos", "Obligatorios y revisados", "No hace falta una solucion enterprise todavia."),
        ("Redis / cola", "Opcional", "Recomendable", "Recomendable", "Puede esperar si empiezas con flujo simple."),
        ("GPU", "No", "No", "No", "No la necesitas para este plan OCR."),
        ("Kubernetes", "No", "No", "No", "Seria complejidad innecesaria."),
    ]
    for row in data:
        rows.append([p(row[0], styles["TableCell"]), p(row[1], styles["TableCell"]), p(row[2], styles["TableCell"]), p(row[3], styles["TableCell"]), p(row[4], styles["TableCell"]),])
    return make_table(rows, [30 * mm, 38 * mm, 38 * mm, 38 * mm, 34 * mm], row_highlights={3: PALETTE["soft_green"]})


def roadmap_table() -> LongTable:
    rows = [[
        p("Fase", styles["TableHead"]),
        p("Que construyes", styles["TableHead"]),
        p("Resultado esperado", styles["TableHead"]),
        p("Decision que habilita", styles["TableHead"]),
    ]]
    phases = [
        ("Fase 1", "API base + Supabase + healthchecks", "El sistema ya puede recibir, guardar y devolver OCR.", "Validar que ya puedes operar un MVP serio."),
        ("Fase 2", "Preprocesamiento + scoring de calidad", "Empiezas a medir cuando una imagen es buena, media o mala.", "Definir umbrales objetivos de escalado."),
        ("Fase 3", "RapidOCR + reglas por pais", "La mayoria de los documentos deberia resolverse en local.", "Medir cuanto volumen absorbe la ruta barata."),
        ("Fase 4", "Segundo intento local", "Reduces llamadas innecesarias a Azure.", "Comparar ahorro vs mejora de precision."),
        ("Fase 5", "Azure controlado", "Solo los casos dificiles escalan a premium.", "Medir costo variable real."),
        ("Fase 6", "Google como ultimo escalon", "Resuelves la cola mas dificil sin pagar siempre por Google.", "Definir el porcentaje maximo aceptable que llega al Nivel 4."),
        ("Fase 7", "Observabilidad y tuning", "Ajustas costo, precision y latencia con datos reales.", "Optimizar el costo por documento procesado."),
    ]
    for phase in phases:
        rows.append([p(phase[0], styles["TableCellCenter"]), p(phase[1], styles["TableCell"]), p(phase[2], styles["TableCell"]), p(phase[3], styles["TableCell"]),])
    return make_table(rows, [18 * mm, 48 * mm, 58 * mm, 54 * mm])


def on_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(PALETTE["line"])
    canvas.line(doc.leftMargin, A4[1] - 14 * mm, A4[0] - doc.rightMargin, A4[1] - 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(PALETTE["muted"])
    canvas.drawString(doc.leftMargin, A4[1] - 10 * mm, "Informe OCR Premium Deluxe")
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


def build_story(styles_dict: dict[str, ParagraphStyle]) -> list:
    global styles
    styles = styles_dict
    story: list = []

    story.append(hero_block())
    story.append(Spacer(1, 8))
    story.append(first_page_cards())
    story.append(Spacer(1, 8))
    story.append(
        info_box(
            "Decision rapida",
            [
                "Si vas a partir con 5.000 OCR/mes, compra Opcion 1 + Supabase Pro.",
                "Si apuntas a 10.000 o mas, la mejor compra es Opcion 2 + Supabase Pro.",
                "Google y Azure deben entrar solo cuando la evidencia lo exija; no como default.",
                "Lo que realmente define la factura es cuanto trafico llega a los niveles premium.",
            ],
            tone="green",
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("1. Lo que debes decidir ahora", styles["Title"]))
    story.append(
        Paragraph(
            "Este informe no intenta describir todo el sistema. Su objetivo es ayudarte a decidir que comprar y cuanto te costaria operar la app con OCR Premium Deluxe, sin extras como biometria o fraude avanzado.",
            styles["Body"],
        )
    )
    story.append(decision_matrix_table())
    story.append(Spacer(1, 8))
    story.append(
        bullets(
            [
                "Opcion 1 es la entrada mas barata, pero no es la mejor base para crecer mas alla de 5.000 OCR/mes.",
                "Opcion 2 es la recomendacion principal porque separa API y OCR, y por eso aguanta mejor crecimiento sin disparar costo.",
                "Opcion 3 no es la opcion base; solo tiene sentido cuando anticipas picos o mucha carga por PDF multipagina.",
                "Supabase Pro es suficiente para la fase actual; Free se queda corto y Team es demasiado para este alcance.",
            ],
            styles,
        )
    )

    story.append(Paragraph("2. Cuanto cuesta realmente la app", styles["Title"]))
    story.append(
        Paragraph(
            "La factura tiene dos bloques: costo fijo mensual e OCR variable. El fijo existe aunque no proceses nada. El variable crece con el volumen y sobre todo con el porcentaje de documentos que terminan usando Azure o Google.",
            styles["Body"],
        )
    )
    story.append(Paragraph("2.1 Costo fijo mensual", styles["Subtitle"]))
    story.append(fixed_cost_table())
    story.append(Spacer(1, 8))
    story.append(Paragraph("2.2 Costo variable OCR", styles["Subtitle"]))
    story.append(variable_cost_table())
    story.append(Spacer(1, 8))
    story.append(Paragraph("2.3 Sensibilidad del costo variable", styles["Subtitle"]))
    story.append(
        Paragraph(
            "La infraestructura no es la unica variable. Si tus fotos vienen peor de lo esperado, mas documentos escalan a Azure y Google, y ahi el costo variable sube rapido.",
            styles["Body"],
        )
    )
    story.append(sensitivity_table())
    story.append(Spacer(1, 8))
    story.append(Paragraph("2.4 Que pesa mas segun el volumen", styles["Subtitle"]))
    story.append(fixed_vs_variable_table())
    story.append(Spacer(1, 8))
    story.append(
        info_box(
            "Lectura de negocio",
            [
                "Con 5.000 OCR/mes pesa mas la infraestructura fija que el OCR variable.",
                "Con 20.000 OCR/mes el OCR variable ya pesa mas que la infraestructura fija.",
                "Por eso, al principio importa no sobredimensionar VMs. Despues importa aun mas controlar el porcentaje que escala a Azure y Google.",
            ],
            tone="blue",
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("3. Flujo OCR recomendado para cuidar costos", styles["Title"]))
    story.append(
        Paragraph(
            "La estrategia correcta no es usar lo mas potente siempre. El flujo ideal intenta resolver barato primero y escala solo cuando la calidad, la confianza o los campos criticos lo hacen necesario.",
            styles["Body"],
        )
    )
    story.append(route_cards())
    story.append(Spacer(1, 8))
    story.append(Paragraph("Reglas del router", styles["Subtitle"]))
    story.append(
        bullets(
            [
                "Si la imagen es buena y los campos criticos salen bien, se termina en OCR local.",
                "Si la imagen es media o falta un campo importante, se hace un segundo intento local antes de gastar en cloud.",
                "Azure entra cuando siguen faltando campos criticos o la calidad de captura ya es claramente insuficiente.",
                "Google debe ser el ultimo escalon y tocar muy poco volumen.",
                "OpenAI, biometria, ABBYY y Regula quedan fuera de esta fase para proteger el costo unitario.",
            ],
            styles,
        )
    )
    story.append(
        info_box(
            "Meta operativa",
            [
                "Objetivo minimo: mantener al menos 70% del volumen en la ruta local.",
                "Objetivo deseable: que Azure no supere 12-15% del volumen y que Google no pase de 3-5%.",
                "Si esas proporciones empeoran, el costo por documento deja de ser tan competitivo.",
            ],
            tone="amber",
        )
    )

    story.append(Paragraph("4. Infraestructura recomendada", styles["Title"]))
    story.append(
        Paragraph(
            "Para esta fase, la arquitectura puede mantenerse deliberadamente simple: Google VM + Supabase Pro. No necesitas GPU, Kubernetes ni un stack enterprise mas caro.",
            styles["Body"],
        )
    )
    story.append(infra_table())
    story.append(Spacer(1, 8))
    story.append(
        info_box(
            "Que no compraria todavia",
            [
                "Supabase Team o Enterprise.",
                "GPU dedicada para OCR.",
                "Kubernetes o una plataforma distribuida compleja.",
                "ABBYY, Regula o biometria mientras el foco siga siendo OCR rentable.",
            ],
            tone="blue",
        )
    )

    story.append(Paragraph("5. Plan de implementacion", styles["Title"]))
    story.append(
        Paragraph(
            "La implementacion debe seguir el mismo principio del costo: construir primero lo que mas impacto tiene en precision y control de gasto. No tiene sentido montar Google antes de exprimir RapidOCR, reglas y segundo intento local.",
            styles["Body"],
        )
    )
    story.append(roadmap_table())
    story.append(Spacer(1, 8))
    story.append(Paragraph("Metricas que debes seguir desde el dia uno", styles["Subtitle"]))
    story.append(
        bullets(
            [
                "% de documentos resueltos en Nivel 1.",
                "% que escalan a Azure.",
                "% que escalan a Google.",
                "Costo variable medio por documento.",
                "Tiempo medio por documento.",
                "Tasa de reproceso.",
                "Exactitud por tipo documental y pais.",
            ],
            styles,
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("6. Supuestos, limites y notas importantes", styles["Title"]))
    story.append(
        bullets(
            [
                "Los costos usan tus cotizaciones reales de VM y Supabase Pro, mas el modelo variable OCR definido durante el analisis.",
                "No se incluyen logging, supervision ni snapshots de GCP porque en la cotizacion original aparecen como variables.",
                "Tampoco se incluyen sobrecostos por exceso de storage o egress en Supabase, impuestos ni licencias externas fuera del alcance OCR Premium Deluxe.",
                "Si la calidad real de las capturas es peor que la supuesta, el costo variable OCR sube por mayor uso de Azure y Google.",
                "Si el trafico llega en picos fuertes, la eleccion puede moverse de Opcion 2 a Opcion 3 aunque el costo puro mensual sea mayor.",
            ],
            styles,
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        info_box(
            "Cierre ejecutivo",
            [
                "La compra mas razonable hoy es Google VM + Supabase Pro.",
                "Para 5.000 OCR/mes conviene Opcion 1. Para 10.000 y 20.000 OCR/mes conviene Opcion 2, salvo que esperes picos fuertes.",
                "La mejor forma de proteger el margen no es recortar infraestructura, sino lograr que la mayoria de los documentos se resuelva en local y que Google sea una ruta muy rara.",
            ],
            tone="green",
        )
    )

    return story


def build_pdf() -> Path:
    styles_dict = build_styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
        title="Informe OCR Premium Deluxe",
        author="OpenCode",
        subject="Costos, infraestructura y decisiones para OCR Premium Deluxe",
    )
    story = build_story(styles_dict)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    print(path)
