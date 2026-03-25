from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.ocr_ensemble import run_visual_ocr_ensemble
from app.services.visual_ocr import OCRToken, VisualOCRResult


class _FakeEngine:
    def __init__(self, result: VisualOCRResult | None):
        self._result = result

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        return self._result


def _result(source: str, text: str, confidence: float) -> VisualOCRResult:
    return VisualOCRResult(
        text=text,
        page_count=1,
        source=source,
        assumptions=[f"run:{source}"],
        tokens=[
            OCRToken(
                text=text.split()[0],
                confidence=confidence,
                bbox=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
                page_number=1,
            )
        ],
        page_texts=[text],
    )


class OcrEnsembleTests(unittest.TestCase):
    def test_selects_best_supported_engine_from_ensemble(self) -> None:
        engines = {
            "rapidocr": _FakeEngine(_result("rapidocr-local", "documento borroso", 0.4)),
            "google-documentai": _FakeEngine(
                _result("google-documentai", "REPUBLICA DE CHILE CEDULA DE IDENTIDAD RUN 12.345.678-5", 0.97)
            ),
            "azure-document-intelligence": _FakeEngine(
                _result("azure-document-intelligence", "CERTIFICADO DE TRABAJO REPUBLICA DEL PERU DNI 12345678", 0.88)
            ),
        }

        with patch("app.services.ocr_ensemble.resolve_visual_ocr_engine_names", return_value=("ensemble", list(engines.keys()))), patch(
            "app.services.ocr_ensemble.get_visual_ocr_engine", side_effect=lambda name: engines[name]
        ):
            result = run_visual_ocr_ensemble([b"page"], requested_engine="auto", requested_family="auto", requested_country="AUTO")

        self.assertEqual(result.mode, "ensemble")
        self.assertEqual(len(result.runs), 3)
        self.assertIsNotNone(result.selected_run)
        self.assertEqual(result.selected_run.source, "google-documentai")
        self.assertTrue(any("OCR ensemble ejecutado" in assumption for assumption in result.assumptions))

    def test_keeps_single_mode_when_only_one_engine_is_requested(self) -> None:
        with patch("app.services.ocr_ensemble.resolve_visual_ocr_engine_names", return_value=("single", ["rapidocr"])), patch(
            "app.services.ocr_ensemble.get_visual_ocr_engine",
            return_value=_FakeEngine(_result("rapidocr-local", "REPUBLICA DEL PERU DOCUMENTO NACIONAL DE IDENTIDAD 12345678", 0.9)),
        ):
            result = run_visual_ocr_ensemble([b"page"], requested_engine="rapidocr", requested_family="identity", requested_country="PE")

        self.assertEqual(result.mode, "single")
        self.assertEqual(len(result.runs), 1)
        self.assertEqual(result.selected_run.source, "rapidocr-local")
        self.assertTrue(result.selected_run.classification.supported)


if __name__ == "__main__":
    unittest.main()
