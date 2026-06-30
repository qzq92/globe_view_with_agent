"""MFA mission fetch/update helpers."""

from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

import helpers.ssl_patch  # noqa: F401  # pylint: disable=unused-import
import requests

from config.paths import CONSULATES_FILE, DATA_DIR

MFA_REPRESENTATIVES_URL = (
    "https://www.mfa.gov.sg/visiting-singapore/foreign-representatives-to-singapore/"
)
MFA_PDF_URL = (
    "https://isomer-user-content.by.gov.sg/262/ffa36ae4-9016-4e68-a1a9-efc403d247b5/"
    "Dipconopen_7May2026.pdf"
)

COUNTRY_NAME_TO_ISO3: dict[str, str] = {
    "algeria": "DZA",
    "argentina": "ARG",
    "armenia": "ARM",
    "australia": "AUS",
    "austria": "AUT",
    "bahamas": "BHS",
    "bahrain": "BHR",
    "bangladesh": "BGD",
    "belarus": "BLR",
    "belgium": "BEL",
    "benin": "BEN",
    "bhutan": "BTN",
    "bosnia and herzegovina": "BIH",
    "botswana": "BWA",
    "brazil": "BRA",
    "brunei darussalam": "BRN",
    "bulgaria": "BGR",
    "burundi": "BDI",
    "cambodia": "KHM",
    "canada": "CAN",
    "chile": "CHL",
    "china": "CHN",
    "colombia": "COL",
    "congo": "COG",
    "congo, the democratic republic": "COD",
    "costa rica": "CRI",
    "croatia": "HRV",
    "cuba": "CUB",
    "cyprus": "CYP",
    "czech republic": "CZE",
    "denmark": "DNK",
    "djibouti": "DJI",
    "ecuador": "ECU",
    "egypt": "EGY",
    "el salvador": "SLV",
    "equatorial guinea": "GNQ",
    "eritrea": "ERI",
    "estonia": "EST",
    "ethiopia": "ETH",
    "finland": "FIN",
    "france": "FRA",
    "gabon": "GAB",
    "georgia": "GEO",
    "germany": "DEU",
    "greece": "GRC",
    "hungary": "HUN",
    "iceland": "ISL",
    "india": "IND",
    "indonesia": "IDN",
    "iran": "IRN",
    "iraq": "IRQ",
    "ireland": "IRL",
    "israel": "ISR",
    "italy": "ITA",
    "japan": "JPN",
    "jordan": "JOR",
    "kazakhstan": "KAZ",
    "kenya": "KEN",
    "kuwait": "KWT",
    "kyrgyzstan": "KGZ",
    "laos": "LAO",
    "latvia": "LVA",
    "lesotho": "LSO",
    "lithuania": "LTU",
    "luxembourg": "LUX",
    "madagascar": "MDG",
    "malawi": "MWI",
    "malaysia": "MYS",
    "maldives": "MDV",
    "mauritius": "MUS",
    "mexico": "MEX",
    "mongolia": "MNG",
    "morocco": "MAR",
    "mozambique": "MOZ",
    "myanmar": "MMR",
    "nepal": "NPL",
    "netherlands": "NLD",
    "new zealand": "NZL",
    "nigeria": "NGA",
    "north macedonia": "MKD",
    "norway": "NOR",
    "oman": "OMN",
    "pakistan": "PAK",
    "panama": "PAN",
    "papua new guinea": "PNG",
    "peru": "PER",
    "philippines": "PHL",
    "poland": "POL",
    "portugal": "PRT",
    "qatar": "QAT",
    "romania": "ROU",
    "russia": "RUS",
    "rwanda": "RWA",
    "saudi arabia": "SAU",
    "senegal": "SEN",
    "serbia": "SRB",
    "seychelles": "SYC",
    "sierra leone": "SLE",
    "singapore": "SGP",
    "slovakia": "SVK",
    "slovenia": "SVN",
    "solomon islands": "SLB",
    "south africa": "ZAF",
    "south korea": "KOR",
    "spain": "ESP",
    "sri lanka": "LKA",
    "sudan": "SDN",
    "sweden": "SWE",
    "switzerland": "CHE",
    "tajikistan": "TJK",
    "tanzania": "TZA",
    "thailand": "THA",
    "timor-leste": "TLS",
    "turkey": "TUR",
    "turkiye": "TUR",
    "uae": "ARE",
    "uganda": "UGA",
    "ukraine": "UKR",
    "united arab emirates": "ARE",
    "united kingdom": "GBR",
    "united states": "USA",
    "united states of america": "USA",
    "uzbekistan": "UZB",
    "vietnam": "VNM",
    "viet nam": "VNM",
    "yemen": "YEM",
    "zambia": "ZMB",
    "zimbabwe": "ZWE",
}


