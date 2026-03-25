from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps

from app.services.image_capture_hardening import build_capture_rescue_plan, serialize_variant_images

try:
    from pillow_heif import register_heif_opener
except Exception:  # noqa: BLE001
    register_heif_opener = None

if register_heif_opener is not None:
    register_heif_opener()


@dataclass(frozen=True)
class PreprocessedPage:
    page_number: int
    image_bytes: bytes
    width: int
    height: int
    orientation: int
    quality_score: float
    blur_score: float
    glare_score: float
    has_embedded_text: bool
    crop_ratio: float = 1.0
    document_coverage: float = 1.0
    edge_confidence: float = 0.0
    skew_angle: float = 0.0
    skew_applied: bool = False
    perspective_applied: bool = False
    capture_conditions: list[str] = field(default_factory=list)
    rescue_profiles: list[str] = field(default_factory=list)
    variant_images: dict[str, bytes] = field(default_factory=dict)
    page_profile_map: dict[str, str] = field(default_factory=dict)
    corners: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class OCRVariantSet:
    profile: str
    images: list[bytes]
    page_count: int
    average_quality: float
    assumptions: list[str]
    page_profiles: list[str]


IMAGE_FILETYPES = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".heic": "heic",
    ".heif": "heif",
    ".webp": "webp",
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _resolve_filetype(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or (content_type or "").lower() == "application/pdf":
        return "pdf"

    if suffix in IMAGE_FILETYPES:
        return IMAGE_FILETYPES[suffix]

    mime = (content_type or "").lower()
    if mime.startswith("image/"):
        return mime.split("/", 1)[1]

    return "pdf"


def _compute_render_scale(page: fitz.Page) -> float:
    rect = page.rect
    shortest_side = max(1.0, min(rect.width, rect.height))
    target_short_side = 1400.0
    return max(1.0, min(2.5, target_short_side / shortest_side))


def _pixel_intensity(samples: bytes, offset: int, channels: int) -> float:
    if channels >= 3:
        return (samples[offset] + samples[offset + 1] + samples[offset + 2]) / 3.0
    return float(samples[offset])


def _analyze_pixmap(pixmap: fitz.Pixmap) -> tuple[float, float, float]:
    total_pixels = max(1, pixmap.width * pixmap.height)
    channels = max(1, pixmap.n)
    samples = pixmap.samples
    stride = max(1, total_pixels // 6000)
    sampled: list[float] = []
    bright_pixels = 0
    total = 0.0
    total_squared = 0.0
    last_value: float | None = None
    diff_sum = 0.0
    diff_count = 0

    for pixel_index in range(0, total_pixels, stride):
        offset = pixel_index * channels
        if offset + (channels - 1) >= len(samples):
            break

        intensity = _pixel_intensity(samples, offset, channels)
        sampled.append(intensity)
        total += intensity
        total_squared += intensity * intensity
        if intensity >= 245:
            bright_pixels += 1
        if last_value is not None:
            diff_sum += abs(intensity - last_value)
            diff_count += 1
        last_value = intensity

    if not sampled:
        return 0.45, 0.28, 0.5

    count = float(len(sampled))
    mean = total / count
    variance = max(0.0, (total_squared / count) - (mean * mean))
    contrast = variance**0.5
    bright_ratio = bright_pixels / count
    edge_density = diff_sum / max(1, diff_count)

    blur_score = _clamp(1.0 - min(1.0, edge_density / 36.0))
    glare_score = _clamp((bright_ratio / 0.16) * 0.8 + (0.25 if mean > 225 else 0.0))

    resolution_score = min(1.0, min(pixmap.width, pixmap.height) / 1400.0)
    contrast_score = min(1.0, contrast / 52.0)
    sharpness_score = 1.0 - blur_score
    glare_penalty = 1.0 - glare_score
    quality_score = _clamp((resolution_score * 0.25) + (contrast_score * 0.25) + (sharpness_score * 0.3) + (glare_penalty * 0.2))

    return round(blur_score, 3), round(glare_score, 3), round(quality_score, 3)


def _analyze_pillow_image(image: Image.Image) -> tuple[float, float, float]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    total_pixels = max(1, width * height)
    stride = max(1, total_pixels // 6000)
    sampled: list[float] = []
    bright_pixels = 0
    total = 0.0
    total_squared = 0.0
    last_value: float | None = None
    diff_sum = 0.0
    diff_count = 0

    for index, pixel in enumerate(rgb.getdata()):
        if index % stride != 0:
            continue
        intensity = (pixel[0] + pixel[1] + pixel[2]) / 3.0
        sampled.append(intensity)
        total += intensity
        total_squared += intensity * intensity
        if intensity >= 245:
            bright_pixels += 1
        if last_value is not None:
            diff_sum += abs(intensity - last_value)
            diff_count += 1
        last_value = intensity

    if not sampled:
        return 0.45, 0.28, 0.5

    count = float(len(sampled))
    mean = total / count
    variance = max(0.0, (total_squared / count) - (mean * mean))
    contrast = variance**0.5
    bright_ratio = bright_pixels / count
    edge_density = diff_sum / max(1, diff_count)

    blur_score = _clamp(1.0 - min(1.0, edge_density / 36.0))
    glare_score = _clamp((bright_ratio / 0.16) * 0.8 + (0.25 if mean > 225 else 0.0))
    resolution_score = min(1.0, min(width, height) / 1400.0)
    contrast_score = min(1.0, contrast / 52.0)
    sharpness_score = 1.0 - blur_score
    glare_penalty = 1.0 - glare_score
    quality_score = _clamp((resolution_score * 0.25) + (contrast_score * 0.25) + (sharpness_score * 0.3) + (glare_penalty * 0.2))

    return round(blur_score, 3), round(glare_score, 3), round(quality_score, 3)


def _prepare_image_with_pillow(file_bytes: bytes, page_texts: list[str] | None = None) -> list[PreprocessedPage]:
    image = Image.open(BytesIO(file_bytes))
    image = ImageOps.exif_transpose(image).convert("RGB")
    blur_score, glare_score, quality_score = _analyze_pillow_image(image)
    rescue_plan = build_capture_rescue_plan(image, quality_score, blur_score, glare_score)
    normalized_image = rescue_plan.normalized_image
    blur_score, glare_score, quality_score = _analyze_pillow_image(normalized_image)
    output = BytesIO()
    normalized_image.save(output, format="PNG")
    return [
        PreprocessedPage(
            page_number=1,
            image_bytes=output.getvalue(),
            width=normalized_image.width,
            height=normalized_image.height,
            orientation=0,
            quality_score=quality_score,
            blur_score=blur_score,
            glare_score=glare_score,
            has_embedded_text=bool(page_texts and page_texts[0].strip()),
            crop_ratio=rescue_plan.crop_ratio,
            document_coverage=rescue_plan.document_coverage,
            edge_confidence=rescue_plan.edge_confidence,
            skew_angle=rescue_plan.skew_angle,
            skew_applied=rescue_plan.skew_applied,
            perspective_applied=rescue_plan.perspective_applied,
            capture_conditions=list(rescue_plan.capture_conditions),
            rescue_profiles=list(rescue_plan.rescue_profiles),
            variant_images=serialize_variant_images(rescue_plan.variant_images),
            page_profile_map=dict(rescue_plan.page_profiles),
            corners=[[x, y] for x, y in rescue_plan.corners],
        )
    ]


def prepare_document_pages(
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    page_texts: list[str] | None = None,
    max_pages: int = 5,
) -> list[PreprocessedPage]:
    filetype = _resolve_filetype(filename, content_type)
    if filetype != "pdf":
        try:
            return _prepare_image_with_pillow(file_bytes, page_texts)
        except Exception:
            pass

    document = fitz.open(stream=file_bytes, filetype=filetype)
    prepared_pages: list[PreprocessedPage] = []

    try:
        for page_index in range(min(max_pages, document.page_count)):
            page = document.load_page(page_index)
            scale = _compute_render_scale(page)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            blur_score, glare_score, quality_score = _analyze_pixmap(pixmap)
            base_image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
            rescue_plan = build_capture_rescue_plan(base_image, quality_score, blur_score, glare_score)
            normalized_image = rescue_plan.normalized_image
            blur_score, glare_score, quality_score = _analyze_pillow_image(normalized_image)
            normalized_output = BytesIO()
            normalized_image.save(normalized_output, format="PNG")
            page_text = page_texts[page_index] if page_texts and page_index < len(page_texts) else ""
            prepared_pages.append(
                PreprocessedPage(
                    page_number=page_index + 1,
                    image_bytes=normalized_output.getvalue(),
                    width=normalized_image.width,
                    height=normalized_image.height,
                    orientation=int(page.rotation or 0),
                    quality_score=quality_score,
                    blur_score=blur_score,
                    glare_score=glare_score,
                    has_embedded_text=bool(page_text.strip()),
                    crop_ratio=rescue_plan.crop_ratio,
                    document_coverage=rescue_plan.document_coverage,
                    edge_confidence=rescue_plan.edge_confidence,
                    skew_angle=rescue_plan.skew_angle,
                    skew_applied=rescue_plan.skew_applied,
                    perspective_applied=rescue_plan.perspective_applied,
                    capture_conditions=list(rescue_plan.capture_conditions),
                    rescue_profiles=list(rescue_plan.rescue_profiles),
                    variant_images=serialize_variant_images(rescue_plan.variant_images),
                    page_profile_map=dict(rescue_plan.page_profiles),
                    corners=[[x, y] for x, y in rescue_plan.corners],
                )
            )
        return prepared_pages
    finally:
        document.close()


def build_ocr_variant_sets(prepared_pages: list[PreprocessedPage]) -> list[OCRVariantSet]:
    if not prepared_pages:
        return []

    profiles = {"original"}
    for page in prepared_pages:
        profiles.update(page.variant_images.keys())

    variant_sets: list[OCRVariantSet] = []
    average_quality = sum(page.quality_score for page in prepared_pages) / len(prepared_pages)
    for profile in sorted(profiles, key=lambda value: (value != "original", value)):
        images = [page.variant_images.get(profile, page.image_bytes) for page in prepared_pages]
        page_profiles = [page.page_profile_map.get(profile, "original") if profile in page.variant_images else "original" for page in prepared_pages]
        assumptions = [f"Perfil OCR {profile} aplicado sobre {len(prepared_pages)} pagina(s)."]
        if profile != "original":
            assumptions.append("Perfil de rescate activado por calidad, glare o geometria de captura movil.")
        variant_sets.append(
            OCRVariantSet(
                profile=profile,
                images=images,
                page_count=len(images),
                average_quality=round(average_quality, 3),
                assumptions=assumptions,
                page_profiles=page_profiles,
            )
        )

    return variant_sets
