from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_runtime_env() -> None:
    current = Path(__file__).resolve()
    search_roots = [current.parent, *current.parents]
    visited: set[Path] = set()

    for root in search_roots:
        if root in visited:
            continue
        visited.add(root)
        for filename in (".env", ".env.local"):
            candidate = root / filename
            if candidate.exists():
                load_dotenv(candidate, override=False)
