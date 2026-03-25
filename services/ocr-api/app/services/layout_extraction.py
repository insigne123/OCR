from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.visual_ocr import OCRToken

KV_INLINE_PATTERN = re.compile(r"^([A-Z0-9ÁÉÍÓÚÜÑ./()\- ]{2,48}?)\s*[:=]\s+(.+)$", re.IGNORECASE)
DATE_OR_AMOUNT_PATTERN = re.compile(r"\b(?:20\d{2}[-/]\d{2}(?:[-/]\d{2})?|\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|\d{2}[-/]\d{2}[-/]\d{4})\b")


@dataclass(frozen=True)
class LayoutLine:
    page_number: int
    text: str
    bbox: list[list[float]] | None = None


@dataclass(frozen=True)
class LayoutKeyValue:
    label: str
    value: str
    page_number: int
    raw_line: str
    bbox: list[list[float]] | None = None


@dataclass(frozen=True)
class LayoutExtractionResult:
    engine: str
    lines: list[LayoutLine]
    key_value_pairs: list[LayoutKeyValue]
    table_candidate_rows: list[str]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _line_bbox(tokens: list[OCRToken]) -> list[list[float]]:
    xs = [point[0] for token in tokens for point in token.bbox]
    ys = [point[1] for token in tokens for point in token.bbox]
    return [[min(xs), min(ys)], [max(xs), min(ys)], [max(xs), max(ys)], [min(xs), max(ys)]]


def _token_center_y(token: OCRToken) -> float:
    ys = [point[1] for point in token.bbox]
    return sum(ys) / max(1, len(ys))


def _token_height(token: OCRToken) -> float:
    ys = [point[1] for point in token.bbox]
    return max(ys) - min(ys)


def _token_min_x(token: OCRToken) -> float:
    return min(point[0] for point in token.bbox)


def _is_label_like(text: str) -> bool:
    cleaned = _clean(text)
    if not cleaned or len(cleaned) > 48:
        return False
    if sum(char.isdigit() for char in cleaned) > 4:
        return False
    alpha_ratio = sum(char.isalpha() for char in cleaned) / max(1, len(cleaned.replace(" ", "")))
    return alpha_ratio >= 0.45


def _looks_like_value(text: str) -> bool:
    cleaned = _clean(text)
    if not cleaned:
        return False
    if len(cleaned) <= 2:
        return False
    return bool(any(char.isdigit() for char in cleaned) or len(cleaned.split()) >= 2 or cleaned[0].isupper())


def _looks_like_table_row(text: str) -> bool:
    cleaned = _clean(text)
    if len(cleaned.split()) < 3:
        return False
    matches = DATE_OR_AMOUNT_PATTERN.findall(cleaned)
    return len(matches) >= 1 and sum(char.isdigit() for char in cleaned) >= 4


def _group_tokens_into_lines(tokens: list[OCRToken]) -> list[LayoutLine]:
    if not tokens:
        return []

    sorted_tokens = sorted(tokens, key=lambda token: (token.page_number, _token_center_y(token), _token_min_x(token)))
    median_height = sorted((_token_height(token) for token in sorted_tokens), reverse=False)[len(sorted_tokens) // 2]
    tolerance = max(10.0, median_height * 0.75)

    grouped: list[tuple[int, float, list[OCRToken]]] = []
    for token in sorted_tokens:
        token_center = _token_center_y(token)
        if not grouped or token.page_number != grouped[-1][0] or abs(token_center - grouped[-1][1]) > tolerance:
            grouped.append((token.page_number, token_center, [token]))
        else:
            grouped[-1][2].append(token)

    lines: list[LayoutLine] = []
    for page_number, _, line_tokens in grouped:
        ordered = sorted(line_tokens, key=_token_min_x)
        text = _clean(" ".join(token.text for token in ordered))
        if not text:
            continue
        lines.append(LayoutLine(page_number=page_number, text=text, bbox=_line_bbox(ordered)))
    return lines


def _extract_key_values(lines: list[LayoutLine]) -> list[LayoutKeyValue]:
    pairs: list[LayoutKeyValue] = []

    for index, line in enumerate(lines):
        inline_match = KV_INLINE_PATTERN.match(line.text)
        if inline_match:
            label = _clean(inline_match.group(1))
            value = _clean(inline_match.group(2))
            if _is_label_like(label) and _looks_like_value(value):
                pairs.append(LayoutKeyValue(label=label, value=value, page_number=line.page_number, raw_line=line.text, bbox=line.bbox))
                continue

        if index + 1 >= len(lines):
            continue

        next_line = lines[index + 1]
        if next_line.page_number != line.page_number:
            continue

        if _is_label_like(line.text) and _looks_like_value(next_line.text):
            if len(line.text.split()) <= 5 and line.text == line.text.upper():
                pairs.append(LayoutKeyValue(label=line.text, value=next_line.text, page_number=line.page_number, raw_line=f"{line.text} -> {next_line.text}", bbox=next_line.bbox or line.bbox))

    deduped: dict[tuple[int, str, str], LayoutKeyValue] = {}
    for pair in pairs:
        deduped[(pair.page_number, pair.label.lower(), pair.value.lower())] = pair
    return list(deduped.values())


def _extract_table_candidates(lines: list[LayoutLine]) -> list[str]:
    rows: list[str] = []
    for line in lines:
        if _looks_like_table_row(line.text):
            rows.append(line.text)
    return rows[:50]


def extract_layout_from_tokens(tokens: list[OCRToken], engine: str = "visual-layout") -> LayoutExtractionResult:
    lines = _group_tokens_into_lines(tokens)
    return LayoutExtractionResult(
        engine=engine,
        lines=lines,
        key_value_pairs=_extract_key_values(lines),
        table_candidate_rows=_extract_table_candidates(lines),
    )


def extract_layout_from_page_texts(page_texts: list[str], engine: str = "text-layout") -> LayoutExtractionResult:
    lines: list[LayoutLine] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        for raw_line in page_text.splitlines():
            cleaned = _clean(raw_line)
            if cleaned:
                lines.append(LayoutLine(page_number=page_number, text=cleaned, bbox=None))

    return LayoutExtractionResult(
        engine=engine,
        lines=lines,
        key_value_pairs=_extract_key_values(lines),
        table_candidate_rows=_extract_table_candidates(lines),
    )