def normalize_country_name(name: str) -> str:
    """Normalize country name for ISO3 lookup."""
    normalized = name.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[,\(\)].*$", "", normalized)
    normalized = normalized.replace("the ", "")
    return normalized.strip()


def country_name_to_iso3(name: str) -> str | None:
    """Convert country name to ISO3 code."""
    normalized = normalize_country_name(name)
    if normalized in COUNTRY_NAME_TO_ISO3:
        return COUNTRY_NAME_TO_ISO3[normalized]
    for key, iso3 in COUNTRY_NAME_TO_ISO3.items():
        if key in normalized or normalized in key:
            return iso3
    return None


def fetch_mfa_representatives_page() -> str | None:
    """Fetch the MFA foreign representatives HTML page."""
    try:
        response = requests.get(
            MFA_REPRESENTATIVES_URL,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"Failed to fetch MFA page: {exc}")
        return None


def parse_representatives_from_html(html: str) -> dict[str, dict[str, Any]]:
    """Parse the MFA HTML to extract country mission information."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    missions: dict[str, dict[str, Any]] = {}
    country_links = soup.find_all(
        "a",
        href=re.compile(r"/visiting-singapore/foreign-representatives-to-singapore/"),
    )

    for link in country_links:
        country_name = link.get_text(strip=True)
        if not country_name or country_name.lower() in ["filter results", "access full list"]:
            continue

        iso3 = country_name_to_iso3(country_name)
        if not iso3:
            print(f"Warning: Could not map '{country_name}' to ISO3 code")
            continue

        href = link.get("href", "")
        detail_url = f"https://www.mfa.gov.sg{href}" if href.startswith("/") else href

        missions[iso3] = {
            "mission_name": f"Mission of {country_name}",
            "address": "See official link for address",
            "official_link": detail_url,
            "note": f"Parsed from MFA directory for {country_name}",
        }
    return missions


def fetch_mfa_pdf() -> bytes | None:
    """Fetch the MFA Diplomatic and Consular List PDF."""
    try:
        response = requests.get(
            MFA_PDF_URL,
            timeout=60,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as exc:
        print(f"Failed to fetch MFA PDF: {exc}")
        return None


def parse_countries_from_pdf(pdf_bytes: bytes) -> dict[str, dict[str, Any]]:
    """Extract country names from MFA PDF and map to ISO3 codes."""
    from pypdf import PdfReader

    missions: dict[str, dict[str, Any]] = {}
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        full_text = "\n".join((page.extract_text() or "") for page in reader.pages)
        lines = full_text.split("\n")
        for i, line in enumerate(lines):
            line_clean = line.strip().upper()
            if any(
                skip in line_clean
                for skip in [
                    "DIPLOMATIC",
                    "CONSULAR",
                    "MISSIONS",
                    "INTERNATIONAL",
                    "ORGANISATIONS",
                    "ORDER OF PRECEDENCE",
                    "CONTENTS",
                    "PART I",
                    "PART II",
                    "PART III",
                    "PART IV",
                ]
            ):
                continue

            if len(line_clean) > 2 and len(line_clean) < 40 and line_clean.isupper():
                context = " ".join(lines[i : i + 3]).lower()
                if any(
                    keyword in context
                    for keyword in [
                        "embassy",
                        "high commission",
                        "chancery",
                        "diplomatic relations",
                        "ambassador",
                    ]
                ):
                    country_name = line.strip()
                    iso3 = country_name_to_iso3(country_name)
                    if iso3 and iso3 not in missions:
                        missions[iso3] = {
                            "mission_name": f"Mission of {country_name.title()}",
                            "address": "See MFA directory for address",
                            "official_link": (
                                "https://www.mfa.gov.sg/visiting-singapore/"
                                f"foreign-representatives-to-singapore/{country_name.lower().replace(' ', '-')}"
                            ),
                            "note": f"Parsed from MFA PDF for {country_name.title()}",
                        }
                        print(f"  Found from PDF: {country_name.title()} ({iso3})")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Error parsing PDF: {exc}")
    return missions


def load_existing_consulates() -> dict[str, dict[str, Any]]:
    """Load existing consulates data if available."""
    if not CONSULATES_FILE.exists():
        return {}
    try:
        return json.loads(CONSULATES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Could not load existing consulates: {exc}")
        return {}


def merge_missions(
    existing: dict[str, dict[str, Any]],
    fetched: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Merge fetched missions with existing data, preserving richer existing data."""
    merged = dict(existing)
    for iso3, mission in fetched.items():
        if iso3 in merged:
            if merged[iso3].get("address", "").startswith("See official"):
                merged[iso3]["official_link"] = mission["official_link"]
        else:
            merged[iso3] = mission
            print(f"Adding new mission: {iso3} - {mission['mission_name']}")
    return merged


