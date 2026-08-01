"""Fetch and normalize satellite positions and open metadata."""

from __future__ import annotations

import io
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from skyfield.api import EarthSatellite, load, wgs84

from config.api import REQUEST_TIMEOUT
from config.paths import CACHE_DIR

TLE_CACHE_TTL_SECONDS = 12 * 60 * 60
UCS_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

SATELLITE_CACHE_DIR = CACHE_DIR / "satellite"
_TIMESCALE = None
_TLE_OBJECT_CACHE: dict[str, tuple[str, list[EarthSatellite]]] = {}
_UCS_METADATA_CACHE: tuple[str, pd.DataFrame] | None = None

CELESTRAK_URLS = {
    "Space Stations": (
        "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"
    ),
    "Weather": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
}

# UCS open-source metadata (tab-separated text export)
UCS_DB_URL = (
    "https://s3.amazonaws.com/ucs-documents/nuclear-weapons/sat-database/"
    "1-1-2023-update/UCS-Satellite-Database-1-1-2023.txt"
)


def _is_fresh(path: Path, ttl_seconds: int) -> bool:
    if not path.exists():
        return False
    age_seconds = (datetime.now(UTC) - datetime.fromtimestamp(path.stat().st_mtime, UTC)).total_seconds()
    return age_seconds < ttl_seconds


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fetch_tle_text(category: str, url: str) -> str:
    cache_file = SATELLITE_CACHE_DIR / f"tle_{category.lower().replace(' ', '_')}.txt"
    if _is_fresh(cache_file, TLE_CACHE_TTL_SECONDS):
        return _read_text(cache_file)

    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    _write_text(cache_file, response.text)
    return response.text


def _load_ucs_metadata() -> pd.DataFrame:
    global _UCS_METADATA_CACHE
    cache_file = SATELLITE_CACHE_DIR / "ucs_satellite_database.tsv"
    raw_text: str
    if _is_fresh(cache_file, UCS_CACHE_TTL_SECONDS):
        raw_text = _read_text(cache_file)
    else:
        response = requests.get(UCS_DB_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        raw_text = response.text
        _write_text(cache_file, raw_text)

    text_hash = hashlib.sha1(raw_text.encode("utf-8", errors="ignore")).hexdigest()
    if _UCS_METADATA_CACHE and _UCS_METADATA_CACHE[0] == text_hash:
        return _UCS_METADATA_CACHE[1]

    df = pd.read_csv(
        io.StringIO(raw_text),
        sep="\t",
        encoding="latin1",
        on_bad_lines="skip",
    )
    df.columns = df.columns.str.strip()
    if "NORAD Number" not in df.columns:
        return pd.DataFrame()

    cols = [
        "NORAD Number",
        "Country of Operator/Owner",
        "Operator/Owner",
        "Users",
        "Purpose",
    ]
    available_cols = [column for column in cols if column in df.columns]
    meta = df[available_cols].copy()
    meta["NORAD Number"] = pd.to_numeric(meta["NORAD Number"], errors="coerce").astype("Int64")
    meta = meta.rename(
        columns={
            "NORAD Number": "norad_id",
            "Country of Operator/Owner": "country",
            "Operator/Owner": "owner",
            "Users": "users",
            "Purpose": "purpose",
        }
    )
    meta = meta.dropna(subset=["norad_id"]).drop_duplicates(subset=["norad_id"])
    _UCS_METADATA_CACHE = (text_hash, meta)
    return meta


def _get_timescale():
    global _TIMESCALE
    if _TIMESCALE is None:
        _TIMESCALE = load.timescale()
    return _TIMESCALE


def _get_satellites_for_tle(category: str, tle_text: str) -> list[EarthSatellite]:
    """Parse and cache EarthSatellite objects per category/TLE content hash."""
    tle_hash = hashlib.sha1(tle_text.encode("utf-8", errors="ignore")).hexdigest()
    cached = _TLE_OBJECT_CACHE.get(category)
    if cached and cached[0] == tle_hash:
        return cached[1]

    lines = [line.strip() for line in tle_text.splitlines() if line.strip()]
    satellites: list[EarthSatellite] = []
    index = 0

    while index < len(lines) - 2:
        name, line1, line2 = lines[index], lines[index + 1], lines[index + 2]
        if not line1.startswith("1 ") or not line2.startswith("2 "):
            index += 1
            continue
        try:
            satellites.append(EarthSatellite(line1, line2, name, _get_timescale()))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        index += 3

    _TLE_OBJECT_CACHE[category] = (tle_hash, satellites)
    return satellites


def _tle_to_records(category: str, satellites: list[EarthSatellite], now) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for satellite in satellites:
        try:
            subpoint = wgs84.subpoint(satellite.at(now))
            records.append(
                {
                    "name": satellite.name,
                    "norad_id": satellite.model.satnum,
                    "category": category,
                    "lat": subpoint.latitude.degrees,
                    "lon": subpoint.longitude.degrees,
                    "elevation_km": subpoint.elevation.km,
                }
            )
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return records


def get_satellite_positions() -> pd.DataFrame:
    """Return current satellite positions with UCS metadata enrichment."""
    all_records: list[dict[str, object]] = []
    now = _get_timescale().now()

    for category, url in CELESTRAK_URLS.items():
        try:
            tle_text = _fetch_tle_text(category, url)
            satellites = _get_satellites_for_tle(category, tle_text)
            all_records.extend(_tle_to_records(category, satellites, now))
        except requests.RequestException:
            continue

    if not all_records:
        return pd.DataFrame(
            columns=[
                "name",
                "norad_id",
                "category",
                "lat",
                "lon",
                "elevation_km",
                "country",
                "owner",
                "purpose",
                "users",
            ]
        )

    satellites = pd.DataFrame(all_records)
    satellites["norad_id"] = pd.to_numeric(satellites["norad_id"], errors="coerce").astype("Int64")

    try:
        metadata = _load_ucs_metadata()
    except requests.RequestException:
        metadata = pd.DataFrame()

    if not metadata.empty:
        satellites = satellites.merge(metadata, on="norad_id", how="left")
    else:
        satellites["country"] = None
        satellites["owner"] = None
        satellites["purpose"] = None
        satellites["users"] = None

    for column in ("country", "owner", "purpose", "users"):
        satellites[column] = satellites[column].fillna("Unknown")

    return satellites
