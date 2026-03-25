from __future__ import annotations

from app.core.contracts import NormalizationRequest, NormalizerEngine
from app.schemas import NormalizedDocument
from app.services.heuristic_normalizer import normalize_text_with_heuristics
from app.services.openai_normalizer import (
    normalize_image_with_openai,
    normalize_rendered_pages_with_openai,
    normalize_text_with_openai,
)
class HeuristicNormalizerEngine(NormalizerEngine):
    name = "heuristic"

    def normalize_text(self, request: NormalizationRequest, source_text: str) -> NormalizedDocument:
        return normalize_text_with_heuristics(
            request.document_family,
            request.country,
            request.filename,
            source_text,
            request.assumptions or [],
            variant=request.variant,
            pack_id=request.pack_id,
            document_side=request.document_side,
        )

    def normalize_image(self, request: NormalizationRequest, mime_type: str, file_bytes: bytes) -> NormalizedDocument:
        raise NotImplementedError("Heuristic normalizer does not support direct image normalization.")

    def normalize_rendered_pages(self, request: NormalizationRequest, images: list[bytes]) -> NormalizedDocument:
        raise NotImplementedError("Heuristic normalizer does not support rendered-page normalization.")


class OpenAINormalizerEngine(NormalizerEngine):
    name = "openai-structured"

    def normalize_text(self, request: NormalizationRequest, source_text: str) -> NormalizedDocument:
        return normalize_text_with_openai(
            request.document_family,
            request.country,
            request.filename,
            source_text,
            request.variant,
            request.pack_id,
            request.document_side,
        )

    def normalize_image(self, request: NormalizationRequest, mime_type: str, file_bytes: bytes) -> NormalizedDocument:
        return normalize_image_with_openai(
            request.document_family,
            request.country,
            request.filename,
            mime_type,
            file_bytes,
            request.variant,
            request.pack_id,
            request.document_side,
        )

    def normalize_rendered_pages(self, request: NormalizationRequest, images: list[bytes]) -> NormalizedDocument:
        return normalize_rendered_pages_with_openai(
            request.document_family,
            request.country,
            request.filename,
            images,
            request.variant,
            request.pack_id,
            request.document_side,
        )
