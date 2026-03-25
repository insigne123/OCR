from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.document_splitter import split_document_pages


class DocumentSplitterTests(unittest.TestCase):
    def test_splits_mixed_document_by_page(self) -> None:
        result = split_document_pages(
            [
                "REPUBLICA DE CHILE CEDULA DE IDENTIDAD RUN 12.345.678-5",
                "CERTIFICADO DE COTIZACIONES AFP PRO VIDA RUT 12.345.678-5 2025-08 2,536,386",
            ],
            "mixed",
            "AUTO",
        )

        self.assertTrue(result.mixed_detected)
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].document_family, "identity")
        self.assertEqual(result.segments[1].document_family, "certificate")

    def test_merges_identity_front_and_back_into_single_segment(self) -> None:
        result = split_document_pages(
            [
                "REPUBLICA DE CHILE CEDULA DE IDENTIDAD RUN 12.345.678-5 NOMBRES JUAN",
                "REPUBLICA DE CHILE CEDULA DE IDENTIDAD DOMICILIO AV SIEMPRE VIVA 123 COMUNA SANTIAGO",
            ],
            "identity",
            "CL",
        )

        self.assertFalse(result.mixed_detected)
        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].document_side, "front+back")
        self.assertEqual(result.segments[0].page_numbers, [1, 2])


if __name__ == "__main__":
    unittest.main()
