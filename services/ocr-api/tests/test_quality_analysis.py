from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.page_preprocessing import PreprocessedPage
from app.services.quality_analysis import build_quality_assessment


class QualityAnalysisTests(unittest.TestCase):
    def test_builds_capture_recommendations_from_page_quality(self) -> None:
        page = PreprocessedPage(
            page_number=1,
            image_bytes=b"page",
            width=1200,
            height=800,
            orientation=0,
            quality_score=0.44,
            blur_score=0.36,
            glare_score=0.28,
            has_embedded_text=False,
            crop_ratio=0.82,
            document_coverage=0.71,
            capture_conditions=["low_quality", "glare"],
        )

        assessment = build_quality_assessment([page])

        self.assertLess(assessment.score, 0.5)
        self.assertIn("low_quality", assessment.capture_conditions)
        self.assertTrue(any("reflejos" in recommendation.lower() or "encuadre" in recommendation.lower() for recommendation in assessment.recommendations))


if __name__ == "__main__":
    unittest.main()
