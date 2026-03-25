from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.custom_extraction import extract_custom_fields
from app.services.document_classifier import DocumentClassification
from app.services.layout_extraction import LayoutExtractionResult, LayoutKeyValue, LayoutLine


class CustomExtractionTests(unittest.TestCase):
    def test_matches_schema_fields_against_layout_pairs(self) -> None:
        classification = DocumentClassification(
            document_family="invoice",
            country="CL",
            variant=None,
            pack_id=None,
            pack_version=None,
            document_side=None,
            confidence=0.81,
            reasons=["invoice wording"],
            supported=False,
        )
        layout = LayoutExtractionResult(
            engine="layout",
            lines=[LayoutLine(page_number=1, text="TOTAL: 15.990", bbox=None)],
            key_value_pairs=[LayoutKeyValue(label="TOTAL", value="15.990", page_number=1, raw_line="TOTAL: 15.990")],
            table_candidate_rows=[],
        )

        fields = extract_custom_fields(
            schema={"total_amount": {"type": "number", "description": "Monto total con IVA"}},
            source_text="TOTAL: 15.990",
            layout=layout,
            classification=classification,
        )

        self.assertEqual(fields[0].field_name, "total_amount")
        self.assertEqual(fields[0].value, "15.990")
        self.assertGreater(fields[0].confidence, 0.7)


if __name__ == "__main__":
    unittest.main()
