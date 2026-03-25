from __future__ import annotations

from dataclasses import dataclass

from app.services.document_classifier import DocumentClassification, classify_document


@dataclass(frozen=True)
class PageClassificationResult:
    page_number: int
    classification: DocumentClassification


@dataclass(frozen=True)
class PageAnalysisResult:
    pages: list[PageClassificationResult]
    dominant: DocumentClassification | None
    document_side: str | None
    cross_side_detected: bool
    assumptions: list[str]


def _summarize_page(classification: DocumentClassification, page_number: int) -> str:
    side = classification.document_side or "unknown-side"
    variant = classification.variant or "no-variant"
    return f"Pagina {page_number}: {classification.document_family}/{classification.country}/{variant}/{side} ({classification.confidence:.2f})"


def analyze_document_pages(page_texts: list[str], requested_family: str, requested_country: str) -> PageAnalysisResult:
    page_results: list[PageClassificationResult] = []

    for index, page_text in enumerate(page_texts, start=1):
        if not (page_text or "").strip():
            continue
        classification = classify_document(page_text, requested_family, requested_country)
        page_results.append(PageClassificationResult(page_number=index, classification=classification))

    if not page_results:
        return PageAnalysisResult(pages=[], dominant=None, document_side=None, cross_side_detected=False, assumptions=[])

    contextual_seed = max(page_results, key=lambda result: result.classification.confidence)
    contextual_family = contextual_seed.classification.document_family if contextual_seed.classification.supported else requested_family
    contextual_country = contextual_seed.classification.country if contextual_seed.classification.supported else requested_country

    improved_page_results: list[PageClassificationResult] = []
    for result in page_results:
        classification = result.classification
        if classification.supported and classification.confidence >= 0.48:
            improved_page_results.append(result)
            continue

        improved = classify_document(page_texts[result.page_number - 1], contextual_family, contextual_country)
        if improved.confidence > classification.confidence:
            improved_page_results.append(PageClassificationResult(page_number=result.page_number, classification=improved))
        else:
            improved_page_results.append(result)

    page_results = improved_page_results

    sorted_pages = sorted(
        page_results,
        key=lambda result: (
            result.classification.document_family == "identity" and result.classification.document_side == "front",
            result.classification.supported,
            result.classification.confidence,
        ),
        reverse=True,
    )
    dominant = sorted_pages[0].classification

    sides = {result.classification.document_side for result in page_results if result.classification.document_side}
    families = {result.classification.document_family for result in page_results}
    countries = {result.classification.country for result in page_results if result.classification.country}
    cross_side_detected = sides == {"front", "back"} and len(families) == 1 and len(countries) == 1

    if cross_side_detected:
        document_side = "front+back"
    elif len(sides) == 1:
        document_side = next(iter(sides))
    else:
        document_side = dominant.document_side

    assumptions = [_summarize_page(result.classification, result.page_number) for result in page_results]
    if cross_side_detected:
        assumptions.append("Se detectaron frente y dorso del mismo documento en paginas separadas.")

    return PageAnalysisResult(
        pages=page_results,
        dominant=dominant,
        document_side=document_side,
        cross_side_detected=cross_side_detected,
        assumptions=assumptions,
    )
