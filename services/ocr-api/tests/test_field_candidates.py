from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import LayoutKeyValueCandidate, OCRRunInfo, OCRRunPageInfo, OCRTokenInfo
from app.services.processing_pipeline import _build_field_candidates


class FieldCandidateTests(unittest.TestCase):
    def test_builds_candidates_and_detects_disagreement(self) -> None:
        runs = [
            OCRRunInfo(
                engine="google-documentai",
                source="google-documentai",
                success=True,
                selected=True,
                score=0.98,
                page_count=1,
                text="RUN 12.345.678-5",
                average_confidence=0.98,
                classification_family="identity",
                classification_country="CL",
                classification_confidence=0.95,
                supported_classification=True,
                assumptions=[],
                pages=[OCRRunPageInfo(page_number=1, text="RUN 12.345.678-5", token_count=2, average_confidence=0.98)],
                tokens=[OCRTokenInfo(text="12.345.678-5", confidence=0.98, bbox=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], page_number=1)],
                key_value_pairs=[LayoutKeyValueCandidate(label="RUN", value="12.345.678-5", page_number=1, raw_line="RUN: 12.345.678-5")],
                table_candidate_rows=[],
            ),
            OCRRunInfo(
                engine="azure-document-intelligence",
                source="azure-document-intelligence",
                success=True,
                selected=False,
                score=0.87,
                page_count=1,
                text="RUN 12.345.678-K",
                average_confidence=0.84,
                classification_family="identity",
                classification_country="CL",
                classification_confidence=0.92,
                supported_classification=True,
                assumptions=[],
                pages=[OCRRunPageInfo(page_number=1, text="RUN 12.345.678-K", token_count=2, average_confidence=0.84)],
                tokens=[OCRTokenInfo(text="12.345.678-K", confidence=0.84, bbox=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], page_number=1)],
                key_value_pairs=[LayoutKeyValueCandidate(label="RUN", value="12.345.678-K", page_number=1, raw_line="RUN: 12.345.678-K")],
                table_candidate_rows=[],
            ),
        ]

        candidates, consensus = _build_field_candidates("RUN", "run", "12.345.678-5", runs)

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0].source, "google-documentai")
        self.assertTrue(candidates[0].selected)
        self.assertIsNotNone(consensus)
        assert consensus is not None
        self.assertEqual(consensus.engines_considered, 2)
        self.assertGreaterEqual(consensus.candidate_count, 2)
        self.assertFalse(consensus.disagreement)
        self.assertAlmostEqual(consensus.agreement_ratio, 0.5)


if __name__ == "__main__":
    unittest.main()
