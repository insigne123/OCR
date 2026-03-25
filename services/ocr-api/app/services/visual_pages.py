from __future__ import annotations

from io import BytesIO

import fitz


def render_pdf_pages_to_png_bytes(file_bytes: bytes, max_pages: int = 3, scale: float = 2.0) -> list[bytes]:
    document = fitz.open(stream=file_bytes, filetype="pdf")
    rendered_pages: list[bytes] = []

    try:
        for page_index in range(min(max_pages, document.page_count)):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            rendered_pages.append(pixmap.tobytes("png"))
    finally:
        document.close()

    return rendered_pages
