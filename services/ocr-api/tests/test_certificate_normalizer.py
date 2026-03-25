from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.heuristic_normalizer import normalize_certificate_text


class CertificateNormalizerTests(unittest.TestCase):
    def test_detects_tabular_movements(self) -> None:
        sample = (
            "CERTIFICADO DE COTIZACIONES\n"
            "TITULAR: JUAN PEREZ\n"
            "AFP PRO VIDA\n"
            "RUT: 12.345.678-5\n"
            "CUENTA: 1008-0760-0100199653\n"
            "2025-08 2025-08-31 2,536,386 COTIZACION OBLIGATORIA\n"
            "2025-09 2025-09-30 2,640,120 COTIZACION VOLUNTARIA"
        )
        normalized = normalize_certificate_text(sample, "CL", "cert.txt", [])
        sections = {section.id: section for section in normalized.report_sections}

        self.assertIn("movements", sections)
        self.assertEqual(sections["movements"].rows[0][0], "2025-08")
        self.assertGreaterEqual(normalized.global_confidence, 0.8)


if __name__ == "__main__":
    unittest.main()
