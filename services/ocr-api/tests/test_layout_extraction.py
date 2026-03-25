from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.layout_extraction import extract_layout_from_page_texts


class LayoutExtractionTests(unittest.TestCase):
    def test_extracts_key_values_and_table_candidates(self) -> None:
        result = extract_layout_from_page_texts(
            [
                "RUT: 12.345.678-5\n"
                "CUENTA: 1008-0760-0100199653\n"
                "2025-08 2025-08-31 2,536,386 COTIZACION OBLIGATORIA"
            ]
        )

        labels = {pair.label for pair in result.key_value_pairs}
        self.assertIn("RUT", labels)
        self.assertIn("CUENTA", labels)
        self.assertTrue(any("2025-08" in row for row in result.table_candidate_rows))


if __name__ == "__main__":
    unittest.main()
