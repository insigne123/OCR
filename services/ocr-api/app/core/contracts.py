from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas import NormalizedDocument
from app.services.visual_ocr import VisualOCRResult


@dataclass(frozen=True)
class NormalizationRequest:
    document_family: str
    country: str
    filename: str
    variant: str | None = None
    pack_id: str | None = None
    document_side: str | None = None
    assumptions: list[str] | None = None


class VisualOCREngine(Protocol):
    name: str

    def run(self, images: list[bytes]) -> VisualOCRResult | None:
        ...


class NormalizerEngine(Protocol):
    name: str

    def normalize_text(self, request: NormalizationRequest, source_text: str) -> NormalizedDocument:
        ...

    def normalize_image(self, request: NormalizationRequest, mime_type: str, file_bytes: bytes) -> NormalizedDocument:
        ...

    def normalize_rendered_pages(self, request: NormalizationRequest, images: list[bytes]) -> NormalizedDocument:
        ...
