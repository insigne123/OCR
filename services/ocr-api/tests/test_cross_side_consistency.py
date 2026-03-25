from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.cross_side_consistency import _extract_identifiers, build_cross_side_consistency_signal
from app.services.document_classifier import DocumentClassification
from app.services.page_analysis import PageAnalysisResult, PageClassificationResult


def _classification(side: str) -> DocumentClassification:
    return DocumentClassification(
        document_family="identity",
        country="CL",
        variant="identity-cl-front-text" if side == "front" else "identity-cl-back-text",
        pack_id="identity-cl-front" if side == "front" else "identity-cl-back",
        pack_version="2026-03",
        document_side=side,
        confidence=0.95,
        reasons=["synthetic"],
        supported=True,
    )


class CrossSideConsistencyTests(unittest.TestCase):
    def test_extract_identifier_canonicalizes_chile_run(self) -> None:
        front_text = "RUN 12.345.678-5\nNOMBRE JUAN PEREZ"
        back_text = "RUT 12345678-5\nDOMICILIO SANTIAGO"

        self.assertIn("12345678-5", _extract_identifiers(front_text, "CL"))
        self.assertIn("12345678-5", _extract_identifiers(back_text, "CL"))

    def test_extract_identifier_normalizes_peruvian_dni(self) -> None:
        text = "DOCUMENTO NACIONAL DE IDENTIDAD\nDNI 1234 5678"
        self.assertIn("12345678", _extract_identifiers(text, "PE"))

    def test_cross_side_signal_matches_td1_back_against_front_identifier(self) -> None:
        front_text = "REPUBLICA DE CHILE\nRUN 21.952.550-8\nNUMERO DOCUMENTO B64.872.150\nNOMBRES NICOLAS"
        back_text = "550<8<9\nYARUR<GONGORA<<NICOLAS<FAELLES\nINCHLB648721500S13<\n0510132M3510133CHL2\nNacio en.\n438584\nNACICAN"
        page_analysis = PageAnalysisResult(
            pages=[
                PageClassificationResult(page_number=1, classification=_classification("front")),
                PageClassificationResult(page_number=2, classification=_classification("back")),
            ],
            dominant=_classification("front"),
            document_side="front+back",
            cross_side_detected=True,
            assumptions=[],
        )

        signal = build_cross_side_consistency_signal(page_analysis, [front_text, back_text], "CL")

        self.assertIsNotNone(signal)
        self.assertTrue(signal.identifier_match)
        self.assertEqual(signal.front_identifier, "B64872150")
        self.assertEqual(signal.back_identifier, "B64872150")


if __name__ == "__main__":
    unittest.main()
