from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path

from app.core.contracts import VisualOCREngine
from app.services.visual_ocr import OCRToken, VisualOCRResult


def _bbox_from_quad(points: list[list[float]]) -> list[list[float]]:
    if len(points) == 4:
        return [[float(point[0]), float(point[1])] for point in points]

    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]


class PaddleVisualOCREngine(VisualOCREngine):
    name = "paddleocr-local"

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        if not images:
            return None

        try:
            from paddleocr import PaddleOCR
        except Exception:
            return None

        engine = PaddleOCR(use_angle_cls=True, lang="en")
        page_texts: list[str] = []
        tokens: list[OCRToken] = []

        with TemporaryDirectory(prefix="ocr-paddle-") as tmpdir:
            for index, image_bytes in enumerate(images, start=1):
                image_path = Path(tmpdir) / f"page-{index}.png"
                image_path.write_bytes(image_bytes)
                result = engine.ocr(str(image_path), cls=True)
                snippets: list[str] = []

                for line in result or []:
                    for entry in line or []:
                        if not entry or len(entry) < 2:
                            continue
                        bbox = _bbox_from_quad(entry[0])
                        text = (entry[1][0] or "").strip() if entry[1] else ""
                        confidence = float(entry[1][1]) if entry[1] and len(entry[1]) > 1 else 0.0
                        if not text:
                            continue
                        snippets.append(text)
                        tokens.append(OCRToken(text=text, confidence=confidence, bbox=bbox, page_number=index))

                page_texts.append("\n".join(snippets))

        full_text = "\n\n".join(text for text in page_texts if text).strip()
        if not full_text:
            return None

        return VisualOCRResult(
            text=full_text,
            page_count=len(images),
            source=self.name,
            assumptions=["Se aplico OCR visual local con PaddleOCR."],
            tokens=tokens,
            page_texts=page_texts,
        )