def save_consulates(data: dict[str, dict[str, Any]]) -> bool:
    """Save consulates data to JSON file."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONSULATES_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except OSError as exc:
        print(f"Failed to save consulates: {exc}")
        return False


def fetch_and_update() -> dict[str, dict[str, Any]] | None:
    """Fetch MFA data and update consulates file."""
    print("Fetching MFA foreign representatives data...")
    fetched_missions: dict[str, dict[str, Any]] = {}

    print("Trying MFA PDF...")
    pdf_bytes = fetch_mfa_pdf()
    if pdf_bytes:
        print("Parsing PDF for country missions...")
        pdf_missions = parse_countries_from_pdf(pdf_bytes)
        if pdf_missions:
            fetched_missions.update(pdf_missions)
            print(f"Found {len(pdf_missions)} missions from MFA PDF")

    print("Checking MFA website...")
    html = fetch_mfa_representatives_page()
    if html:
        html_missions = parse_representatives_from_html(html)
        for iso3, mission in html_missions.items():
            if iso3 not in fetched_missions:
                fetched_missions[iso3] = mission
            elif "mfa.gov.sg" in mission.get("official_link", ""):
                fetched_missions[iso3]["official_link"] = mission["official_link"]
        print(f"Found {len(html_missions)} missions from MFA website")

    if not fetched_missions:
        print("Failed to fetch from any MFA source")
        return None

    print(f"Total unique missions found: {len(fetched_missions)}")
    existing = load_existing_consulates()
    print(f"Loaded {len(existing)} existing missions")
    merged = merge_missions(existing, fetched_missions)
    print(f"Total missions after merge: {len(merged)}")

    if save_consulates(merged):
        print(f"Successfully updated {CONSULATES_FILE}")
        return merged
    return None


def update_on_startup() -> dict[str, dict[str, Any]]:
    """Update consulates on app startup, falling back to existing data."""
    fresh = fetch_and_update()
    if fresh is not None:
        return fresh
    existing = load_existing_consulates()
    if existing:
        print("Using existing consulates data (fetch failed)")
        return existing
    return {}

