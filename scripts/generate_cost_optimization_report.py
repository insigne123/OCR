from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Informe_OCR_Costos_Comparativos.pdf"

SUPABASE_PRO_COST = Decimal("25.00")
UNIT_COSTS = (Decimal("0.0015"), Decimal("0.0040"), Decimal("0.0465"), Decimal("0.0965"))
CURRENT_ROUTE_SHARES = (Decimal("0.70"), Decimal("0.15"), Decimal("0.12"), Decimal("0.03"))
PROPOSED_ROUTE_SHARES = (Decimal("0.75"), Decimal("0.15"), Decimal("0.09"), Decimal("0.01"))
VOLUMES = (5000, 10000, 20000)


PALETTE = {
    "ink": colors.HexColor("#0F172A"),
    "text": colors.HexColor("#1E293B"),
    "muted": colors.HexColor("#475569"),
    "line": colors.HexColor("#CBD5E1"),
    "soft": colors.HexColor("#F8FAFC"),
    "soft_blue": colors.HexColor("#EEF6FF"),
    "soft_green": colors.HexColor("#ECFDF3"),
    "soft_amber": colors.HexColor("#FFF7ED"),
    "soft_red": colors.HexColor("#FEF2F2"),
    "hero": colors.HexColor("#0B1220"),
    "blue": colors.HexColor("#2563EB"),
    "green": colors.HexColor("#16A34A"),
    "amber": colors.HexColor("#D97706"),
    "red": colors.HexColor("#DC2626"),
}


@dataclass(frozen=True)
class VmOption:
    name: str
    vm_total: Decimal
    description: str


@dataclass(frozen=True)
class ScheduleOption:
    name: str
    factor: Decimal
    note: str
    risk: str


VM_OPTIONS = {
    "Opcion 1": VmOption("Opcion 1", Decimal("98.40"), "1 VM 4 vCPU / 8 GB / 80 GB SSD"),
    "Opcion 2": VmOption("Opcion 2", Decimal("147.60"), "VM API 2 vCPU / 4 GB + VM OCR 4 vCPU / 8 GB"),
    "Opcion 3": VmOption("Opcion 3", Decimal("234.10"), "VM API 2 vCPU / 4 GB + VM OCR 8 vCPU / 16 GB"),
}

CURRENT_OPTION_BY_VOLUME = {
    5000: "Opcion 1",
    10000: "Opcion 2",
    20000: "Opcion 2",
}

SCHEDULES = (
    ScheduleOption("24/7 x 30 dias", Decimal("1.0"), "Base actual del informe previo.", "Bajo"),
    ScheduleOption("24/7 x 22 dias", Decimal("22") / Decimal("30"), "Ahorro por apagar el stack 8 dias completos al mes.", "Medio"),
    ScheduleOption("8 am a 11 pm x 30 dias", Decimal("15") / Decimal("24"), "Operacion diaria con ventana de 15 horas.", "Medio"),
    ScheduleOption(
        "8 am a 11 pm x 22 dias",
        (Decimal("22") / Decimal("30")) * (Decimal("15") / Decimal("24")),
        "Escenario mas agresivo: menos horas y menos dias activos.",
        "Alto",
    ),
)


def money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"USD {rounded:,.2f}"


