from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from app.core.contracts import VisualOCREngine
from app.services.visual_ocr import OCRToken, VisualOCRResult


class DocTRVisualOCREngine(VisualOCREngine):
    name = "doctr-local"

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        if not images:
            return None

        try:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor
        except Exception:
            return None

        with TemporaryDirectory(prefix="ocr-doctr-") as tmpdir:
            image_paths: list[str] = []
            page_sizes: list[tuple[int, int]] = []
            for index, image_bytes in enumerate(images, start=1):
                image_path = Path(tmpdir) / f"page-{index}.png"
                image_path.write_bytes(image_bytes)
                image_paths.append(str(image_path))
                document = fitz.open(stream=image_bytes, filetype="png")
                try:
                    page = document.load_page(0)
                    pix = page.get_pixmap(alpha=False)
                    page_sizes.append((pix.width, pix.height))
                finally:
                    document.close()

            predictor = ocr_predictor(pretrained=True)
            doc = DocumentFile.from_images(image_paths)
            result = predictor(doc)

        page_texts: list[str] = []
        tokens: list[OCRToken] = []

        for index, page in enumerate(result.pages, start=1):
            snippets: list[str] = []
            width, height = page_sizes[index - 1] if index - 1 < len(page_sizes) else (1, 1)
            for block in page.blocks:
                for line in block.lines:
                    for word in line.words:
                        text = (word.value or "").strip()
                        if not text:
                            continue
                        geom = word.geometry
                        bbox = [
                            [float(geom[0][0] * width), float(geom[0][1] * height)],
                            [float(geom[1][0] * width), float(geom[0][1] * height)],
                            [float(geom[1][0] * width), float(geom[1][1] * height)],
                            [float(geom[0][0] * width), float(geom[1][1] * height)],
                        ]
                        snippets.append(text)
                        tokens.append(
                            OCRToken(
                                text=text,
                                confidence=float(getattr(word, "confidence", 0.0) or 0.0),
                                bbox=bbox,
                                page_number=index,
                            )
                        )
            page_texts.append(" ".join(snippets).strip())

        full_text = "\n\n".join(text for text in page_texts if text).strip()
        if not full_text:
            return None

        return VisualOCRResult(
            text=full_text,
            page_count=len(images),
            source=self.name,
            assumptions=["Se aplico OCR visual local con docTR."],
            tokens=tokens,
            page_texts=page_texts,
        )
