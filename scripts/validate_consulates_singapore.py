"""Validate curated Singapore consulate data.

This script performs lightweight fact-checking for
``data/consulates_singapore.json``:

- validates the expected JSON shape and required fields
- checks ISO-3 codes against loaded dashboard country data
- checks official links are reachable
- warns if fetched page text does not mention Singapore

Run:

    uv run python scripts/validate_consulates_singapore.py

Use ``--offline`` to skip HTTP checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.paths import CONSULATES_FILE
from config.validation import (
    BOT_BLOCK_HINTS,
    ISO3_RE,
    REQUIRED_FIELDS,
    SINGAPORE_HINTS,
)

import helpers.ssl_patch  # noqa: E402 - initialize SSL before requests

import requests  # noqa: E402
from data_loader import load_country_data  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate data/consulates_singapore.json."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip HTTP reachability and page-content checks.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds for official link checks.",
    )
    return parser.parse_args()


def load_data() -> dict[str, Any]:
    try:
        data = json.loads(CONSULATES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AssertionError(f"Missing dataset: {CONSULATES_FILE}") from None
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Invalid JSON in {CONSULATES_FILE}: {exc}") from exc

    if not isinstance(data, dict):
        raise AssertionError("Dataset must be a JSON object keyed by ISO-3 code.")
    return data


def validate_schema(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_links: dict[str, str] = {}

    for iso3, entry in sorted(data.items()):
        if not ISO3_RE.match(iso3):
            errors.append(f"{iso3}: key must be a three-letter uppercase ISO-3 code.")
        if not isinstance(entry, dict):
            errors.append(f"{iso3}: entry must be an object.")
            continue

        missing = [field for field in REQUIRED_FIELDS if field not in entry]
        if missing:
            errors.append(f"{iso3}: missing required field(s): {', '.join(missing)}")

        for field in REQUIRED_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str):
                errors.append(f"{iso3}.{field}: must be a string.")
                continue
            if field != "note" and not value.strip():
                errors.append(f"{iso3}.{field}: must not be empty.")

        link = entry.get("official_link", "")
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{iso3}.official_link: must be a valid HTTP(S) URL.")
        elif link in seen_links:
            warnings.append(
                f"{iso3}.official_link duplicates {seen_links[link]}: {link}"
            )
        else:
            seen_links[link] = iso3

        address = entry.get("address", "")
        if (
            isinstance(address, str)
            and "singapore" not in address.lower()
            and "official link" not in address.lower()
        ):
            warnings.append(
                f"{iso3}.address does not mention Singapore or official-link fallback."
            )

    return errors, warnings


def validate_iso3_codes(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Check entries match dashboard country ISO-3 codes."""
    df = load_country_data().df
    known_iso3 = set(df["iso3"])
    errors = [iso3 for iso3 in sorted(data) if iso3 not in known_iso3]
    return [f"{iso3}: not found in dashboard country data." for iso3 in errors], []


def check_link(iso3: str, url: str, timeout: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; globe-view-consulate-validator/1.0)"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
    except requests.RequestException as exc:
        if any(hint in str(exc) for hint in BOT_BLOCK_HINTS):
            warnings.append(
                f"{iso3}.official_link closed the automated check connection; "
                "verify manually if this entry changes."
            )
            return errors, warnings
        errors.append(f"{iso3}.official_link unreachable: {exc}")
        return errors, warnings

    if response.status_code in {403, 429, 503}:
        warnings.append(
            f"{iso3}.official_link returned HTTP {response.status_code}; "
            "site may block automated checks or be temporarily unavailable."
        )
        return errors, warnings

    if response.status_code >= 400:
        errors.append(
            f"{iso3}.official_link returned HTTP {response.status_code}: {url}"
        )
        return errors, warnings

    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "text/plain" not in content_type:
        warnings.append(
            f"{iso3}.official_link reachable but content type is {content_type or 'unknown'}."
        )
        return errors, warnings

    try:
        body = response.raw.read(250_000, decode_content=True)
        text = body.decode(response.encoding or "utf-8", errors="ignore").lower()
    except (OSError, UnicodeError, requests.RequestException) as exc:
        warnings.append(f"{iso3}.official_link content could not be inspected: {exc}")
        return errors, warnings

    final_url = response.url.lower()
    if not any(hint in text or hint in final_url for hint in SINGAPORE_HINTS):
        warnings.append(
            f"{iso3}.official_link reachable but page text/URL did not mention Singapore."
        )
    return errors, warnings


def validate_links(data: dict[str, Any], timeout: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for iso3, entry in sorted(data.items()):
        link = entry.get("official_link")
        if not isinstance(link, str) or not link:
            continue
        link_errors, link_warnings = check_link(iso3, link, timeout)
        errors.extend(link_errors)
        warnings.extend(link_warnings)

    return errors, warnings


def print_results(errors: list[str], warnings: list[str]) -> None:
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return

    print("Consulate dataset validation passed.")


def main() -> int:
    args = parse_args()
    data = load_data()

    errors: list[str] = []
    warnings: list[str] = []

    for validate in (validate_schema, validate_iso3_codes):
        found_errors, found_warnings = validate(data)
        errors.extend(found_errors)
        warnings.extend(found_warnings)

    if not args.offline:
        found_errors, found_warnings = validate_links(data, args.timeout)
        errors.extend(found_errors)
        warnings.extend(found_warnings)

    print_results(errors, warnings)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
