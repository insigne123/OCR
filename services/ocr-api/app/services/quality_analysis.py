from __future__ import annotations

from collections.abc import Sequence

from app.schemas import QualityAssessment


def _average(values: Sequence[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), 3)


def build_quality_assessment(pages: Sequence[object], warnings: Sequence[str] | None = None) -> QualityAssessment:
    quality_scores = [getattr(page, "quality_score", None) for page in pages]
    blur_scores = [getattr(page, "blur_score", None) for page in pages]
    glare_scores = [getattr(page, "glare_score", None) for page in pages]
    crop_ratios = [getattr(page, "crop_ratio", None) for page in pages]
    document_coverages = [getattr(page, "document_coverage", None) for page in pages]
    orientations = [getattr(page, "orientation", None) for page in pages]
    capture_conditions: list[str] = []

    for page in pages:
        for condition in getattr(page, "capture_conditions", []) or []:
            if condition not in capture_conditions:
                capture_conditions.append(condition)

    average_quality = _average(quality_scores) or 0.0
    blur_score = _average(blur_scores)
    glare_score = _average(glare_scores)
    crop_ratio = _average(crop_ratios)
    document_coverage = _average(document_coverages)
    orientation = next((value for value in orientations if value is not None), None)

    recommendations: list[str] = []
    if average_quality < 0.55:
        recommendations.append("La captura tiene calidad baja; pedir nueva foto antes de automatizar.")
    if blur_score is not None and blur_score >= 0.3:
        recommendations.append("Se detecta blur apreciable; sugerir foto mas estable o mejor enfoque.")
    if glare_score is not None and glare_score >= 0.24:
        recommendations.append("Hay reflejos visibles; sugerir mover la fuente de luz o cambiar angulo.")
    if crop_ratio is not None and crop_ratio < 0.92:
        recommendations.append("El documento parece recortado; pedir encuadre completo con margenes visibles.")
    if document_coverage is not None and document_coverage < 0.82:
        recommendations.append("La cobertura del documento es baja; acercar la camara o usar guia de captura.")
    if orientation not in {None, 0}:
        recommendations.append("La orientacion no es canonica; conviene enderezar antes del OCR final.")
    if warnings:
        recommendations.extend([warning for warning in warnings if warning not in recommendations][:2])
    if not recommendations:
        recommendations.append("La captura se ve apta para OCR automatico.")

    return QualityAssessment(
        score=round(max(0.05, min(average_quality, 0.99)), 3),
        blur_score=blur_score,
        glare_score=glare_score,
        crop_ratio=crop_ratio,
        document_coverage=document_coverage,
        orientation=orientation,
        capture_conditions=capture_conditions,
        recommendations=recommendations,
    )
