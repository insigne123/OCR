from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import ReportSection
from app.services.layout_extraction import LayoutExtractionResult, LayoutLine
from app.services.table_extraction import build_table_extraction_response


class TableExtractionTests(unittest.TestCase):
    def test_prefers_structured_report_tables(self) -> None:
        response = build_table_extraction_response(
            document_family="certificate",
            country="CL",
            variant="certificate-cl-previsional",
            pack_id="certificate-cl-previsional",
            report_sections=[
                ReportSection(
                    id="movements",
                    title="Movimientos",
                    variant="table",
                    columns=["Periodo", "Monto"],
                    rows=[["2025-01", "12000"]],
                )
            ],
            layout=LayoutExtractionResult(engine="layout", lines=[LayoutLine(page_number=1, text="2025-01 12000", bbox=None)], key_value_pairs=[], table_candidate_rows=["2025-01 12000"]),
            output_format="csv",
        )

        self.assertEqual(len(response.tables), 1)
        self.assertEqual(response.tables[0].headers, ["Periodo", "Monto"])
        self.assertIn("Movimientos", response.csv)


if __name__ == "__main__":
    unittest.main()
