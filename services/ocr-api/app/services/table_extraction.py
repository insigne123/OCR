from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
import re

from app.schemas import ReportSection, TableCell, TableExtractionResponse, TableExtractionResult
from app.services.layout_extraction import LayoutExtractionResult

WHITESPACE_COLUMNS = re.compile(r"\s{2,}")


@dataclass(frozen=True)
class ExtractedTablesPayload:
    tables: list[TableExtractionResult]
    assumptions: list[str]


def _table_from_section(section: ReportSection, index: int) -> TableExtractionResult:
    headers = section.columns or []
    rows = section.rows or []
    cells = [
        TableCell(row_index=row_index, column_index=column_index, value=value)
        for row_index, row in enumerate(rows)
        for column_index, value in enumerate(row)
    ]
    confidence = 0.93 if rows and len(headers) >= 2 else 0.81 if rows else 0.58
    return TableExtractionResult(
        table_id=f"section-{index}-{section.id}",
        title=section.title,
        headers=headers,
        rows=rows,
        cells=cells,
        confidence=round(confidence, 3),
        source="normalized-report",
        format_hint="json",
    )


def _layout_row_to_cells(row: str) -> list[str]:
    cells = [cell.strip() for cell in WHITESPACE_COLUMNS.split(row.strip()) if cell.strip()]
    if len(cells) >= 2:
        return cells
    fallback = [cell.strip() for cell in row.split("|") if cell.strip()]
    if len(fallback) >= 2:
        return fallback
    return [row.strip()]


def _table_from_layout(layout: LayoutExtractionResult) -> TableExtractionResult | None:
    if not layout.table_candidate_rows:
        return None

    rows = [_layout_row_to_cells(row) for row in layout.table_candidate_rows[:25]]
    max_columns = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (max_columns - len(row)) for row in rows]
    headers = [f"column_{index + 1}" for index in range(max_columns)]
    cells = [
        TableCell(row_index=row_index, column_index=column_index, value=value)
        for row_index, row in enumerate(normalized_rows)
        for column_index, value in enumerate(row)
    ]
    return TableExtractionResult(
        table_id="layout-table-candidates",
        title="Layout table candidates",
        headers=headers,
        rows=normalized_rows,
        cells=cells,
        confidence=0.64 if max_columns > 1 else 0.51,
        source=layout.engine,
        format_hint="layout-candidates",
    )


def extract_tables_payload(report_sections: list[ReportSection], layout: LayoutExtractionResult) -> ExtractedTablesPayload:
    tables = [
        _table_from_section(section, index)
        for index, section in enumerate(report_sections, start=1)
        if section.variant == "table" and not section.id.startswith("debug-") and not section.id.startswith("layout-")
    ]
    assumptions: list[str] = []

    layout_table = _table_from_layout(layout)
    if not tables and layout_table is not None:
        tables.append(layout_table)
        assumptions.append("No habia tablas canonicas del pack; se devolvieron filas candidatas detectadas por layout.")
    elif tables and layout_table is not None:
        assumptions.append("Se privilegiaron tablas canonicas del pack sobre filas candidatas genericas del layout.")

    if tables:
        assumptions.append(f"Se extrajeron {len(tables)} tabla(s) estructurada(s).")
    else:
        assumptions.append("No se detectaron tablas estructurables con la evidencia actual.")

    return ExtractedTablesPayload(tables=tables, assumptions=assumptions)


def render_tables_csv(tables: list[TableExtractionResult]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)

    for index, table in enumerate(tables, start=1):
        writer.writerow([table.title])
        if table.headers:
            writer.writerow(table.headers)
        for row in table.rows:
            writer.writerow(row)
        if index < len(tables):
            writer.writerow([])

    return buffer.getvalue().strip()


def build_table_extraction_response(
    *,
    document_family: str,
    country: str,
    variant: str | None,
    pack_id: str | None,
    report_sections: list[ReportSection],
    layout: LayoutExtractionResult,
    output_format: str = "json",
) -> TableExtractionResponse:
    payload = extract_tables_payload(report_sections, layout)
    return TableExtractionResponse(
        document_family=document_family,
        country=country,
        variant=variant,
        pack_id=pack_id,
        tables=payload.tables,
        csv=render_tables_csv(payload.tables) if output_format == "csv" and payload.tables else None,
        assumptions=payload.assumptions,
    )
