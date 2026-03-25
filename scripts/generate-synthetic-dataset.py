from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.append(str((Path(__file__).resolve().parents[1] / "services" / "ocr-api").resolve()))

from app.services.synthetic_documents import build_manifest_entry, generate_synthetic_record, render_synthetic_document_bytes


DEFAULT_FAMILIES = ("identity", "passport", "driver_license", "certificate")
DEFAULT_COUNTRIES = ("CL", "PE", "CO")
REGISTRY_PATH = Path(".data/dataset-registry.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic OCR training/evaluation documents.")
    parser.add_argument("output", help="Output folder for generated dataset")
    parser.add_argument("--families", default=",".join(DEFAULT_FAMILIES), help="Comma-separated families to generate")
    parser.add_argument("--countries", default=",".join(DEFAULT_COUNTRIES), help="Comma-separated countries to generate")
    parser.add_argument("--count-per-combination", type=int, default=24, help="Synthetic documents per family/country combination")
    parser.add_argument("--conditions", default="", help="Optional comma-separated capture conditions to cycle")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    parser.add_argument("--register", action="store_true", help="Register dataset in local dataset registry")
    return parser.parse_args()


def _load_registry() -> list[dict[str, object]]:
    if not REGISTRY_PATH.exists():
        return []
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _save_registry(entries: list[dict[str, object]]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(entries, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    families = tuple(part.strip() for part in args.families.split(",") if part.strip())
    countries = tuple(part.strip().upper() for part in args.countries.split(",") if part.strip())
    conditions = tuple(part.strip() for part in args.conditions.split(",") if part.strip())
    manifest_entries: list[dict[str, object]] = []

    counter = 0
    for family in families:
        if family == "passport":
            family_countries = tuple(dict.fromkeys([*countries, "CHL", "PER", "COL"]))
        elif family == "certificate":
            family_countries = ("CL",)
        else:
            family_countries = countries
        for country in family_countries:
            for index in range(args.count_per_combination):
                condition = conditions[index % len(conditions)] if conditions else None
                record = generate_synthetic_record(family, country, counter + index, condition=condition, seed=args.seed)
                filename = f"{record.filename_stem}.png"
                (images_dir / filename).write_bytes(render_synthetic_document_bytes(record))
                manifest_entries.append(build_manifest_entry(record, f"images/{filename}"))
            counter += args.count_per_combination

    manifest_path = output_dir / "manifest.jsonl"
    manifest_path.write_text("\n".join(json.dumps(entry, ensure_ascii=True) for entry in manifest_entries), encoding="utf-8")

    summary = {
        "dataset": output_dir.name,
        "documents": len(manifest_entries),
        "families": sorted(str(entry["family"]) for entry in manifest_entries),
        "countries": sorted(str(entry["country"]) for entry in manifest_entries),
        "manifest": str(manifest_path).replace("\\", "/"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")

    if args.register:
        registry = _load_registry()
        registry = [entry for entry in registry if entry.get("name") != output_dir.name]
        registry.insert(
            0,
            {
                "name": output_dir.name,
                "path": str(output_dir).replace("\\", "/"),
                "manifest": str(manifest_path).replace("\\", "/"),
                "documents": len(manifest_entries),
                "families": summary["families"],
                "countries": summary["countries"],
                "synthetic": True,
                "benchmark_profiles": sorted(str(entry.get("benchmark_profile") or "unspecified") for entry in manifest_entries),
                "splits": sorted(str(entry.get("split") or "unspecified") for entry in manifest_entries),
            },
        )
        _save_registry(registry)

    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
