from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import atan, ceil, degrees
from statistics import mean

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import cv2 as _cv2
    import numpy as _np
except Exception:  # noqa: BLE001
    _cv2 = None
    _np = None


@dataclass(frozen=True)
class CaptureRescuePlan:
    normalized_image: Image.Image
    crop_ratio: float
    document_coverage: float
    rescue_profiles: tuple[str, ...]
    variant_images: dict[str, Image.Image]
    corners: tuple[tuple[float, float], ...]
    edge_confidence: float
    skew_angle: float
    skew_applied: bool
    perspective_applied: bool
    capture_conditions: tuple[str, ...]
    page_profiles: dict[str, str]


def _serialize_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _resize_for_analysis(image: Image.Image, max_edge: int = 720) -> tuple[Image.Image, float]:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image, 1.0
    scale = max_edge / float(longest)
    resized = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), resample=Image.Resampling.BILINEAR)
    return resized, scale


def _resize_for_ocr(image: Image.Image, max_edge: int = 1500) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    return image.resize((max(1, int(width * scale)), max(1, int(height * scale))), resample=Image.Resampling.LANCZOS)


def _advanced_rescue_available() -> bool:
    return _cv2 is not None and _np is not None


def _to_rgb_array(image: Image.Image):
    if not _advanced_rescue_available():
        return None
    import numpy as np_module

    return np_module.array(image.convert("RGB"), dtype=np_module.uint8)


def _from_rgb_array(array) -> Image.Image:
    if not _advanced_rescue_available():
        raise RuntimeError("Advanced rescue stack is not available")
    import numpy as np_module

    clipped = np_module.clip(array, 0, 255).astype(np_module.uint8)
    return Image.fromarray(clipped)


