from __future__ import annotations

from io import BytesIO
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.image_capture_hardening import build_capture_rescue_plan
from app.services.page_preprocessing import build_ocr_variant_sets, prepare_document_pages


class MobileCaptureHardeningTests(unittest.TestCase):
    def test_capture_plan_generates_rescue_profiles(self) -> None:
        image = Image.new("RGB", (1200, 900), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((120, 140, 1080, 760), radius=30, fill=(235, 240, 252), outline=(40, 60, 80), width=6)
        draw.rectangle((620, 180, 1040, 340), fill=(255, 255, 255))
        plan = build_capture_rescue_plan(image, quality_hint=0.7, blur_hint=0.3, glare_hint=0.4)

        self.assertGreater(plan.edge_confidence, 0.0)
        self.assertIn("deglare", plan.rescue_profiles)
        self.assertIn("shadow_boost", plan.variant_images)
        self.assertIn("clahe", plan.variant_images)
        self.assertIn("adaptive_binarize", plan.variant_images)
        self.assertIn("denoise_sharpen", plan.variant_images)

    def test_capture_plan_adds_aggressive_rescue_for_extreme_low_quality(self) -> None:
        image = Image.new("RGB", (1200, 900), (248, 248, 248))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((140, 110, 1085, 785), radius=22, fill=(232, 232, 232), outline=(90, 90, 90), width=4)
        draw.text((200, 240), "CERTIFICADO AFP", fill=(120, 120, 120))
        plan = build_capture_rescue_plan(image, quality_hint=0.52, blur_hint=0.41, glare_hint=0.29)

        self.assertIn("extreme_low_quality", plan.capture_conditions)
        self.assertIn("aggressive_rescue", plan.rescue_profiles)
        self.assertIn("aggressive_rescue", plan.variant_images)

    def test_prepare_document_pages_preserves_variant_images(self) -> None:
        image = Image.new("RGB", (1000, 650), (250, 250, 250))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((80, 70, 920, 580), radius=18, fill=(240, 245, 234), outline=(55, 60, 70), width=4)
        draw.text((140, 180), "REPUBLICA DE CHILE", fill=(20, 20, 20))
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        pages = prepare_document_pages(buffer.getvalue(), "synthetic.png", "image/png")
        self.assertEqual(len(pages), 1)
        self.assertIn("original", pages[0].variant_images)
        variants = build_ocr_variant_sets(pages)
        self.assertTrue(any(variant.profile == "original" for variant in variants))


if __name__ == "__main__":
    unittest.main()
