from __future__ import annotations

import argparse
import json
from pathlib import Path


REGISTRY_PATH = Path(".data/dataset-registry.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register an OCR dataset manifest in the local registry.")
    parser.add_argument("name", help="Dataset name")
    parser.add_argument("manifest", help="Path to manifest.jsonl")
    parser.add_argument("--synthetic", action="store_true", help="Mark dataset as synthetic")
    parser.add_argument("--source-dataset", default=None, help="Optional upstream dataset name, e.g. MIDV-2020 or DocXPand-25k")
    parser.add_argument("--format", default="manifest", help="Dataset format label")
    return parser.parse_args()


def load_registry() -> list[dict[str, object]]:
    if not REGISTRY_PATH.exists():
        return []
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(entries: list[dict[str, object]]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(entries, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    entries = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    capture_conditions = sorted({str(entry.get("capture_condition") or "unknown") for entry in entries})
    splits = sorted({str(entry.get("split") or "unspecified") for entry in entries})
    benchmark_profiles = sorted({str(entry.get("benchmark_profile") or "unspecified") for entry in entries})
    registry = [entry for entry in load_registry() if entry.get("name") != args.name]
    registry.insert(
        0,
        {
            "name": args.name,
            "manifest": str(manifest_path).replace("\\", "/"),
            "path": str(manifest_path.parent).replace("\\", "/"),
            "documents": len(entries),
            "families": sorted(str(entry.get("family") or "unknown") for entry in entries),
            "countries": sorted(str(entry.get("country") or "XX") for entry in entries),
            "synthetic": args.synthetic,
            "format": args.format,
            "source_dataset": args.source_dataset,
            "capture_conditions": capture_conditions,
            "splits": splits,
            "benchmark_profiles": benchmark_profiles,
        },
    )
    save_registry(registry)
    print(json.dumps(registry[0], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
