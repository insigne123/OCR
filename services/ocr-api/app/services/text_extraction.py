from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


@dataclass
class TextExtractionResult:
    text: str
    page_count: int
    source: str
    assumptions: list[str]
    page_texts: list[str]


def extract_document_text(file_bytes: bytes, filename: str, content_type: str | None) -> TextExtractionResult:
    suffix = Path(filename).suffix.lower()
    mime_type = (content_type or "").lower()

    if suffix == ".pdf" or mime_type == "application/pdf":
        reader = PdfReader(BytesIO(file_bytes))
        page_text: list[str] = []

        for page in reader.pages:
            extracted = (page.extract_text() or "").strip()
            page_text.append(extracted)

        text = "\n\n".join(extracted for extracted in page_text if extracted).strip()
        assumptions = ["Se intento extraer texto embebido desde el PDF."]

        if text:
            assumptions.append("El documento contiene texto embebido utilizable para normalizacion.")
            source = "pdf-embedded-text"
        else:
            assumptions.append("No se detecto texto embebido; el documento podria requerir OCR visual adicional.")
            source = "pdf-no-text"

        return TextExtractionResult(text=text, page_count=len(reader.pages), source=source, assumptions=assumptions, page_texts=page_text)

    if mime_type.startswith("text/") or suffix in {".txt", ".csv"}:
        text = file_bytes.decode("utf-8", errors="ignore").strip()
        page_texts = [segment.strip() for segment in text.split("\f") if segment.strip()] or [text]
        return TextExtractionResult(
            text=text,
            page_count=len(page_texts),
            source="plain-text",
            assumptions=["El archivo se trato como texto plano para extraer contenido estructurable."],
            page_texts=page_texts,
        )

    return TextExtractionResult(
        text="",
        page_count=1,
        source="binary-no-text",
        assumptions=["El archivo no aporta texto utilizable sin OCR visual o interpretacion multimodal."],
        page_texts=[],
    )
