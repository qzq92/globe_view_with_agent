"""REST Countries API record parsing helpers."""

from __future__ import annotations

from typing import Any

from config.data import MEMBERSHIP_LABELS, MISSING


def primary_capital(capitals: list[dict[str, Any]] | None) -> str:
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


def leader_from_api(leaders: list[dict[str, Any]] | None) -> str | None:
    if not leaders:
        return None
    first = leaders[0]
    if isinstance(first, dict) and first.get("message"):
        return None
    names: list[str] = []
    for entry in leaders:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("full_name")
        title = entry.get("title") or entry.get("role")
        if name and title:
            names.append(f"{title} {name}")
        elif name:
            names.append(name)
    return "; ".join(names) if names else None


def organizations_from_api(country: dict[str, Any]) -> str:
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
