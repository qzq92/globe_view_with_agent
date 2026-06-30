"""Fetch and parse UN Protocol heads of state/government/foreign affairs list."""

from __future__ import annotations

import re
from io import BytesIO

import requests
from pypdf import PdfReader

from config.api import CACHE_TTL_SECONDS, REQUEST_TIMEOUT, UN_PROTOCOL_PDF_URL
from config.paths import CACHE_DIR
from helpers.cache import cache_is_fresh, read_cache, write_cache

UN_PROTOCOL_CACHE_FILE = CACHE_DIR / "un_protocol_officials.json"

_COUNTRY_NAME = re.compile(
    r"^(?!COUNTRY HEAD|Full Title|HEADS OF|MINISTERS FOR|UNITED NATIONS|"
    r"Protocol and Liaison|PUBLIC LIST|Date:|Date of|AFFAIRS|MINISTER FOR)"
    r"([A-Z][A-Z0-9 ,.'()&\-]+)$",
    re.MULTILINE,
)
_OFFICIAL_RE = re.compile(
    r"(?:His|Her|Their)\s+(?:Excellency|Royal Highness|Majesty)\s*\n\s*"
    r"(?:(?:Mr|Ms|Mrs|Dr|Sir|Dame|King|Queen)\.?\s+)?([^\n]+)"
    r"|(?:Son|Sa)\s+(?:Excellence|Majest[eé])\s*\n\s*"
    r"(?:(?:Monsieur|Madame|Don)\s+)?([^\n]+)"
    r"|Excelent[ií]simo\s+Señor\s*\n\s*([^\n]+)"
    r"|Su Majestad\s*\n\s*(?:Don\s+)?([^\n]+)",
    re.IGNORECASE,
)
_DATE_OF_APPOINTMENT = re.compile(r"^Date of Appointment\b", re.MULTILINE | re.IGNORECASE)

UN_COUNTRY_ALIASES: dict[str, str] = {
    "united states of america": "USA",
    "united kingdom of great britain and northern ireland": "GBR",
    "russian federation": "RUS",
    "viet nam": "VNM",
    "republic of korea": "KOR",
    "korea, republic of": "KOR",
    "korea, democratic people's republic of": "PRK",
    "democratic people's republic of korea": "PRK",
    "iran (islamic republic of)": "IRN",
    "syrian arab republic": "SYR",
    "lao people's democratic republic": "LAO",
    "bolivia (plurinational state of)": "BOL",
    "venezuela (bolivarian republic of)": "VEN",
    "tanzania, united republic of": "TZA",
    "moldova, republic of": "MDA",
    "north macedonia, republic of": "MKD",
    "micronesia (federated states of)": "FSM",
    "congo, democratic republic of the": "COD",
    "congo, republic of the": "COG",
    "cote d'ivoire": "CIV",
    "côte d'ivoire": "CIV",
    "brunei darussalam": "BRN",
    "timor-leste": "TLS",
    "holy see": "VAT",
    "state of palestine": "PSE",
    "united republic of tanzania": "TZA",
    "united kingdom": "GBR",
}


def _country_to_iso3(country_name: str) -> str | None:
    normalized = country_name.lower().strip()
    if normalized in UN_COUNTRY_ALIASES:
        return UN_COUNTRY_ALIASES[normalized]
    # Lazy import avoids pulling heavy scraping dependencies at module import time.
    from scripts.fetch_mfa_representatives import country_name_to_iso3

    return country_name_to_iso3(country_name)


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip(" ,.")
    cleaned = re.sub(r"\s*,\s*(MP|KC|GCMG|KGN|KStJ|AC|SC).*$", "", cleaned, flags=re.I)
    return cleaned


def _looks_like_country_entry(block: str) -> bool:
    return bool(_OFFICIAL_RE.search(block[:400]))


def _iter_country_blocks(text: str):
    """Yield (country_name, block_text) pairs from extracted PDF text."""
    country_starts = [
        match
        for match in _COUNTRY_NAME.finditer(text)
        if _looks_like_country_entry(text[match.start() : match.start() + 400])
    ]

    for index, match in enumerate(country_starts):
        start = match.start()
        next_start = (
            country_starts[index + 1].start()
            if index + 1 < len(country_starts)
            else len(text)
        )
        search_end = min(next_start, start + 2500)
        date_match = _DATE_OF_APPOINTMENT.search(text, start, search_end)
        end = date_match.start() if date_match else search_end
        yield match.group(1).strip(), text[start:end]


def _extract_officials(block: str) -> dict[str, str]:
    names: list[str] = []
    for match_groups in _OFFICIAL_RE.findall(block):
        if isinstance(match_groups, tuple):
            raw = next((part for part in match_groups if part and part.strip()), "")
        else:
            raw = match_groups
        if raw and raw.strip() not in {"...", "…"}:
            cleaned = _clean_name(raw)
            if cleaned and (not names or names[-1] != cleaned):
                names.append(cleaned)

    no_pm = bool(re.search(r"\bNo Prime Minister\b", block, re.I))
    same_hos = bool(re.search(r"\bsame as Head of State\b", block, re.I))
    same_pm = bool(re.search(r"\bsame as Prime Minister\b", block, re.I))

    head_of_state = names[0] if names else ""

    if no_pm:
        head_of_government = "No Prime Minister"
        foreign_minister = names[1] if len(names) > 1 else ""
    elif same_hos and names:
        head_of_government = names[0]
        foreign_minister = names[2] if len(names) > 2 else (names[1] if len(names) > 1 else "")
    elif same_pm:
        head_of_government = names[1] if len(names) > 1 else ""
        foreign_minister = head_of_government
    else:
        head_of_government = names[1] if len(names) > 1 else ""
        foreign_minister = names[2] if len(names) > 2 else ""

    return {
        "head_of_state": head_of_state,
        "head_of_government": head_of_government,
        "foreign_minister": foreign_minister,
    }


def parse_un_protocol_text(text: str) -> dict[str, dict[str, str]]:
    """Parse UN protocol PDF text into officials keyed by ISO-3 code."""
    officials_by_iso3: dict[str, dict[str, str]] = {}

    for country_name, block in _iter_country_blocks(text):
        iso3 = _country_to_iso3(country_name)
        if not iso3:
            continue

        parsed = _extract_officials(block)
        if not any(parsed.values()):
            continue

        officials_by_iso3[iso3] = parsed

    return officials_by_iso3


def _fetch_pdf_bytes() -> bytes | None:
    try:
        response = requests.get(
            UN_PROTOCOL_PDF_URL,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        return None


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def fetch_un_protocol_officials() -> dict[str, dict[str, str]]:
    """Download and parse UN protocol list, returning officials keyed by ISO-3."""
    if cache_is_fresh(UN_PROTOCOL_CACHE_FILE, CACHE_TTL_SECONDS):
        cached = read_cache(UN_PROTOCOL_CACHE_FILE)
        if isinstance(cached, dict):
            return cached  # type: ignore[return-value]

    pdf_bytes = _fetch_pdf_bytes()
    if not pdf_bytes:
        cached = read_cache(UN_PROTOCOL_CACHE_FILE)
        return cached if isinstance(cached, dict) else {}

    officials = parse_un_protocol_text(_extract_pdf_text(pdf_bytes))
    write_cache(UN_PROTOCOL_CACHE_FILE, officials)
    return officials
