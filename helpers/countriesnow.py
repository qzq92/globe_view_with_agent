"""CountriesNow API fetcher for city data and country codes.

This module fetches free country data from the CountriesNow API:
- Cities by country
- Country codes (ISO2, dial codes)
- Population data

API: https://countriesnow.space
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from config.api import CACHE_TTL_SECONDS, COUNTRIESNOW_BASE, REQUEST_TIMEOUT
from config.paths import CACHE_DIR
from helpers.cache import cache_is_fresh, read_cache, write_cache

COUNTRIESNOW_CACHE_FILE = CACHE_DIR / "countriesnow_cities.json"
COUNTRIESNOW_CODES_CACHE_FILE = CACHE_DIR / "countriesnow_codes.json"

COUNTRY_ALIASES = {
    "united states of america": "united states",
    "united kingdom of great britain and northern ireland": "united kingdom",
    "korea, republic of": "south korea",
    "republic of korea": "south korea",
    "korea, democratic people's republic of": "north korea",
    "democratic people's republic of korea": "north korea",
    "cote d'ivoire": "ivory coast",
    "côte d'ivoire": "ivory coast",
    "russian federation": "russia",
    "bolivia (plurinational state of)": "bolivia",
    "iran (islamic republic of)": "iran",
    "venezuela (bolivarian republic of)": "venezuela",
    "syrian arab republic": "syria",
    "lao people's democratic republic": "laos",
    "viet nam": "vietnam",
    "brunei darussalam": "brunei",
    "micronesia (federated states of)": "micronesia",
    "tanzania, united republic of": "tanzania",
}


def _normalize_country_name(country_name: str) -> str:
    normalized = " ".join(country_name.lower().strip().split())
    return COUNTRY_ALIASES.get(normalized, normalized)


def build_normalized_city_lookup(
    cities_data: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Build normalized-name lookup for city results."""
    return {
        _normalize_country_name(name): values for name, values in cities_data.items()
    }


def _fetch_cities_for_country(country: str) -> list[str] | None:
    """Fetch cities for a single country from CountriesNow API."""
    url = f"{COUNTRIESNOW_BASE}/cities"
    try:
        response = requests.post(
            url,
            json={"country": country},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error") is False:
            return data.get("data", [])
        return None
    except requests.RequestException:
        return None


def fetch_all_cities(
    country_names: list[str],
    max_cities: int = 5,
) -> dict[str, list[str]]:
    """Fetch cities for multiple countries and cache results.

    Args:
        country_names: List of country names to fetch cities for
        max_cities: Maximum number of cities to store per country

    Returns:
        Dictionary mapping country names to lists of cities
    """
    # Check cache first
    if cache_is_fresh(COUNTRIESNOW_CACHE_FILE, CACHE_TTL_SECONDS):
        cached = read_cache(COUNTRIESNOW_CACHE_FILE)
        if cached:
            return cached

    result: dict[str, list[str]] = {}
    if COUNTRIESNOW_CACHE_FILE.exists():
        cached = read_cache(COUNTRIESNOW_CACHE_FILE)
        if isinstance(cached, dict):
            result.update(cached)

    unique_countries = list(dict.fromkeys(country_names))
    missing = [country for country in unique_countries if country and country not in result]

    if missing:
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = {
                pool.submit(_fetch_cities_for_country, country): country
                for country in missing
            }
            for future in as_completed(futures):
                country = futures[future]
                try:
                    cities = future.result()
                except Exception:  # pylint: disable=broad-exception-caught
                    cities = None
                if cities:
                    result[country] = cities[:max_cities]

    # Save to cache
    write_cache(COUNTRIESNOW_CACHE_FILE, result)
    return result


def fetch_country_codes() -> dict[str, dict[str, str]]:
    """Fetch ISO2 codes and dial codes for all countries.

    Returns:
        Dictionary mapping country names to dict with 'iso2' and 'dial_code'
    """
    # Check cache first
    if cache_is_fresh(COUNTRIESNOW_CODES_CACHE_FILE, CACHE_TTL_SECONDS):
        cached = read_cache(COUNTRIESNOW_CODES_CACHE_FILE)
        if cached:
            return cached

    url = f"{COUNTRIESNOW_BASE}/codes"
    result: dict[str, dict[str, str]] = {}

    try:
        with requests.Session() as session:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            if data.get("error") is False:
                for item in data.get("data", []):
                    name = item.get("name", "")
                    if name:
                        result[name] = {
                            "iso2": item.get("code", ""),
                            "dial_code": item.get("dial_code", ""),
                        }

        # Save to cache
        write_cache(COUNTRIESNOW_CODES_CACHE_FILE, result)
    except requests.RequestException:
        pass

    return result


def get_cities_for_country(
    cities_data: dict[str, list[str]],
    country_name: str,
    normalized_lookup: dict[str, list[str]] | None = None,
) -> str:
    """Format cities for display.

    Args:
        cities_data: Dictionary from fetch_all_cities
        country_name: Country name to look up

    Returns:
        Comma-separated city names or "N/A"
    """
    cities = cities_data.get(country_name, [])
    if not cities:
        lookup = normalized_lookup or build_normalized_city_lookup(cities_data)
        cities = lookup.get(_normalize_country_name(country_name), [])
    if cities:
        return ", ".join(cities)
    return "N/A"


def get_country_code_info(
    codes_data: dict[str, dict[str, str]],
    country_name: str,
) -> dict[str, str]:
    """Get country code info for a specific country.

    Args:
        codes_data: Dictionary from fetch_country_codes
        country_name: Country name to look up

    Returns:
        Dict with 'iso2' and 'dial_code' or empty values
    """
    return codes_data.get(country_name, {"iso2": "", "dial_code": ""})
