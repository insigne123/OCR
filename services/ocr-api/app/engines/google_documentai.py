from __future__ import annotations

import os

from app.core.contracts import VisualOCREngine
from app.services.visual_ocr import OCRToken, VisualOCRResult


def has_google_documentai_config() -> bool:
    return bool(
        os.getenv("GOOGLE_DOCUMENTAI_PROJECT_ID")
        and os.getenv("GOOGLE_DOCUMENTAI_LOCATION")
        and os.getenv("GOOGLE_DOCUMENTAI_PROCESSOR_ID")
    )


class GoogleDocumentAIOCREngine(VisualOCREngine):
    name = "google-documentai"

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        if not images or not has_google_documentai_config():
            return None

        try:
            from google.api_core.client_options import ClientOptions
            from google.cloud import documentai
        except Exception:
            return None

        project_id = os.getenv("GOOGLE_DOCUMENTAI_PROJECT_ID", "")
        location = os.getenv("GOOGLE_DOCUMENTAI_LOCATION", "")
        processor_id = os.getenv("GOOGLE_DOCUMENTAI_PROCESSOR_ID", "")
        client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
        )
        processor_name = client.processor_path(project_id, location, processor_id)

        tokens: list[OCRToken] = []
        page_texts: list[str] = []

        for page_number, image in enumerate(images, start=1):
            try:
                request = documentai.ProcessRequest(
                    name=processor_name,
                    raw_document=documentai.RawDocument(content=image, mime_type="image/png"),
                )
                result = client.process_document(request=request)
            except Exception:
                page_texts.append("")
                continue

            document = result.document
            snippets: list[str] = []
            for page in getattr(document, "pages", []) or []:
                for token in getattr(page, "tokens", []) or []:
                    text_anchor = getattr(token.layout, "text_anchor", None)
                    if not text_anchor or not getattr(text_anchor, "text_segments", None):
                        continue
                    start_index = int(getattr(text_anchor.text_segments[0], "start_index", 0) or 0)
                    end_index = int(getattr(text_anchor.text_segments[0], "end_index", 0) or 0)
                    content = (document.text[start_index:end_index] or "").strip()
                    if not content:
                        continue
                    vertices = getattr(getattr(token.layout, "bounding_poly", None), "normalized_vertices", None) or []
                    bbox = [[float(vertex.x), float(vertex.y)] for vertex in vertices]
                    if len(bbox) >= 4:
                        snippets.append(content)
                        tokens.append(
                            OCRToken(
                                text=content,
                                confidence=float(getattr(token.layout, "confidence", 0.0) or 0.0),
                                bbox=bbox[:4],
                                page_number=page_number,
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
            assumptions=["Se aplico OCR con Google Document AI."],
            tokens=tokens,
            page_texts=page_texts,
        )
