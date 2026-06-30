"""Load and merge country data from the REST Countries v5 API.

REST Countries is the primary source for country facts (area, population,
capital, government type, and organization memberships), using an API key stored
in ``.env`` as ``REST_COUNTRIES_API_KEY``.

When REST Countries does not provide a value, the loader falls back to the
World Bank Open Data API for area, population, and capital. Other unavailable
API values are shown as ``N/A``.
"""

from __future__ import annotations

import helpers.ssl_patch  # noqa: F401 - must run before requests (Windows OpenSSL applink)

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from config.api import (
    AREA_INDICATOR,
    AUTO_REFRESH_CONSULATES,
    CACHE_TTL_SECONDS,
    MAX_CITIES_DISPLAY,
    PAGE_LIMIT,
    POPULATION_INDICATOR,
    REQUEST_TIMEOUT,
    REST_COUNTRIES_API_KEY_ENV,
    REST_COUNTRIES_BASE,
    WORLD_BANK_BASE,
)
from config.data import MISSING, NO_SINGAPORE_MISSION
from config.dashboard import REST_COUNTRIES_API_LABEL, WORLD_BANK_API_LABEL
from config.paths import (
    CONSULATES_FILE,
    ENV_FILE,
    RESTCOUNTRIES_CACHE_FILE,
    WORLDBANK_CACHE_FILE,
)
from helpers.cache import cache_is_fresh, read_cache, write_cache
from helpers.countriesnow import (
    build_normalized_city_lookup,
    fetch_all_cities,
    get_cities_for_country,
)
from helpers.country import organizations_from_api, primary_capital
from helpers.un_protocol import fetch_un_protocol_officials
from helpers.values import is_missing
from helpers.worldbank import indicator_map

_api_key_cache: str | None = None


@dataclass
class CountryDataLoad:
    df: pd.DataFrame
    rest_countries_error: str | None = None
    worldbank_error: str | None = None

    @property
    def banner_messages(self) -> list[str]:
        messages: list[str] = []
        if self.rest_countries_error:
            messages.append(
                f"{REST_COUNTRIES_API_LABEL} is unavailable ({self.rest_countries_error}). "
                "Country details may be incomplete."
            )
            if self.worldbank_error:
                messages.append(
                    f"{WORLD_BANK_API_LABEL} fallback is also unavailable "
                    f"({self.worldbank_error})."
                )
        elif self.df.empty:
            messages.append(
                f"{REST_COUNTRIES_API_LABEL} returned no country data. "
                "Check your API key and network connection."
            )
        return messages


def _get_api_key() -> str:
    global _api_key_cache
    if _api_key_cache is None:
        load_dotenv(ENV_FILE)
        key = os.getenv(REST_COUNTRIES_API_KEY_ENV, "").strip().strip('"').strip("'")
        if not key:
            raise RuntimeError(
                f"{REST_COUNTRIES_API_KEY_ENV} is not set. "
                "Add it to .env before running the app."
            )
        _api_key_cache = key
    return _api_key_cache


def _auth_headers() -> dict[str, str]:
    """Return Bearer authorisation headers for the REST Countries API."""
    return {"Authorization": f"Bearer {_get_api_key()}"}


