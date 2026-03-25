from __future__ import annotations

from app.core.contracts import VisualOCREngine
from app.services.visual_ocr import VisualOCRResult, run_visual_ocr


class RapidVisualOCREngine(VisualOCREngine):
    name = "rapidocr-local"

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        return run_visual_ocr(images)


class CompositeVisualOCREngine(VisualOCREngine):
    name = "composite-visual-ocr"

    def __init__(self, engines: list[VisualOCREngine]):
        self.engines = engines

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        for engine in self.engines:
            try:
                result = engine.run(images)
            except Exception:
                result = None
            if result and result.text:
                return result
        return None