def per_doc(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f"USD {rounded:,.4f}"


def volume_label(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def pct(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"


def avg_variable_cost(shares: tuple[Decimal, Decimal, Decimal, Decimal]) -> Decimal:
    total = sum((share * unit for share, unit in zip(shares, UNIT_COSTS, strict=True)), Decimal("0"))
    return total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


CURRENT_VARIABLE_PER_DOC = avg_variable_cost(CURRENT_ROUTE_SHARES)
PROPOSED_VARIABLE_PER_DOC = avg_variable_cost(PROPOSED_ROUTE_SHARES)


def variable_cost(volume: int, shares: tuple[Decimal, Decimal, Decimal, Decimal]) -> Decimal:
    return (avg_variable_cost(shares) * Decimal(str(volume))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fixed_cost(option_name: str, schedule: ScheduleOption) -> Decimal:
    return (VM_OPTIONS[option_name].vm_total * schedule.factor + SUPABASE_PRO_COST).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def current_total(volume: int) -> Decimal:
    option_name = CURRENT_OPTION_BY_VOLUME[volume]
    return (fixed_cost(option_name, SCHEDULES[0]) + variable_cost(volume, CURRENT_ROUTE_SHARES)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def proposed_total(volume: int, schedule: ScheduleOption) -> Decimal:
    option_name = CURRENT_OPTION_BY_VOLUME[volume]
    return (fixed_cost(option_name, schedule) + variable_cost(volume, PROPOSED_ROUTE_SHARES)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def savings_against_current(volume: int, schedule: ScheduleOption) -> Decimal:
    return (current_total(volume) - proposed_total(volume, schedule)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def docs_per_active_hour(volume: int, schedule: ScheduleOption) -> Decimal:
    monthly_hours = schedule.factor * Decimal("30") * Decimal("24")
    return (Decimal(str(volume)) / monthly_hours).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
    styles["HeroSub"] = ParagraphStyle(
        "HeroSub",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=10,
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
        fontSize=9.2,
        leading=13,
        textColor=PALETTE["text"],
        spaceAfter=5,
    )
    styles["Small"] = ParagraphStyle(
        "Small",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=8.1,
        leading=10,
        textColor=PALETTE["muted"],
        spaceAfter=3,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet",
        parent=sample["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        leftIndent=12,
        textColor=PALETTE["text"],
        spaceAfter=2,
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
        fontSize=8.1,
        leading=10,
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
    return styles


styles = build_styles()


def p(text: str, style_name: str) -> Paragraph:
    return Paragraph(text, styles[style_name])


def bullets(lines: list[str]) -> ListFlowable:
    return ListFlowable([p(line, "Bullet") for line in lines], bulletType="bullet", leftIndent=14)


def make_table(rows: list[list], col_widths: list[float], *, row_highlights: dict[int, colors.Color] | None = None) -> LongTable:
    table = LongTable(rows, colWidths=col_widths, repeatRows=1)
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


def card(label: str, value: str, note: str, accent: colors.Color) -> Table:
    rows = [[p(label, "CardLabel")], [p(value, "CardValue")], [p(note, "CardNote")]]
    table = Table(rows, colWidths=[56 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                ("BOX", (0, 0), (-1, -1), 0.5, PALETTE["line"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def info_box(title: str, lines: list[str], tone: str) -> Table:
    tone_map = {
        "blue": (PALETTE["soft_blue"], PALETTE["blue"]),
        "green": (PALETTE["soft_green"], PALETTE["green"]),
        "amber": (PALETTE["soft_amber"], PALETTE["amber"]),
        "red": (PALETTE["soft_red"], PALETTE["red"]),
    }
    background, accent = tone_map[tone]
    body = [p(title, "Subtitle")]
    for line in lines:
        body.append(p(f"- {line}", "Body"))
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


def hero() -> Table:
    rows = [
        [p("OCR Cost Optimization", "Kicker")],
        [p("Informe comparativo de costos actuales vs costos potenciales", "HeroTitle")],
        [
            p(
                "Documento pensado para impresion. Cruza los costos actuales del proyecto con una propuesta conservadora de ahorro que prioriza calidad OCR, confianza y continuidad operativa.",
                "HeroSub",
            )
        ],
        [p(f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "HeroSub")],
    ]
    table = Table(rows, colWidths=[178 * mm])
    table.setStyle(
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
    return table


def top_cards() -> Table:
    routing_saving_10k = savings_against_current(10000, SCHEDULES[0])
    best_case_20k = savings_against_current(20000, SCHEDULES[3])
    cards = [
        card("Costo variable actual", per_doc(CURRENT_VARIABLE_PER_DOC), "Mix base 70% / 15% / 12% / 3%", PALETTE["amber"]),
        card("Costo variable propuesto", per_doc(PROPOSED_VARIABLE_PER_DOC), "Mix conservador 75% / 15% / 9% / 1%", PALETTE["green"]),
        card("Ahorro a 10.000/mes", money(routing_saving_10k), "Solo por mejorar routing, sin apagar servidores", PALETTE["blue"]),
        card("Ahorro maximo modelado", money(best_case_20k), "20.000/mes con horario 8 a 23, 22 dias", PALETTE["red"]),
    ]
    table = Table([cards], colWidths=[44 * mm, 44 * mm, 44 * mm, 44 * mm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def assumptions_table() -> LongTable:
    rows = [[p("Elemento", "TableHead"), p("Costo o criterio", "TableHead"), p("Fuente del modelo", "TableHead")]]
    rows.extend(
        [
            [p("Supabase Pro", "TableCell"), p(money(SUPABASE_PRO_COST), "TableCellRight"), p("Costo fijo mensual asumido", "TableCell")],
            [p("Opcion 1", "TableCell"), p(money(VM_OPTIONS['Opcion 1'].vm_total), "TableCellRight"), p("1 VM 4 vCPU / 8 GB / 80 GB SSD", "TableCell")],
            [p("Opcion 2", "TableCell"), p(money(VM_OPTIONS['Opcion 2'].vm_total), "TableCellRight"), p("VM API + VM OCR", "TableCell")],
            [p("Variable actual / doc", "TableCell"), p(per_doc(CURRENT_VARIABLE_PER_DOC), "TableCellRight"), p("Mix 70% / 15% / 12% / 3%", "TableCell")],
            [p("Variable propuesto / doc", "TableCell"), p(per_doc(PROPOSED_VARIABLE_PER_DOC), "TableCellRight"), p("Mix 75% / 15% / 9% / 1%", "TableCell")],
        ]
    )
    return make_table(rows, [42 * mm, 32 * mm, 104 * mm], row_highlights={5: PALETTE["soft_green"]})


def routing_comparison_table() -> LongTable:
    rows = [[
        p("Volumen", "TableHead"),
        p("Costo actual", "TableHead"),
        p("Propuesta 24/7 x 30 dias", "TableHead"),
        p("Ahorro", "TableHead"),
        p("Lectura", "TableHead"),
    ]]
    notes = {
        5000: "Ahorro chico pero seguro. No toca disponibilidad ni calidad.",
        10000: "Punto medio interesante: reduce variable sin cambiar infraestructura base.",
        20000: "A esta escala el routing importa mas que la VM adicional.",
    }
    for volume in VOLUMES:
        current = current_total(volume)
        proposed = proposed_total(volume, SCHEDULES[0])
        saving = savings_against_current(volume, SCHEDULES[0])
        rows.append([
            p(volume_label(volume), "TableCellCenter"),
            p(money(current), "TableCellRight"),
            p(money(proposed), "TableCellRight"),
            p(money(saving), "TableCellRight"),
            p(notes[volume], "TableCell"),
        ])
    return make_table(rows, [24 * mm, 28 * mm, 38 * mm, 25 * mm, 63 * mm], row_highlights={2: PALETTE["soft_blue"]})


def schedule_fixed_table() -> LongTable:
    rows = [[
        p("Horario", "TableHead"),
        p("Factor VM", "TableHead"),
        p("Fijo O1", "TableHead"),
        p("Fijo O2", "TableHead"),
        p("Riesgo", "TableHead"),
        p("Lectura", "TableHead"),
    ]]
    for schedule in SCHEDULES:
        rows.append([
            p(schedule.name, "TableCell"),
            p(pct(schedule.factor), "TableCellCenter"),
            p(money(fixed_cost("Opcion 1", schedule)), "TableCellRight"),
            p(money(fixed_cost("Opcion 2", schedule)), "TableCellRight"),
            p(schedule.risk, "TableCellCenter"),
            p(schedule.note, "TableCell"),
        ])
    return make_table(rows, [42 * mm, 21 * mm, 24 * mm, 24 * mm, 18 * mm, 50 * mm], row_highlights={4: PALETTE["soft_red"]})


def total_cross_table() -> LongTable:
    rows = [[
        p("Volumen", "TableHead"),
        p("Actual", "TableHead"),
        p("24/7 x 30 dias", "TableHead"),
        p("24/7 x 22 dias", "TableHead"),
        p("8 a 23 x 30 dias", "TableHead"),
        p("8 a 23 x 22 dias", "TableHead"),
    ]]
    for volume in VOLUMES:
        rows.append([
            p(volume_label(volume), "TableCellCenter"),
            p(f"{money(current_total(volume))}<br/><font size='7'>Base previa</font>", "TableCellRight"),
            p(f"{money(proposed_total(volume, SCHEDULES[0]))}<br/><font size='7'>-{money(savings_against_current(volume, SCHEDULES[0]))}</font>", "TableCellRight"),
            p(f"{money(proposed_total(volume, SCHEDULES[1]))}<br/><font size='7'>-{money(savings_against_current(volume, SCHEDULES[1]))}</font>", "TableCellRight"),
            p(f"{money(proposed_total(volume, SCHEDULES[2]))}<br/><font size='7'>-{money(savings_against_current(volume, SCHEDULES[2]))}</font>", "TableCellRight"),
            p(f"{money(proposed_total(volume, SCHEDULES[3]))}<br/><font size='7'>-{money(savings_against_current(volume, SCHEDULES[3]))}</font>", "TableCellRight"),
        ])
    return make_table(rows, [20 * mm, 28 * mm, 31 * mm, 31 * mm, 31 * mm, 31 * mm], row_highlights={3: PALETTE["soft_green"]})


def throughput_table() -> LongTable:
    rows = [[
        p("Volumen", "TableHead"),
        p("24/7 x 30 dias", "TableHead"),
        p("24/7 x 22 dias", "TableHead"),
        p("8 a 23 x 30 dias", "TableHead"),
        p("8 a 23 x 22 dias", "TableHead"),
    ]]
    for volume in VOLUMES:
        rows.append([
            p(volume_label(volume), "TableCellCenter"),
            p(str(docs_per_active_hour(volume, SCHEDULES[0])), "TableCellRight"),
            p(str(docs_per_active_hour(volume, SCHEDULES[1])), "TableCellRight"),
            p(str(docs_per_active_hour(volume, SCHEDULES[2])), "TableCellRight"),
            p(str(docs_per_active_hour(volume, SCHEDULES[3])), "TableCellRight"),
        ])
    return make_table(rows, [24 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm], row_highlights={3: PALETTE["soft_red"]})


def risks_table() -> LongTable:
    rows = [[
        p("Configuracion", "TableHead"),
        p("Que se pierde o arriesga", "TableHead"),
        p("Riesgo", "TableHead"),
    ]]
    items = [
        (
            "Solo routing mejorado",
            "No se pierde disponibilidad. El riesgo real es calibrar mal el routing y mandar demasiados casos a rutas premium o demasiado pocos a premium.",
            "Bajo",
        ),
        (
            "24/7 x 22 dias",
            "8 dias al mes sin servicio si se apaga todo el stack. Si solo se apaga OCR, se conserva intake pero se acumula cola.",
            "Medio",
        ),
        (
            "8 am a 11 pm x 30 dias",
            "No hay procesamiento nocturno. Puede haber backlog matinal y perdida de SLA overnight.",
            "Medio",
        ),
        (
            "8 am a 11 pm x 22 dias",
            "Es el mayor ahorro, pero combina cierre nocturno y 8 dias completos apagado. Exige mucha disciplina operativa y clientes compatibles con cola.",
            "Alto",
        ),
        (
            "Apagar web y OCR a la vez",
            "Se pierde upload, API publica, dashboards y estado durante la ventana apagada. Es la opcion mas delicada operativamente.",
            "Alto",
        ),
    ]
    for config_name, risk_text, level in items:
        rows.append([p(config_name, "TableCell"), p(risk_text, "TableCell"), p(level, "TableCellCenter")])
    return make_table(rows, [34 * mm, 118 * mm, 18 * mm], row_highlights={5: PALETTE["soft_red"]})


def recommendation_table() -> LongTable:
    rows = [[
        p("Volumen", "TableHead"),
        p("Configuracion recomendada", "TableHead"),
        p("Motivo", "TableHead"),
    ]]
    rows.extend(
        [
            [
                p("5.000/mes", "TableCellCenter"),
                p("Routing mejorado + 24/7", "TableCell"),
                p("Es el ahorro mas limpio: baja costo sin tocar disponibilidad ni tensionar la operacion.", "TableCell"),
            ],
            [
                p("10.000/mes", "TableCellCenter"),
                p("Routing mejorado + 8 a 23 todos los dias", "TableCell"),
                p("Es el mejor equilibrio si el negocio acepta cola nocturna y la calidad sigue siendo la prioridad maxima.", "TableCell"),
            ],
            [
                p("20.000/mes", "TableCellCenter"),
                p("Routing mejorado + Opcion 2 base", "TableCell"),
                p("A esta escala conviene no recortar demasiado la ventana operativa. El ahorro grande ya viene del routing, no de apagar servidores.", "TableCell"),
            ],
        ]
    )
    return make_table(rows, [25 * mm, 50 * mm, 103 * mm], row_highlights={2: PALETTE["soft_blue"]})


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(PALETTE["muted"])
    canvas.drawString(doc.leftMargin, 10 * mm, "Informe OCR - costos actuales vs optimizados")
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Pagina {canvas.getPageNumber()}")
    canvas.restoreState()


def build_report() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="Informe OCR Costos Comparativos",
        author="OpenCode",
    )

    story = [hero(), Spacer(1, 8), top_cards(), Spacer(1, 10)]
    story.append(
        info_box(
            "Como leer este informe",
            [
                "Los costos actuales salen del modelo previo del repo: 5.000 con Opcion 1; 10.000 y 20.000 con Opcion 2.",
                "La propuesta conserva calidad OCR y asume mejora por routing, no por recortar validaciones criticas.",
                "Los escenarios de horario reducen solo VMs; Supabase y costo variable OCR siguen activos en el modelo.",
                "Si en la practica se mantiene la web 24/7 y solo se programa OCR, el ahorro real quedara entre el caso 24/7 y el caso de apagado total modelado aqui.",
            ],
            "blue",
        )
    )
    story.append(Spacer(1, 8))
    story.append(p("Supuestos del modelo", "Title"))
    story.append(assumptions_table())
    story.append(Spacer(1, 8))
    story.append(p("Comparacion segura: solo mejorando routing", "Title"))
    story.append(routing_comparison_table())
    story.append(Spacer(1, 8))
    story.append(
        info_box(
            "Lectura ejecutiva",
            [
                "El costo variable actual promedio es USD 0.010125 por documento.",
                "La propuesta conservadora lo baja a USD 0.006875 por documento.",
                "Eso equivale a una reduccion de 32.1% en el componente variable sin bajar el nivel de proteccion del pipeline.",
            ],
            "green",
        )
    )
    story.append(Spacer(1, 8))
    story.append(p("Costo fijo bajo distintas ventanas horarias", "Title"))
    story.append(schedule_fixed_table())
    story.append(Spacer(1, 8))
    story.append(p("Costos mensuales cruzados", "Title"))
    story.append(total_cross_table())
    story.append(Spacer(1, 8))
    story.append(p("Carga operativa requerida", "Title"))
    story.append(p("La siguiente tabla muestra cuantos OCR promedio por hora activa deberia absorber la operacion en cada ventana. Cuanto mas alto el numero, mas sensible sera el sistema a picos y backlog.", "Body"))
    story.append(throughput_table())
    story.append(Spacer(1, 8))
    story.append(p("Que se pierde o arriesga", "Title"))
    story.append(risks_table())
    story.append(Spacer(1, 8))
    story.append(
        info_box(
            "Regla operativa recomendada",
            [
                "Si el objetivo es ahorrar sin afectar experiencia del cliente, es preferible programar el worker OCR y mantener la capa web/API arriba con cola.",
                "Apagar web y OCR al mismo tiempo maximiza ahorro, pero tambien maximiza friccion comercial y riesgo de SLA.",
                "Por eso, el modelo horario debe verse como techo de ahorro posible, no como recomendacion obligatoria de arquitectura.",
            ],
            "amber",
        )
    )
    story.append(Spacer(1, 8))
    story.append(p("Recomendacion final", "Title"))
    story.append(recommendation_table())
    story.append(Spacer(1, 8))
    story.append(
        bullets(
            [
                "5.000/mes: mejor mover primero routing y retencion antes de tocar horario.",
                "10.000/mes: la palanca con mejor equilibrio es routing mejorado mas operacion 8 a 23 si el negocio tolera cola nocturna.",
                "20.000/mes: no conviene recortar demasiado la infraestructura base; el ahorro principal ya sale de premium routing mejor controlado.",
            ]
        )
    )

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build_report()
    print(f"PDF generado: {OUTPUT}")
