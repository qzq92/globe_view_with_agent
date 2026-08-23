"""Fetch and normalize maritime news from GDELT and public RSS feeds."""

from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from config.api import (
    GDELT_DOC_API_URL,
    GDELT_DOC_QUERY,
    MARITIME_NEWS_MAX_ARTICLES,
    MARITIME_NEWS_REQUEST_TIMEOUT,
    MARITIME_NEWS_RSS_FEEDS,
    MARITIME_NEWS_TTL_SECONDS,
)
from config.paths import MARITIME_NEWS_CACHE_FILE
from helpers.cache import cache_is_fresh, read_cache, write_cache

_NEWS_LOCK = threading.Lock()
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TRACKING_QUERY_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


def _http_get(url: str, params: dict[str, str] | None = None) -> requests.Response:
    return requests.get(
        url,
        params=params,
        timeout=MARITIME_NEWS_REQUEST_TIMEOUT,
        headers={"User-Agent": _USER_AGENT, "Accept": "*/*"},
    )


def _plain_text(raw: str | None, *, limit: int = 280) -> str:
    text = BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _url_key(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
    ]
    normalized = urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query, doseq=True),
            "",
        )
    )
    return normalized


def _iso_utc(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_gdelt_seen(raw: str) -> str:
    try:
        return _iso_utc(datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC))
    except ValueError:
        return ""


def _parse_rss_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        return _iso_utc(parsedate_to_datetime(raw))
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return _iso_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return ""


def _article(
    *,
    title: str,
    url: str,
    source: str,
    domain: str = "",
    published_at: str = "",
    summary: str = "",
    image: str = "",
) -> dict[str, str] | None:
    title = " ".join((title or "").split())
    url = (url or "").strip()
    if not title or not url:
        return None
    return {
        "title": title,
        "url": url,
        "source": source,
        "domain": domain,
        "published_at": published_at,
        "summary": summary,
        "image": image.strip(),
    }


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local_tag(child.tag) == name:
            href = child.attrib.get("href", "").strip()
            if href and not (child.text or "").strip():
                return href
            return (child.text or "").strip()
    return ""


def _child_attr(element: ET.Element, name: str, attr: str) -> str:
    for child in element:
        if _local_tag(child.tag) == name:
            return (child.attrib.get(attr) or "").strip()
    return ""


def _rss_image(item: ET.Element) -> str:
    enclosure = _child_attr(item, "enclosure", "url")
    if enclosure:
        return enclosure
    return _child_attr(item, "content", "url") or _child_attr(item, "thumbnail", "url")


def _parse_rss_items(xml_text: str, source: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    articles: list[dict[str, str]] = []
    for element in root.iter():
        tag = _local_tag(element.tag)
        if tag not in {"item", "entry"}:
            continue
        title = _child_text(element, "title")
        url = _child_text(element, "link") or _child_attr(element, "link", "href")
        published = (
            _child_text(element, "pubDate")
            or _child_text(element, "published")
            or _child_text(element, "updated")
            or _child_text(element, "date")
        )
        summary = _plain_text(
            _child_text(element, "description")
            or _child_text(element, "summary")
            or _child_text(element, "encoded")
        )
        article = _article(
            title=title,
            url=url,
            source=source,
            domain=urlsplit(url).netloc,
            published_at=_parse_rss_date(published),
            summary=summary,
            image=_rss_image(element),
        )
        if article:
            articles.append(article)
    return articles


def _fetch_gdelt() -> tuple[list[dict[str, str]], str | None]:
    try:
        response = _http_get(
            GDELT_DOC_API_URL,
            {
                "query": GDELT_DOC_QUERY,
                "mode": "ArtList",
                "maxrecords": str(MARITIME_NEWS_MAX_ARTICLES),
                "timespan": "7d",
                "format": "json",
                "sort": "DateDesc",
            },
        )
        if response.status_code == 429:
            return [], "GDELT temporarily rate-limited"
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return [], f"GDELT: {exc}"

    articles: list[dict[str, str]] = []
    for row in payload.get("articles") or []:
        url = str(row.get("url") or "").strip()
        article = _article(
            title=str(row.get("title") or ""),
            url=url,
            source="GDELT",
            domain=str(row.get("domain") or urlsplit(url).netloc),
            published_at=_parse_gdelt_seen(str(row.get("seendate") or "")),
            image=str(row.get("socialimage") or ""),
        )
        if article:
            articles.append(article)
    return articles, None


def _fetch_rss(source: str, url: str) -> tuple[list[dict[str, str]], str | None]:
    try:
        response = _http_get(url)
        response.raise_for_status()
        return _parse_rss_items(response.text, source), None
    except (requests.RequestException, ET.ParseError) as exc:
        return [], f"{source}: {exc}"


def _merge_articles(groups: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for article in sorted(
        (item for group in groups for item in group),
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    ):
        key = _url_key(article["url"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(article)
        if len(merged) >= MARITIME_NEWS_MAX_ARTICLES:
            break
    return merged


def _fetch_all_sources() -> dict[str, Any]:
    groups: list[list[dict[str, str]]] = []
    errors: list[str] = []
    jobs: list[tuple[str, Any]] = [("gdelt", None)]
    jobs.extend(("rss", feed) for feed in MARITIME_NEWS_RSS_FEEDS)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {}
        for kind, feed in jobs:
            if kind == "gdelt":
                futures[pool.submit(_fetch_gdelt)] = "GDELT"
            else:
                source, url = feed
                futures[pool.submit(_fetch_rss, source, url)] = source
        for future in as_completed(futures):
            articles, error = future.result()
            if articles:
                groups.append(articles)
            if error:
                errors.append(error)

    return {
        "articles": _merge_articles(groups),
        "fetched_at": _iso_utc(datetime.now(UTC)),
        "errors": errors,
        "from_cache": False,
    }


def fetch_maritime_news(*, force: bool = False) -> dict[str, Any]:
    """Return cached maritime headlines, refreshing from APIs when stale."""
    if not force and cache_is_fresh(MARITIME_NEWS_CACHE_FILE, MARITIME_NEWS_TTL_SECONDS):
        payload = read_cache(MARITIME_NEWS_CACHE_FILE)
        if isinstance(payload, dict) and payload.get("articles"):
            payload["from_cache"] = True
            return payload

    with _NEWS_LOCK:
        if not force and cache_is_fresh(MARITIME_NEWS_CACHE_FILE, MARITIME_NEWS_TTL_SECONDS):
            payload = read_cache(MARITIME_NEWS_CACHE_FILE)
            if isinstance(payload, dict) and payload.get("articles"):
                payload["from_cache"] = True
                return payload

        payload = _fetch_all_sources()
        if payload["articles"]:
            write_cache(MARITIME_NEWS_CACHE_FILE, payload)
        elif MARITIME_NEWS_CACHE_FILE.exists():
            stale = read_cache(MARITIME_NEWS_CACHE_FILE)
            if isinstance(stale, dict) and stale.get("articles"):
                stale["from_cache"] = True
                stale["errors"] = list(stale.get("errors") or []) + payload.get("errors", [])
                return stale
        return payload
