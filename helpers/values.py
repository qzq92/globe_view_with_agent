"""Value checks used when merging country records."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config.data import MISSING


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and (not value.strip() or value == MISSING):
        return True
    return False
