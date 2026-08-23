"""REST Countries API record parsing helpers."""

from __future__ import annotations

from typing import Any

from config.data import MEMBERSHIP_LABELS, MISSING


def primary_capital(capitals: list[dict[str, Any]] | None) -> str:
    """Return the primary capital name from a REST Countries capitals list."""
    if not capitals:
        return MISSING
    primary = [
        capital["name"]
        for capital in capitals
        if capital.get("name")
        and (capital.get("attributes") or {}).get("primary")
    ]
    if primary:
        return ", ".join(primary)
    first = capitals[0].get("name")
    return first or MISSING


def organizations_from_api(country: dict[str, Any]) -> str:
    """Return a semicolon-separated organization membership label."""
    memberships = country.get("memberships") or {}
    classification = country.get("classification") or {}
    orgs: list[str] = []

    if classification.get("un_observer"):
        orgs.append("United Nations (Observer State)")
    elif memberships.get("un") or classification.get("un_member"):
        orgs.append("United Nations")

    for key, label in MEMBERSHIP_LABELS.items():
        if key == "un":
            continue
        if memberships.get(key) and label not in orgs:
            orgs.append(label)

    return "; ".join(orgs) if orgs else "None"


def primary_currency(currencies: Any) -> str:
    """Return a human-friendly primary currency label from REST Countries payload."""
    if not currencies:
        return MISSING

    # Handle modern payloads like {"USD": {"name": "United States dollar", "symbol": "$"}}
    if isinstance(currencies, dict):
        for code, value in currencies.items():
            if isinstance(value, dict):
                name = value.get("name")
                symbol = value.get("symbol")
                if name and symbol:
                    return f"{name} ({code}, {symbol})"
                if name:
                    return f"{name} ({code})"
                return str(code)
            if value:
                return f"{value} ({code})"
            return str(code)
        return MISSING

    # Handle list-shaped payloads.
    if isinstance(currencies, list):
        first = currencies[0] if currencies else None
        if isinstance(first, dict):
            code = first.get("code")
            name = first.get("name")
            symbol = first.get("symbol")
            if name and code and symbol:
                return f"{name} ({code}, {symbol})"
            if name and code:
                return f"{name} ({code})"
            if name:
                return str(name)
            if code:
                return str(code)
        if first:
            return str(first)
        return MISSING

    text = str(currencies).strip()
    return text or MISSING
