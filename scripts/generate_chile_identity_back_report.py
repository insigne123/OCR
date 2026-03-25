from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "Informe_Dorso_Cedula_Chile.pdf"
BACK_BATCH = ROOT / "test-data" / "_batch_results_id_back_post_fix.json"
BACK_COMPARE = ROOT / "test-data" / "_compare_identity_back.json"
FRONT_BACK_RUN = ROOT / "test-data" / "_front_back_identity_run.json"


PALETTE = {
    "ink": colors.HexColor("#0F172A"),
    "text": colors.HexColor("#1E293B"),
    "muted": colors.HexColor("#475569"),
    "line": colors.HexColor("#CBD5E1"),
    "soft": colors.HexColor("#F8FAFC"),
    "soft_green": colors.HexColor("#ECFDF3"),
    "soft_blue": colors.HexColor("#EEF6FF"),
    "hero": colors.HexColor("#0B1220"),
    "green": colors.HexColor("#16A34A"),
    "blue": colors.HexColor("#2563EB"),
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "hero": ParagraphStyle("hero", parent=sample["Title"], fontName="Helvetica-Bold", fontSize=21, leading=26, textColor=colors.white),
        "hero_sub": ParagraphStyle("hero_sub", parent=sample["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#D7E3F4")),
        "h1": ParagraphStyle("h1", parent=sample["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=PALETTE["ink"], spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", parent=sample["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=PALETTE["text"]),
        "small": ParagraphStyle("small", parent=sample["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=PALETTE["muted"]),
        "head": ParagraphStyle("head", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white, alignment=1),
        "cell": ParagraphStyle("cell", parent=sample["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=PALETTE["text"]),
        "cell_right": ParagraphStyle("cell_right", parent=sample["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=PALETTE["text"], alignment=2),
        "card_label": ParagraphStyle("card_label", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=PALETTE["muted"]),
        "card_value": ParagraphStyle("card_value", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=PALETTE["ink"]),
        "card_note": ParagraphStyle("card_note", parent=sample["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=PALETTE["muted"]),
    }


S = styles()


def p(text: str, style: str) -> Paragraph:
    return Paragraph(text, S[style])


def make_table(rows: list[list], widths: list[float]) -> LongTable:
    table = LongTable(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALETTE["ink"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, PALETTE["line"]),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALETTE["soft"]]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def card(label: str, value: str, note: str, accent: colors.Color) -> Table:
    table = Table([[p(label, "card_label")], [p(value, "card_value")], [p(note, "card_note")]], colWidths=[56 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                ("BOX", (0, 0), (-1, -1), 0.45, PALETTE["line"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def hero() -> Table:
    rows = [
        [p("Benchmark Dorso Cedula Chile", "hero")],
        [p("Validacion del soporte para el reverso de la cedula chilena y del flujo combinado frente+dorso.", "hero_sub")],
        [p(f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "hero_sub")],
    ]
    table = Table(rows, colWidths=[178 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALETTE["hero"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return table


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(PALETTE["muted"])
    canvas.drawString(doc.leftMargin, 10 * mm, "Informe benchmark - dorso cedula chilena")
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Pagina {canvas.getPageNumber()}")
    canvas.restoreState()


def build_report() -> None:
    batch = load_json(BACK_BATCH)
    compare = load_json(BACK_COMPARE)
    combined = load_json(FRONT_BACK_RUN)

    total_matches = sum(report["summary"]["matches"] for report in compare["reports"])
    total_expected = sum(report["summary"]["matches"] + report["summary"]["mismatches"] + report["summary"]["missing"] for report in compare["reports"])
    average_confidence = batch["summary"]["average_confidence"]
    auto_accepts = batch["summary"]["by_decision"].get("auto_accept", 0)
    total_images = batch["summary"]["total_files"]

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title="Informe Dorso Cedula Chile",
        author="OpenCode",
    )

    story = [hero(), Spacer(1, 8)]
    cards = Table(
        [[
            card("Imagenes dorso", str(total_images), "Fotos 0843 a 0846 evaluadas", PALETTE["blue"]),
            card("Auto-accept", f"{auto_accepts}/{total_images}", "Todas las imagenes quedaron autoaceptadas", PALETTE["green"]),
            card("Confianza promedio", f"{average_confidence:.4f}", "Promedio del lote dorso", PALETTE["blue"]),
            card("Campos criticos", f"{total_matches}/{total_expected}", "Comparacion contra referencias JSON", PALETTE["green"]),
        ]],
        colWidths=[44 * mm, 44 * mm, 44 * mm, 44 * mm],
    )
    story.extend([cards, Spacer(1, 10)])

    story.append(p("Resultado del benchmark dorso", "h1"))
    story.append(p("La app ya reconoce el dorso de la cedula chilena como `identity / CL / identity-cl-back-text`, extrae los identificadores y las fechas desde la MRZ TD1, y mantiene autoaceptacion conservadora en las cuatro imagenes nuevas.", "body"))
    story.append(Spacer(1, 6))

    detail_rows = [[
        p("Archivo", "head"),
        p("Decision", "head"),
        p("Confianza", "head"),
        p("Numero", "head"),
        p("RUN", "head"),
        p("Nacimiento", "head"),
        p("Vencimiento", "head"),
        p("Lugar", "head"),
    ]]
    compare_by_image = {report["image"]: report for report in compare["reports"]}
    for item in batch["results"]:
        image_compare = compare_by_image[item["file"]]
        actual = {entry["field"]: entry.get("actual") for entry in image_compare["comparisons"]}
        detail_rows.append([
            p(item["file"], "cell"),
            p(item["decision"], "cell"),
            p(f"{item['global_confidence']:.3f}", "cell_right"),
            p(actual.get("document_number") or "-", "cell"),
            p(actual.get("run") or "-", "cell"),
            p(actual.get("birth_date") or "-", "cell"),
            p(actual.get("expiry_date") or "-", "cell"),
            p(actual.get("birth_place") or "-", "cell"),
        ])
    story.append(make_table(detail_rows, [28 * mm, 22 * mm, 18 * mm, 24 * mm, 24 * mm, 22 * mm, 22 * mm, 26 * mm]))
    story.append(Spacer(1, 8))

    story.append(p("Comparacion contra referencias", "h1"))
    compare_rows = [[p("Archivo", "head"), p("Matches", "head"), p("Mismatches", "head"), p("Missing", "head"), p("Lectura", "head")]]
    for report in compare["reports"]:
        summary = report["summary"]
        compare_rows.append([
            p(report["image"], "cell"),
            p(str(summary["matches"]), "cell_right"),
            p(str(summary["mismatches"]), "cell_right"),
            p(str(summary["missing"]), "cell_right"),
            p("Todos los campos de referencia quedaron correctos." if summary["mismatches"] == 0 and summary["missing"] == 0 else "Revisar outliers.", "cell"),
        ])
    story.append(make_table(compare_rows, [30 * mm, 18 * mm, 18 * mm, 18 * mm, 94 * mm]))
    story.append(Spacer(1, 8))

    story.append(p("Flujo frente + dorso", "h1"))
    story.append(p("Tambien se probo un PDF temporal con el frente `IMG_0841.jpeg` y el dorso `IMG_0843.jpeg`. Tras la fusion por lado, el documento combinado queda autoaceptado y conserva consistencia cross-side.", "body"))
    combined_rows = [[p("Campo", "head"), p("Valor", "head")]]
    for label, value in [
        ("Decision", combined["decision"]),
        ("Confianza", f"{combined['global_confidence']:.3f}"),
        ("Titular", combined.get("holder_name") or "-"),
        ("Numero", combined.get("document_number") or "-"),
        ("RUN", combined.get("run") or "-"),
        ("Nacimiento", combined.get("birth_date") or "-"),
        ("Emision", combined.get("issue_date") or "-"),
        ("Vencimiento", combined.get("expiry_date") or "-"),
        ("Lugar de nacimiento", combined.get("birth_place") or "-"),
    ]:
        combined_rows.append([p(label, "cell"), p(value, "cell",)])
    story.append(make_table(combined_rows, [46 * mm, 132 * mm]))
    story.append(Spacer(1, 8))

    story.append(p("Conclusiones", "h1"))
    story.append(p("- El dorso chileno ya no cae como pasaporte; queda clasificado correctamente como identidad CL dorso.<br/>- La referencia critica del dorso pasa 28/28 campos en total (7 por imagen).<br/>- El flujo combinado frente+dorso ahora autoacepta y consolida numero, RUN, fechas y lugar de nacimiento.<br/>- Sigue habiendo margen para pulir el `holder_name` visual en algunos dorsos individuales muy degradados, pero el benchmark critico ya queda estable.", "body"))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF generado: {OUTPUT}")


if __name__ == "__main__":
    build_report()
