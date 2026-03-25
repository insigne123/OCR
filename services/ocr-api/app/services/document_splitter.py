from __future__ import annotations

from dataclasses import dataclass

from app.services.document_classifier import DocumentClassification, classify_document


@dataclass(frozen=True)
class DocumentSegment:
    segment_id: str
    start_page: int
    end_page: int
    page_numbers: list[int]
    document_family: str
    country: str
    variant: str | None
    pack_id: str | None
    document_side: str | None
    supported: bool
    confidence: float
    summary: str


@dataclass(frozen=True)
class SplitDocumentResult:
    page_count: int
    segments: list[DocumentSegment]
    mixed_detected: bool
    assumptions: list[str]


def _base_pack_id(pack_id: str | None) -> str | None:
    if not pack_id:
        return None
    for suffix in ("-front", "-back"):
        if pack_id.endswith(suffix):
            return pack_id[: -len(suffix)]
    return pack_id


def _merge_side(left: str | None, right: str | None) -> str | None:
    sides = {side for side in (left, right) if side}
    if sides == {"front", "back"}:
        return "front+back"
    if len(sides) == 1:
        return next(iter(sides))
    return left or right


def _segment_summary(classification: DocumentClassification, start_page: int, end_page: int, document_side: str | None) -> str:
    pages = f"pages {start_page}-{end_page}" if start_page != end_page else f"page {start_page}"
    variant = classification.variant or "no-variant"
    side = document_side or classification.document_side or "unknown-side"
    return f"{pages}: {classification.document_family}/{classification.country}/{variant}/{side} ({classification.confidence:.2f})"


def _can_join_segments(current: DocumentClassification, candidate: DocumentClassification) -> bool:
    if current.document_family != candidate.document_family or current.country != candidate.country:
        return False

    if current.document_family == "identity":
        current_pack = _base_pack_id(current.pack_id)
        candidate_pack = _base_pack_id(candidate.pack_id)
        if current_pack and candidate_pack and current_pack == candidate_pack:
            return True
        if current.document_side and candidate.document_side and {current.document_side, candidate.document_side} == {"front", "back"}:
            return True

    return (current.variant or "") == (candidate.variant or "")


def split_document_pages(page_texts: list[str], requested_family: str, requested_country: str) -> SplitDocumentResult:
    non_empty_pages = [(index + 1, text) for index, text in enumerate(page_texts) if (text or "").strip()]

    if not non_empty_pages:
        return SplitDocumentResult(page_count=max(1, len(page_texts)), segments=[], mixed_detected=False, assumptions=[])

    page_classifications = [
        (page_number, classify_document(text, requested_family, requested_country))
        for page_number, text in non_empty_pages
    ]

    segments: list[DocumentSegment] = []
    current_pages: list[int] = []
    current_classification: DocumentClassification | None = None
    current_side: str | None = None

    def flush_segment() -> None:
        nonlocal current_pages, current_classification, current_side
        if not current_pages or current_classification is None:
            return
        segments.append(
            DocumentSegment(
                segment_id=f"segment-{len(segments) + 1}",
                start_page=current_pages[0],
                end_page=current_pages[-1],
                page_numbers=[*current_pages],
                document_family=current_classification.document_family,
                country=current_classification.country,
                variant=current_classification.variant,
                pack_id=current_classification.pack_id,
                document_side=current_side or current_classification.document_side,
                supported=current_classification.supported,
                confidence=current_classification.confidence,
                summary=_segment_summary(current_classification, current_pages[0], current_pages[-1], current_side),
            )
        )
        current_pages = []
        current_classification = None
        current_side = None

    for page_number, classification in page_classifications:
        if current_classification is None:
            current_classification = classification
            current_pages = [page_number]
            current_side = classification.document_side
            continue

        same_segment = _can_join_segments(current_classification, classification)
        if same_segment:
            current_pages.append(page_number)
            current_side = _merge_side(current_side, classification.document_side)
            continue

        flush_segment()
        current_classification = classification
        current_pages = [page_number]
        current_side = classification.document_side

    flush_segment()

    mixed_detected = len({(segment.document_family, segment.country, _base_pack_id(segment.pack_id)) for segment in segments}) > 1 or len(segments) > 1
    assumptions = [segment.summary for segment in segments]
    if any(segment.document_side == "front+back" for segment in segments):
        assumptions.append("Se reagruparon paginas consecutivas frente/dorso del mismo documento para ruteo conjunto.")
    if mixed_detected:
        assumptions.append("Se detectaron multiples segmentos documentales en el archivo; conviene separar el PDF antes de la extraccion final.")

    return SplitDocumentResult(
        page_count=max(page_number for page_number, _ in non_empty_pages),
        segments=segments,
        mixed_detected=mixed_detected,
        assumptions=assumptions,
    )
