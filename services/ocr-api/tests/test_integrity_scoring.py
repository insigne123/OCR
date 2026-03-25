from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas import ReportSection
from app.services.cross_side_consistency import CrossSideConsistencySignal
from app.services.document_packs import resolve_document_pack
from app.services.integrity_scoring import build_integrity_assessment
from app.services.page_preprocessing import PreprocessedPage
from app.services.rule_packs import FieldDecisionSignal


class IntegrityScoringTests(unittest.TestCase):
    def test_detects_cross_side_mismatch_and_low_quality(self) -> None:
        pack = resolve_document_pack(pack_id="identity-cl-front")
        assessment = build_integrity_assessment(
            report_sections=[
                ReportSection(id="summary", title="Resumen", variant="pairs", rows=[["RUN", "12.345.678-5"]]),
            ],
            pack=pack,
            prepared_pages=[
                PreprocessedPage(
                    page_number=1,
                    image_bytes=b"page",
                    width=1200,
                    height=800,
                    orientation=0,
                    quality_score=0.42,
                    blur_score=0.31,
                    glare_score=0.16,
                    has_embedded_text=False,
                )
            ],
            field_signals={"run": FieldDecisionSignal(agreement_ratio=0.52, disagreement=True, candidate_count=2, supporting_engines=("rapidocr",))},
            cross_side_signal=CrossSideConsistencySignal(
                front_present=True,
                back_present=True,
                front_identifier="123456785",
                back_identifier="223456785",
                identifier_match=False,
                assumptions=["mismatch"],
            ),
        )

        self.assertEqual(assessment.risk_level, "high")
        self.assertTrue(any(indicator.code == "cross_side_mismatch" for indicator in assessment.indicators))


if __name__ == "__main__":
    unittest.main()