def _fetch_page(session: requests.Session, offset: int) -> dict[str, Any]:
    response = session.get(
        REST_COUNTRIES_BASE,
        headers=_auth_headers(),
        params={"offset": offset, "limit": PAGE_LIMIT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", True):
        errors = payload.get("errors", [])
        message = errors[0]["message"] if errors else "Unknown REST Countries API error."
        raise ValueError(message)
    return payload["data"]  # type: ignore[return-value]


def _fetch_rest_countries_from_api(session: requests.Session) -> list[dict[str, Any]]:
    """Fetch all countries from REST Countries v5."""
    countries: list[dict[str, Any]] = []
    offset = 0

    while True:
        page = _fetch_page(session, offset)
        countries.extend(page.get("objects", []))
        meta = page.get("meta", {})
        if not meta.get("more"):
            break
        offset += meta.get("count", PAGE_LIMIT)

    return countries


def _worldbank_get_json(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    with requests.Session() as session:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            raise ValueError(f"Unexpected World Bank response shape from {url}.")
        return payload[1] or []  # type: ignore[return-value]


def _fetch_worldbank_from_api() -> dict[str, Any]:
    """Fetch World Bank country metadata and indicators in parallel."""
    requests_spec = [
        ("countries", f"{WORLD_BANK_BASE}/country", {"format": "json", "per_page": 400}),
        (
            "population",
            f"{WORLD_BANK_BASE}/country/all/indicator/{POPULATION_INDICATOR}",
            {"format": "json", "per_page": 20000, "mrnev": 1},
        ),
        (
            "area",
            f"{WORLD_BANK_BASE}/country/all/indicator/{AREA_INDICATOR}",
            {"format": "json", "per_page": 20000, "mrnev": 1},
        ),
    ]
    result: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_worldbank_get_json, url, params): key
            for key, url, params in requests_spec
        }
        for future in as_completed(futures):
            key = futures[future]
            result[key] = future.result()

    return result


def _resolve_rest_countries() -> tuple[list[dict[str, Any]] | None, str | None]:
    """Load REST Countries data from cache or the live API."""
    if cache_is_fresh(RESTCOUNTRIES_CACHE_FILE, CACHE_TTL_SECONDS):
        print("Using cached REST Countries data.")
        return read_cache(RESTCOUNTRIES_CACHE_FILE), None

    try:
        with requests.Session() as session:
            data = _fetch_rest_countries_from_api(session)
            write_cache(RESTCOUNTRIES_CACHE_FILE, data)
            return data, None
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        error = str(exc)
        if RESTCOUNTRIES_CACHE_FILE.exists():
            print(f"API fetch failed ({error}); using cached REST Countries data.")
            return read_cache(RESTCOUNTRIES_CACHE_FILE), error
        print(f"API fetch failed ({error}). Cannot load country data.")
        return None, error


def _resolve_worldbank_raw() -> tuple[dict[str, Any] | None, str | None]:
    """Load World Bank data from cache or the live API."""
    if cache_is_fresh(WORLDBANK_CACHE_FILE, CACHE_TTL_SECONDS):
        print("Using cached World Bank data.")
        return read_cache(WORLDBANK_CACHE_FILE), None

    try:
        data = _fetch_worldbank_from_api()
        write_cache(WORLDBANK_CACHE_FILE, data)
        return data, None
    except (requests.RequestException, ValueError) as exc:
        error = str(exc)
        if WORLDBANK_CACHE_FILE.exists():
            print(f"World Bank fetch failed ({error}); using cached fallback data.")
            return read_cache(WORLDBANK_CACHE_FILE), error
        print(f"World Bank fetch failed ({error}); no fallback data available.")
        return None, error


def _fetch_sources_parallel() -> tuple[
    list[dict[str, Any]] | None,
    str | None,
    dict[str, Any] | None,
    str | None,
]:
    """Fetch REST Countries and World Bank data concurrently."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        rest_future = pool.submit(_resolve_rest_countries)
        wb_future = pool.submit(_resolve_worldbank_raw)
        raw, rest_error = rest_future.result()
        wb_raw, wb_error = wb_future.result()
    return raw, rest_error, wb_raw, wb_error


def _load_consulates(*, refresh_from_mfa: bool = False) -> dict[str, dict[str, Any]]:
    """Return consulate entries keyed by ISO-3 code, or empty dict if file absent.

    Args:
        refresh_from_mfa: If True, attempt to refresh consulate data from
            Singapore MFA website before loading. Defaults to False.
    """
    should_refresh = (
        refresh_from_mfa
        and (
            not CONSULATES_FILE.exists()
            or (time.time() - CONSULATES_FILE.stat().st_mtime) > CACHE_TTL_SECONDS
        )
    )
    if should_refresh:
        try:
            # Import here to avoid circular dependencies
            from helpers.mfa import update_on_startup

            updated = update_on_startup()
            if updated:
                return updated
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Note: Could not refresh consulates from MFA: {exc}")

    if not CONSULATES_FILE.exists():
        return {}
    return json.loads(CONSULATES_FILE.read_text(encoding="utf-8"))


def _worldbank_by_iso3(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build an ISO-3 lookup from World Bank data for fallback fields."""
    population_map = indicator_map(raw.get("population", []))
    area_map = indicator_map(raw.get("area", []))
    by_iso3: dict[str, dict[str, Any]] = {}

    for country in raw.get("countries", []):
        iso3 = country.get("id")
        if not iso3:
            continue
        region = (country.get("region") or {}).get("value", "")
        if region == "Aggregates":
            continue
        by_iso3[iso3] = {
            "name": country.get("name", iso3),
            "capital": country.get("capitalCity") or None,
            "area": area_map.get(iso3),
            "population": population_map.get(iso3),
        }
    return by_iso3


def _apply_worldbank_fallback(
    record: dict[str, Any],
    worldbank: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Fill missing REST Countries fields from World Bank, without overwriting."""
    fallback = worldbank.get(record["iso3"])
    if not fallback:
        return record

    if is_missing(record.get("name")):
        record["name"] = fallback["name"]
    if is_missing(record.get("capital")):
        record["capital"] = fallback["capital"] or MISSING
    if is_missing(record.get("area")):
        record["area"] = fallback["area"]
    if is_missing(record.get("population")):
        record["population"] = fallback["population"]
    return record


def _apply_consulate_info(
    record: dict[str, Any],
    consulates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attach Singapore mission details, or a clear no-mission note."""
    entry = consulates.get(record["iso3"], {})
    if not entry:
        record.update(
            {
                "consulate_name": MISSING,
                "consulate_address": MISSING,
                "consulate_link": MISSING,
                "consulate_note": NO_SINGAPORE_MISSION,
            }
        )
        return record

    record.update(
        {
            "consulate_name": entry.get("mission_name") or MISSING,
            "consulate_address": entry.get("address") or MISSING,
            "consulate_link": entry.get("official_link") or MISSING,
            "consulate_note": entry.get("note") or "",
        }
    )
    return record


def _normalize_country(country: dict[str, Any]) -> dict[str, Any] | None:
    iso3 = (country.get("codes") or {}).get("alpha_3")
    if not iso3:
        return None

    names = country.get("names") or {}
    area = (country.get("area") or {}).get("kilometers")

    return {
        "iso3": iso3,
        "name": names.get("common") or names.get("official") or iso3,
        "area": area,
        "population": country.get("population"),
        "capital": primary_capital(country.get("capitals")),
        "government": country.get("government_type") or MISSING,
        "head_of_state": MISSING,
        "head_of_government": MISSING,
        "foreign_minister": MISSING,
        "major_cities": MISSING,  # Will be populated from CountriesNow
        "news_outlet": MISSING,
        "un_organizations": organizations_from_api(country),
    }


def load_country_data() -> CountryDataLoad:
    """Return merged country data and any API connection errors."""
    raw, rest_countries_error, wb_raw, worldbank_error = _fetch_sources_parallel()
    worldbank = _worldbank_by_iso3(wb_raw) if wb_raw else {}
    consulates = _load_consulates(refresh_from_mfa=AUTO_REFRESH_CONSULATES)

    if raw is None:
        if worldbank:
            records = [
                _apply_worldbank_fallback(
                    {
                        "iso3": iso3,
                        "name": entry.get("name", iso3),
                        "area": entry.get("area"),
                        "population": entry.get("population"),
                        "capital": entry.get("capital") or MISSING,
                        "government": MISSING,
                        "head_of_state": MISSING,
                        "head_of_government": MISSING,
                        "foreign_minister": MISSING,
                        "major_cities": MISSING,
                        "news_outlet": MISSING,
                        "un_organizations": "None",
                    },
                    worldbank,
                )
                for iso3, entry in worldbank.items()
            ]
        else:
            records = [
                _apply_worldbank_fallback(
                    {
                        "iso3": iso3,
                        "name": iso3,
                        "area": None,
                        "population": None,
                        "capital": MISSING,
                        "government": MISSING,
                        "head_of_state": MISSING,
                        "head_of_government": MISSING,
                        "foreign_minister": MISSING,
                        "major_cities": MISSING,
                        "news_outlet": MISSING,
                        "un_organizations": "None",
                    },
                    worldbank,
                )
                for iso3 in consulates
            ]
    else:
        records = []
        for country in raw:
            record = _normalize_country(country)
            if record:
                records.append(_apply_worldbank_fallback(record, worldbank))

    records = [_apply_consulate_info(record, consulates) for record in records]

    country_names = [str(record.get("name", "")) for record in records]
    un_officials: dict[str, dict[str, str]] = {}
    cities_data: dict[str, list[str]] = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        un_future = pool.submit(fetch_un_protocol_officials)
        cities_future = pool.submit(
            fetch_all_cities,
            country_names,
            MAX_CITIES_DISPLAY,
        )

        print("Fetching officials from UN Protocol list...")
        try:
            un_officials = un_future.result()
            if un_officials:
                print(f"Loaded UN officials for {len(un_officials)} countries")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Could not fetch officials from UN Protocol list: {exc}")
            un_officials = {}

        print("Fetching major cities from CountriesNow API...")
        try:
            cities_data = cities_future.result()
            if cities_data:
                print(f"Loaded cities for {len(cities_data)} countries")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Could not fetch cities from CountriesNow: {exc}")
            cities_data = {}

    for record in records:
        entry = un_officials.get(record["iso3"], {})
        record["head_of_state"] = entry.get("head_of_state") or MISSING
        record["head_of_government"] = entry.get("head_of_government") or MISSING
        record["foreign_minister"] = entry.get("foreign_minister") or MISSING

    df = pd.DataFrame.from_records(records)
    if not df.empty and "name" in df.columns:
        normalized_city_lookup = build_normalized_city_lookup(cities_data)
        df["major_cities"] = df["name"].map(
            lambda name: get_cities_for_country(
                cities_data,
                str(name),
                normalized_city_lookup,
            )
        )

    if df.empty:
        return CountryDataLoad(
            df=df,
            rest_countries_error=rest_countries_error,
            worldbank_error=worldbank_error,
        )
    return CountryDataLoad(
        df=df.sort_values("name").reset_index(drop=True),
        rest_countries_error=rest_countries_error,
        worldbank_error=worldbank_error,
    )


if __name__ == "__main__":
    result = load_country_data()
    print(f"Loaded {len(result.df)} countries.")
    if result.banner_messages:
        for message in result.banner_messages:
            print(f"Warning: {message}")
    print(result.df.head(10).to_string(index=False))
