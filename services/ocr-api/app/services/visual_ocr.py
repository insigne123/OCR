from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass
class OCRToken:
    text: str
    confidence: float
    bbox: list[list[float]]
    page_number: int


@dataclass
class VisualOCRResult:
    text: str
    page_count: int
    source: str
    assumptions: list[str]
    tokens: list[OCRToken]
    page_texts: list[str]


@lru_cache(maxsize=1)
def _get_rapidocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _run_rapidocr(images: list[bytes]) -> VisualOCRResult | None:
    try:
        engine = _get_rapidocr_engine()
    except Exception:
        return None

    page_texts: list[str] = []
    tokens: list[OCRToken] = []

    for page_number, image in enumerate(images, start=1):
        result, _ = engine(image)
        if not result:
            continue

        snippets = [entry[1].strip() for entry in result if len(entry) > 1 and isinstance(entry[1], str) and entry[1].strip()]
        for entry in result:
            if len(entry) < 3 or not isinstance(entry[1], str) or not entry[1].strip():
                continue
            tokens.append(
                OCRToken(
                    text=entry[1].strip(),
                    confidence=float(entry[2]),
                    bbox=[[float(point[0]), float(point[1])] for point in entry[0]],
                    page_number=page_number,
                )
            )
        if snippets:
            page_texts.append("\n".join(snippets))
        else:
            page_texts.append("")

    text = "\n\n".join(page_texts).strip()

    if not text:
        return None

    return VisualOCRResult(
        text=text,
        page_count=len(images),
        source="rapidocr-local",
        assumptions=[
            "Se aplico OCR visual local con RapidOCR sobre imagenes renderizadas del documento.",
        ],
        tokens=tokens,
        page_texts=page_texts,
    )


def run_visual_ocr(images: list[bytes]) -> VisualOCRResult | None:
    if not images:
        return None

    return _run_rapidocr(images)


def warm_visual_ocr_runtime() -> None:
    try:
        _get_rapidocr_engine()
    except Exception:
        return