def _border_background_level(grayscale: Image.Image) -> float:
    width, height = grayscale.size
    if width == 0 or height == 0:
        return 255.0

    pixels = grayscale.load()
    assert pixels is not None
    border = max(1, min(width, height) // 20)
    samples: list[int] = []

    for x in range(width):
        for y in range(border):
            samples.append(pixels[x, y])
            samples.append(pixels[x, height - 1 - y])
    for y in range(border, height - border):
        for x in range(border):
            samples.append(pixels[x, y])
            samples.append(pixels[width - 1 - x, y])

    return float(mean(samples)) if samples else 255.0


def _estimate_document_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    grayscale = image.convert("L")
    width, height = grayscale.size
    if width < 24 or height < 24:
        return None

    background_level = _border_background_level(grayscale)
    pixels = grayscale.load()
    assert pixels is not None
    threshold = 18 if background_level < 210 else 28

    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        for x in range(width):
            if abs(pixels[x, y] - background_level) >= threshold:
                xs.append(x)
                ys.append(y)

    if not xs or not ys:
        return None

    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    area = max(1, (right - left + 1) * (bottom - top + 1))
    coverage = area / float(width * height)
    if coverage < 0.22 or coverage > 0.985:
        return None
    return left, top, right, bottom


def _scale_bbox(bbox: tuple[int, int, int, int] | None, scale: float) -> tuple[int, int, int, int] | None:
    if bbox is None or scale == 1.0:
        return bbox
    inverse = 1.0 / scale
    left, top, right, bottom = bbox
    return (int(left * inverse), int(top * inverse), int(right * inverse), int(bottom * inverse))


def _scale_corners(corners: tuple[tuple[float, float], ...], scale: float) -> tuple[tuple[float, float], ...]:
    if scale == 1.0:
        return corners
    inverse = 1.0 / scale
    return tuple((x * inverse, y * inverse) for x, y in corners)


def _find_corner_points(image: Image.Image, bbox: tuple[int, int, int, int]) -> tuple[tuple[float, float], ...]:
    left, top, right, bottom = bbox
    grayscale = image.convert("L")
    pixels = grayscale.load()
    assert pixels is not None
    background_level = _border_background_level(grayscale)
    threshold = 18 if background_level < 210 else 28

    def probe(region: tuple[int, int, int, int], horizontal_reverse: bool = False, vertical_reverse: bool = False) -> tuple[float, float]:
        x_start, y_start, x_end, y_end = region
        x_range = range(x_end - 1, x_start - 1, -1) if horizontal_reverse else range(x_start, x_end)
        y_range = range(y_end - 1, y_start - 1, -1) if vertical_reverse else range(y_start, y_end)
        for y in y_range:
            for x in x_range:
                if abs(pixels[x, y] - background_level) >= threshold:
                    return float(x), float(y)
        fallback_x = float(x_end - 1 if horizontal_reverse else x_start)
        fallback_y = float(y_end - 1 if vertical_reverse else y_start)
        return fallback_x, fallback_y

    width = max(1, right - left + 1)
    height = max(1, bottom - top + 1)
    region_w = max(8, width // 6)
    region_h = max(8, height // 6)
    top_left = probe((left, top, min(right + 1, left + region_w), min(bottom + 1, top + region_h)))
    top_right = probe((max(left, right - region_w + 1), top, right + 1, min(bottom + 1, top + region_h)), horizontal_reverse=True)
    bottom_right = probe((max(left, right - region_w + 1), max(top, bottom - region_h + 1), right + 1, bottom + 1), horizontal_reverse=True, vertical_reverse=True)
    bottom_left = probe((left, max(top, bottom - region_h + 1), min(right + 1, left + region_w), bottom + 1), vertical_reverse=True)
    return (top_left, top_right, bottom_right, bottom_left)


def _estimate_skew_angle(corners: tuple[tuple[float, float], ...]) -> float:
    if len(corners) != 4:
        return 0.0
    top_left, top_right, bottom_right, bottom_left = corners
    top_delta_y = top_right[1] - top_left[1]
    top_delta_x = max(1.0, top_right[0] - top_left[0])
    bottom_delta_y = bottom_right[1] - bottom_left[1]
    bottom_delta_x = max(1.0, bottom_right[0] - bottom_left[0])
    average_slope = ((top_delta_y / top_delta_x) + (bottom_delta_y / bottom_delta_x)) / 2.0
    return round(degrees(atan(average_slope)), 3)


def _estimate_edge_confidence(image: Image.Image, bbox: tuple[int, int, int, int], corners: tuple[tuple[float, float], ...]) -> float:
    width, height = image.size
    bbox_area = max(1.0, (bbox[2] - bbox[0] + 1) * (bbox[3] - bbox[1] + 1))
    coverage = bbox_area / max(1.0, width * height)
    corner_spread_x = max(corner[0] for corner in corners) - min(corner[0] for corner in corners)
    corner_spread_y = max(corner[1] for corner in corners) - min(corner[1] for corner in corners)
    geometry_score = min(1.0, (corner_spread_x / max(1.0, bbox[2] - bbox[0] + 1) + corner_spread_y / max(1.0, bbox[3] - bbox[1] + 1)) / 2.0)
    return round(_clamp((coverage * 0.7) + (geometry_score * 0.3)), 3)


def _correct_perspective(image: Image.Image, corners: tuple[tuple[float, float], ...]) -> Image.Image:
    top_left, top_right, bottom_right, bottom_left = corners
    target_width = int(max(top_right[0] - top_left[0], bottom_right[0] - bottom_left[0], 1))
    target_height = int(max(bottom_left[1] - top_left[1], bottom_right[1] - top_right[1], 1))
    if target_width < 32 or target_height < 32:
        return image
    quad = (*top_left, *top_right, *bottom_right, *bottom_left)
    return image.transform((target_width, target_height), Image.Transform.QUAD, quad, resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255))


def _crop_document(image: Image.Image) -> tuple[Image.Image, float, float, tuple[int, int, int, int] | None]:
    analysis_image, analysis_scale = _resize_for_analysis(image)
    bbox = _scale_bbox(_estimate_document_bbox(analysis_image), analysis_scale)
    width, height = image.size
    total_area = float(max(1, width * height))
    if bbox is None:
        return image, 1.0, 1.0, None

    left, top, right, bottom = bbox
    padding_x = max(4, ceil((right - left + 1) * 0.03))
    padding_y = max(4, ceil((bottom - top + 1) * 0.03))
    crop_box = (
        max(0, left - padding_x),
        max(0, top - padding_y),
        min(width, right + padding_x + 1),
        min(height, bottom + padding_y + 1),
    )
    cropped = image.crop(crop_box)
    crop_area = float(max(1, cropped.size[0] * cropped.size[1]))
    document_coverage = round(((right - left + 1) * (bottom - top + 1)) / total_area, 3)
    return cropped, round(crop_area / total_area, 3), document_coverage, crop_box


def _compress_highlights(image: Image.Image) -> Image.Image:
    lut = []
    for value in range(256):
        if value < 210:
            lut.append(value)
        elif value < 235:
            lut.append(int(210 + ((value - 210) * 0.6)))
        else:
            lut.append(int(225 + ((value - 235) * 0.2)))
    return image.point(lut * 3 if image.mode == "RGB" else lut)


def _shadow_boost(image: Image.Image) -> Image.Image:
    boosted = ImageEnhance.Brightness(image).enhance(1.08)
    boosted = ImageEnhance.Contrast(boosted).enhance(1.18)
    return ImageOps.autocontrast(boosted, cutoff=1)


def _grayscale_contrast(image: Image.Image) -> Image.Image:
    grayscale = image.convert("L")
    grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
    grayscale = ImageEnhance.Contrast(grayscale).enhance(1.35)
    return grayscale.convert("RGB")


def _sharpen(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.UnsharpMask(radius=1.4, percent=150, threshold=3))


def _denoise(image: Image.Image) -> Image.Image:
    if not _advanced_rescue_available():
        return image
    import cv2 as cv2_module

    array = _to_rgb_array(image)
    if array is None:
        return image
    bgr = cv2_module.cvtColor(array, cv2_module.COLOR_RGB2BGR)
    denoised = cv2_module.fastNlMeansDenoisingColored(bgr, None, 7, 7, 7, 21)
    rgb = cv2_module.cvtColor(denoised, cv2_module.COLOR_BGR2RGB)
    return _from_rgb_array(rgb)


def _clahe_enhance(image: Image.Image) -> Image.Image:
    if not _advanced_rescue_available():
        return image
    import cv2 as cv2_module

    array = _to_rgb_array(image)
    if array is None:
        return image
    lab = cv2_module.cvtColor(array, cv2_module.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2_module.split(lab)
    clahe = cv2_module.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    merged = cv2_module.merge((clahe.apply(l_channel), a_channel, b_channel))
    rgb = cv2_module.cvtColor(merged, cv2_module.COLOR_LAB2RGB)
    return _from_rgb_array(rgb)


def _adaptive_binarize(image: Image.Image, window_size: int = 25, k: float = 0.18) -> Image.Image:
    if not _advanced_rescue_available():
        return image
    import cv2 as cv2_module
    import numpy as np_module

    array = _to_rgb_array(image)
    if array is None:
        return image
    grayscale = cv2_module.cvtColor(array, cv2_module.COLOR_RGB2GRAY).astype(np_module.float32)
    effective_window = max(15, window_size)
    if effective_window % 2 == 0:
        effective_window += 1
    mean_map = cv2_module.boxFilter(grayscale, ddepth=-1, ksize=(effective_window, effective_window), normalize=True)
    sqr_mean_map = cv2_module.sqrBoxFilter(grayscale, ddepth=-1, ksize=(effective_window, effective_window), normalize=True)
    variance = np_module.maximum(sqr_mean_map - (mean_map * mean_map), 0.0)
    std_map = np_module.sqrt(variance)
    threshold = mean_map * (1.0 + k * ((std_map / 128.0) - 1.0))
    binary = np_module.where(grayscale > threshold, 255, 0).astype(np_module.uint8)
    rgb = cv2_module.cvtColor(binary, cv2_module.COLOR_GRAY2RGB)
    return _from_rgb_array(rgb)


def _aggressive_rescue(image: Image.Image) -> Image.Image:
    enhanced = _denoise(image)
    enhanced = _clahe_enhance(enhanced)
    enhanced = _sharpen(enhanced)
    enhanced = _adaptive_binarize(enhanced)
    return enhanced


def _rotate_with_canvas(image: Image.Image, angle: float) -> Image.Image:
    rotated = image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255))
    cropped, _, _, _ = _crop_document(rotated)
    return cropped


def _capture_conditions(
    quality: float,
    blur: float,
    glare: float,
    crop_ratio: float,
    document_coverage: float,
    skew_angle: float,
    perspective_applied: bool,
) -> tuple[str, ...]:
    conditions: list[str] = []
    if quality >= 0.86 and blur < 0.2 and glare < 0.18 and crop_ratio >= 0.95:
        conditions.append("clean")
    if quality < 0.8:
        conditions.append("low_quality")
    if blur >= 0.24:
        conditions.append("blur")
    if glare >= 0.24:
        conditions.append("glare")
    if crop_ratio < 0.94 or document_coverage < 0.82:
        conditions.append("cropped")
    if abs(skew_angle) >= 2.5:
        conditions.append("tilt")
    if perspective_applied:
        conditions.append("perspective")
    if quality < 0.72 and glare < 0.18:
        conditions.append("low_light")
    if quality < 0.58 or blur >= 0.36:
        conditions.append("extreme_low_quality")
    return tuple(dict.fromkeys(conditions or ["clean"]))


def build_capture_rescue_plan(image: Image.Image, quality_hint: float | None = None, blur_hint: float | None = None, glare_hint: float | None = None) -> CaptureRescuePlan:
    base = ImageOps.exif_transpose(image).convert("RGB")
    analysis_image, analysis_scale = _resize_for_analysis(base)
    bbox_small = _estimate_document_bbox(analysis_image)
    bbox = _scale_bbox(bbox_small, analysis_scale)
    corners_small = _find_corner_points(analysis_image, bbox_small) if bbox_small else ((0.0, 0.0), (float(analysis_image.width), 0.0), (float(analysis_image.width), float(analysis_image.height)), (0.0, float(analysis_image.height)))
    corners = _scale_corners(corners_small, analysis_scale)
    skew_angle = _estimate_skew_angle(corners)
    edge_confidence = _estimate_edge_confidence(base, bbox, corners) if bbox else 0.0

    perspective_applied = bool(bbox and edge_confidence >= 0.46)
    perspective_image = _correct_perspective(base, corners) if perspective_applied else base
    skew_applied = abs(skew_angle) >= 2.5
    normalized_base = _rotate_with_canvas(perspective_image, -skew_angle) if skew_applied else perspective_image
    cropped, crop_ratio, document_coverage, _ = _crop_document(normalized_base)
    cropped = _resize_for_ocr(cropped)

    variants: dict[str, Image.Image] = {"original": cropped}
    rescue_profiles: list[str] = []
    quality = quality_hint if quality_hint is not None else 0.75
    blur = blur_hint if blur_hint is not None else 0.35
    glare = glare_hint if glare_hint is not None else 0.25
    conditions = _capture_conditions(quality, blur, glare, crop_ratio, document_coverage, skew_angle, perspective_applied)

    if "glare" in conditions:
        variants["deglare"] = _compress_highlights(cropped)
        rescue_profiles.append("deglare")
    if blur >= 0.24 or quality < 0.84:
        variants["sharpen"] = _sharpen(cropped)
        rescue_profiles.append("sharpen")
    if "low_light" in conditions or "shadow" in conditions or quality < 0.8:
        variants["shadow_boost"] = _shadow_boost(cropped)
        rescue_profiles.append("shadow_boost")
    if quality < 0.74:
        variants["gray_contrast"] = _grayscale_contrast(cropped)
        rescue_profiles.append("gray_contrast")
    if _advanced_rescue_available():
        if blur >= 0.3 or quality < 0.75:
            denoised = _denoise(cropped)
            variants["denoise"] = denoised
            variants["denoise_sharpen"] = _sharpen(denoised)
            rescue_profiles.extend(["denoise", "denoise_sharpen"])
        if "low_light" in conditions or quality < 0.78 or glare >= 0.22:
            clahe_source = variants.get("deglare", cropped)
            variants["clahe"] = _clahe_enhance(clahe_source)
            rescue_profiles.append("clahe")
        if "low_light" in conditions or glare >= 0.28 or quality < 0.7:
            adaptive_source = variants.get("clahe") or variants.get("shadow_boost") or variants.get("deglare") or cropped
            variants["adaptive_binarize"] = _adaptive_binarize(adaptive_source)
            rescue_profiles.append("adaptive_binarize")
        if "extreme_low_quality" in conditions or (quality < 0.64 and "cropped" in conditions):
            variants["aggressive_rescue"] = _aggressive_rescue(cropped)
            rescue_profiles.append("aggressive_rescue")
    if abs(skew_angle) >= 4.5:
        variants["rotate_left_4" if skew_angle > 0 else "rotate_right_4"] = _rotate_with_canvas(cropped, -4 if skew_angle > 0 else 4)
        rescue_profiles.append("rotate_left_4" if skew_angle > 0 else "rotate_right_4")

    profile_priority = {
        "aggressive_rescue": 0,
        "adaptive_binarize": 1,
        "clahe": 2,
        "denoise_sharpen": 3,
        "deglare": 4,
        "shadow_boost": 5,
        "gray_contrast": 6,
        "denoise": 7,
        "sharpen": 8,
    }
    unique_profiles = tuple(
        sorted(
            dict.fromkeys(rescue_profiles),
            key=lambda profile: (profile_priority.get(profile, 20), profile),
        )[:6]
    )
    variants = {profile: variants[profile] for profile in ("original", *unique_profiles) if profile in variants}
    page_profiles = {profile: profile for profile in variants}
    return CaptureRescuePlan(
        normalized_image=cropped,
        crop_ratio=crop_ratio,
        document_coverage=document_coverage,
        rescue_profiles=unique_profiles,
        variant_images=variants,
        corners=tuple((round(x, 2), round(y, 2)) for x, y in corners),
        edge_confidence=edge_confidence,
        skew_angle=skew_angle,
        skew_applied=skew_applied,
        perspective_applied=perspective_applied,
        capture_conditions=conditions,
        page_profiles=page_profiles,
    )


def serialize_variant_images(variant_images: dict[str, Image.Image]) -> dict[str, bytes]:
    return {profile: _serialize_png(image) for profile, image in variant_images.items()}
