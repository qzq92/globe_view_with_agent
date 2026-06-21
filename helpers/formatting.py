"""Display formatting helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from config.data import MISSING


def format_number(value: Any, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return MISSING
    try:
        return f"{float(value):,.0f}{suffix}"
    except (TypeError, ValueError):
        return str(value)
