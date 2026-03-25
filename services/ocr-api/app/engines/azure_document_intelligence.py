from __future__ import annotations

from io import BytesIO
import os

from app.core.contracts import VisualOCREngine
from app.services.visual_ocr import OCRToken, VisualOCRResult


def has_azure_document_intelligence_config() -> bool:
    return bool(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") and os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY"))


def _polygon_to_bbox(polygon) -> list[list[float]]:
    if not polygon:
        return []

    if all(isinstance(value, (int, float)) for value in polygon):
        pairs = list(zip(polygon[::2], polygon[1::2]))
        return [[float(x), float(y)] for x, y in pairs[:4]]

    bbox = []
    for point in polygon:
        if hasattr(point, "x"):
            bbox.append([float(point.x), float(point.y)])
        else:
            bbox.append([float(point[0]), float(point[1])])
    return bbox[:4]


class AzureDocumentIntelligenceOCREngine(VisualOCREngine):
    name = "azure-document-intelligence"

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        if not images or not has_azure_document_intelligence_config():
            return None

        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except Exception:
            return None

        endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
        key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
        model_id = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_MODEL", "prebuilt-read")
        client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

        tokens: list[OCRToken] = []
        page_texts: list[str] = []

        for page_number, image in enumerate(images, start=1):
            try:
                poller = client.begin_analyze_document(model_id, body=BytesIO(image))
                result = poller.result()
            except Exception:
                page_texts.append("")
                continue

            snippets: list[str] = []
            for page in getattr(result, "pages", []) or []:
                words = getattr(page, "words", []) or []
                for word in words:
                    content = (getattr(word, "content", "") or "").strip()
                    if not content:
                        continue
                    polygon = getattr(getattr(word, "polygon", None), "points", None) or getattr(word, "polygon", None) or []
                    bbox = _polygon_to_bbox(polygon)
                    if len(bbox) >= 4:
                        snippets.append(content)
                        tokens.append(
                            OCRToken(
                                text=content,
                                confidence=float(getattr(word, "confidence", 0.0) or 0.0),
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
            assumptions=["Se aplico OCR con Azure Document Intelligence."],
            tokens=tokens,
            page_texts=page_texts,
        )
