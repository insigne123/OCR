from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.document_classifier import DocumentClassification
from app.services.layout_extraction import LayoutExtractionResult
from app.services.ocr_ensemble import VisualOCREnsembleResult, VisualOCRRunRecord
from app.services.page_preprocessing import OCRVariantSet, PreprocessedPage
from app.services.processing_pipeline import _run_visual_ocr_with_rescue
from app.services.visual_ocr import OCRToken, VisualOCRResult


def _classification(document_family: str = "identity", country: str = "CL", supported: bool = True) -> DocumentClassification:
    return DocumentClassification(
        document_family=document_family,
        country=country,
        variant=None,
        pack_id=None,
        pack_version=None,
        document_side=None,
        confidence=0.94,
        reasons=["synthetic"],
        supported=supported,
    )


def _token(text: str, confidence: float = 0.9) -> OCRToken:
    return OCRToken(text=text, confidence=confidence, bbox=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], page_number=1)


def _run(profile: str, engine: str, score: float, average_confidence: float, text: str = "REPUBLICA DE CHILE RUN 12.345.678-5") -> VisualOCRRunRecord:
    result = VisualOCRResult(
        text=text,
        page_count=1,
        source=engine,
        assumptions=[f"run:{engine}:{profile}"],
        tokens=[_token(text.split()[0], average_confidence)],
        page_texts=[text],
    )
    return VisualOCRRunRecord(
        engine_name=engine,
        source=engine,
        preprocess_profile=profile,
        page_profiles=[profile],
        success=True,
        result=result,
        average_confidence=average_confidence,
        classification=_classification(),
        layout=LayoutExtractionResult(engine=engine, lines=[], key_value_pairs=[], table_candidate_rows=[]),
        score=score,
        error=None,
    )


def _variant(profile: str, average_quality: float = 0.58) -> OCRVariantSet:
    return OCRVariantSet(
        profile=profile,
        images=[profile.encode("utf-8")],
        page_count=1,
        average_quality=average_quality,
        assumptions=[f"variant:{profile}"],
        page_profiles=[profile],
    )


def _page(quality_score: float = 0.58) -> PreprocessedPage:
    return PreprocessedPage(
        page_number=1,
        image_bytes=b"page",
        width=1200,
        height=800,
        orientation=0,
        quality_score=quality_score,
        blur_score=0.34,
        glare_score=0.18,
        has_embedded_text=False,
        capture_conditions=["low_quality", "blur"],
        rescue_profiles=["clahe", "aggressive_rescue"],
        variant_images={"original": b"page", "aggressive_rescue": b"rescue"},
        page_profile_map={"original": "original", "aggressive_rescue": "aggressive_rescue"},
    )


class ProcessingPipelineRescueTests(unittest.TestCase):
    def test_tries_rescue_local_before_single_premium_escalation(self) -> None:
        variants = [_variant("original", average_quality=0.58), _variant("aggressive_rescue", average_quality=0.58)]
        local_original = VisualOCREnsembleResult(mode="single", runs=[_run("original", "rapidocr", 0.41, 0.64)], selected_run=_run("original", "rapidocr", 0.41, 0.64), assumptions=[])
        local_rescue = VisualOCREnsembleResult(mode="single", runs=[_run("aggressive_rescue", "rapidocr", 0.69, 0.79)], selected_run=_run("aggressive_rescue", "rapidocr", 0.69, 0.79), assumptions=[])
        premium_rescue = VisualOCREnsembleResult(mode="single", runs=[_run("aggressive_rescue", "google-documentai", 0.92, 0.96)], selected_run=_run("aggressive_rescue", "google-documentai", 0.92, 0.96), assumptions=[])

        with patch("app.services.processing_pipeline._should_use_rescue_profiles", return_value=True), patch(
            "app.services.processing_pipeline.build_ocr_variant_sets", return_value=variants
        ), patch("app.services.processing_pipeline.resolve_visual_ocr_engine_names", return_value=("ensemble", ["rapidocr", "google-documentai"])), patch(
            "app.services.processing_pipeline.run_visual_ocr_ensemble",
            side_effect=[local_original, local_rescue, premium_rescue],
        ) as runner:
            result = _run_visual_ocr_with_rescue(
                prepared_pages=[_page()],
                rendered_pages=[b"page"],
                requested_engine="auto",
                requested_family="identity",
                requested_country="CL",
                ensemble_mode="always",
                ensemble_engines="rapidocr,google-documentai",
            )

        self.assertEqual(runner.call_count, 3)
        third_call = runner.call_args_list[2]
        self.assertEqual(third_call.kwargs["preprocess_profile"], "aggressive_rescue")
        self.assertEqual(result.selected_run.source, "google-documentai")
        self.assertTrue(any("mejor perfil local" in assumption for assumption in result.assumptions))

    def test_skips_premium_when_second_local_variant_becomes_acceptable(self) -> None:
        variants = [_variant("original", average_quality=0.74), _variant("clahe", average_quality=0.74)]
        local_original = VisualOCREnsembleResult(mode="single", runs=[_run("original", "rapidocr", 0.51, 0.7)], selected_run=_run("original", "rapidocr", 0.51, 0.7), assumptions=[])
        local_clahe = VisualOCREnsembleResult(mode="single", runs=[_run("clahe", "rapidocr", 0.74, 0.84)], selected_run=_run("clahe", "rapidocr", 0.74, 0.84), assumptions=[])

        with patch("app.services.processing_pipeline._should_use_rescue_profiles", return_value=True), patch(
            "app.services.processing_pipeline.build_ocr_variant_sets", return_value=variants
        ), patch("app.services.processing_pipeline.resolve_visual_ocr_engine_names", return_value=("ensemble", ["rapidocr", "google-documentai"])), patch(
            "app.services.processing_pipeline.run_visual_ocr_ensemble",
            side_effect=[local_original, local_clahe],
        ) as runner:
            result = _run_visual_ocr_with_rescue(
                prepared_pages=[_page(quality_score=0.74)],
                rendered_pages=[b"page"],
                requested_engine="auto",
                requested_family="identity",
                requested_country="CL",
                ensemble_mode="always",
                ensemble_engines="rapidocr,google-documentai",
            )

        self.assertEqual(runner.call_count, 2)
        self.assertEqual(result.selected_run.preprocess_profile, "clahe")
        self.assertTrue(any("OCR local fue suficiente" in assumption for assumption in result.assumptions))


if __name__ == "__main__":
    unittest.main()
