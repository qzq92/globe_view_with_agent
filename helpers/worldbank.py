"""World Bank API response helpers."""

from __future__ import annotations


def indicator_map(rows: list[dict]) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows:
        iso3 = row.get("countryiso3code")
        value = row.get("value")
        if iso3 and value is not None and iso3 not in result:
            result[iso3] = value
    return result
