from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def list_artifacts(dir_path: Path) -> list[Path]:
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.glob("*") if p.is_dir()])


def enforce_limit(base_dir: Path, max_items: int) -> None:
    items = list_artifacts(base_dir)
    overflow = len(items) - max_items
    for old in items[: max(0, overflow)]:
        shutil.rmtree(old, ignore_errors=True)


