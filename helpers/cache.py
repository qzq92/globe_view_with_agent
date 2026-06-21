"""Local JSON cache helpers for API responses."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def cache_is_fresh(path: Path, ttl_seconds: int) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_seconds


def read_cache(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_cache(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
