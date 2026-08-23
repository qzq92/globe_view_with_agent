"""World Map, Satellite, and Maritime Dashboard.

An interactive Plotly Dash app. Hovering a country on the choropleth surfaces
its land area, population, capital, government type, UN officials, and major news
outlet, both in the map tooltip and a synced side panel.

Run with::

    python app.py

then open http://127.0.0.1:8050 in a browser.
"""

from __future__ import annotations

import helpers.ssl_patch  # noqa: F401 - must run before data_loader / requests

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import ClientsideFunction, Dash, Input, Output, Patch, ctx, dcc, html, no_update
from dash.development.base_component import Component

from config.dashboard import (
    APP_TITLE,
    CHOROPLETH_COLORS,
    COLORS,
    CONTENT_ROW_STYLE,
    CUSTOMDATA_COLUMNS,
    DATA_SOURCE_LINKS,
    FIELD_LABELS,
    GEO_STYLE,
    GLOBE_PROJECTION,
    GRAPH_CONFIG,
    GRAPH_HEIGHT,
    HIDDEN_STYLE,
    HOVERTEMPLATE,
    LABEL_STYLE,
    LAYOUT_STYLE,
    LINK_STYLE,
    MAP_CONTAINER_STYLE,
    MAP_VIEW_TAB_GLOBE,
    MAP_VIEW_TAB_MARITIME,
    MAP_VIEW_TAB_MARITIME_NEWS,
    MAP_VIEW_TAB_SATELLITE_3D,
    MAP_VIEW_TABS_STYLE,
    MARITIME_EMBED_URL,
    MARITIME_PAGE_URL,
    PANEL_CONTAINER_STYLE,
    SUBTITLE_STYLE,
    TAB_COLORS,
)
from config.data import MISSING
from config.server import DEBUG, HOST, PORT
from data_loader import load_country_data, CountryDataLoad
from helpers.banner import build_api_error_banner
from helpers.formatting import format_number
from helpers.maritime_news import fetch_maritime_news
from helpers.satellite import get_satellite_positions

# Global state for cached data
_load_result: CountryDataLoad | None = None
df: pd.DataFrame = pd.DataFrame()
_iso3_index: dict[str, pd.Series] = {}
_load_lock = threading.Lock()

_satellite_lock = threading.Lock()
_satellite_df: pd.DataFrame = pd.DataFrame()
_satellite_updated_at: datetime | None = None

SATELLITE_INTERVAL_MS = 180_000
SATELLITE_REFRESH_SECONDS = 180
MARITIME_NEWS_INTERVAL_MS = 1_800_000
SATELLITE_CATEGORIES = ["Space Stations", "Weather"]
SATELLITE_STORE_COLUMNS = [
    "name",
    "norad_id",
    "category",
    "lat",
    "lon",
    "elevation_km",
    "alt_m",
    "country",
    "owner",
    "purpose",
    "marker_color",
]
SATELLITE_COLORS = {
    "Space Stations": "#ff4d4f",
    "Weather": "#73d13d",
}
COUNTRY_HIGHLIGHT_TRACE_INDEX = 1
GLOBE_UIREVISION = "globe-view"
CESIUM_BASE_URL = (
    "https://cesium.com/downloads/cesiumjs/releases/1.123/Build/Cesium/"
)
CESIUM_SCRIPT_URL = f"{CESIUM_BASE_URL}Cesium.js"
CESIUM_CSS_URL = f"{CESIUM_BASE_URL}Widgets/widgets.css"


def load_and_process_data() -> CountryDataLoad:
    """Load country data and prepare formatted columns."""
    global df, _iso3_index

    result = load_country_data()

    if not result.df.empty:
        # customdata columns must align with the hovertemplate indices below.
        result.df["area_fmt"] = result.df["area"].map(lambda v: format_number(v, " km2"))
        result.df["population_fmt"] = result.df["population"].map(format_number)
        # Vectorized replacement for row-wise apply.
        result.df["consulate_status"] = result.df["consulate_name"].where(
            result.df["consulate_name"] != MISSING,
            result.df["consulate_note"],
        )
        _iso3_index = {iso3: row for iso3, row in result.df.set_index("iso3").iterrows()}
        df = result.df

    return result


def ensure_data_loaded() -> CountryDataLoad:
    """Load app data once per process, even with concurrent callbacks."""
    global _load_result
    if _load_result is not None:
        return _load_result

    with _load_lock:
        if _load_result is None:
            print("Loading country data and diplomatic missions...")
            _load_result = load_and_process_data()
            print(f"Loaded {len(df)} countries into dashboard")

    return _load_result


def _satellite_cache_is_fresh(now: datetime) -> bool:
    """Return True when the in-memory satellite snapshot is still within TTL."""
    return (
        _satellite_updated_at is not None
        and now - _satellite_updated_at < timedelta(seconds=SATELLITE_REFRESH_SECONDS)
    )


def _get_satellite_data() -> tuple[pd.DataFrame, datetime | None]:
    """Return shared satellite dataframe refreshed every 3 minutes."""
    global _satellite_df, _satellite_updated_at
    now = datetime.now(UTC)
    if _satellite_cache_is_fresh(now):
        return _satellite_df.copy(), _satellite_updated_at

    with _satellite_lock:
        now = datetime.now(UTC)
        if _satellite_cache_is_fresh(now):
            return _satellite_df.copy(), _satellite_updated_at

        _satellite_df = get_satellite_positions()
        _satellite_updated_at = now
        return _satellite_df.copy(), _satellite_updated_at


def _build_satellite_store() -> dict[str, Any]:
    """Build satellite-store payload for map overlays and the 3D tab."""
    categories = SATELLITE_CATEGORIES
    satellites, updated_at = _get_satellite_data()

    if satellites.empty:
        return {"satellites": [], "categories": categories, "updated_at": None}

    filtered = satellites[satellites["category"].isin(categories)].copy()
    filtered["alt_m"] = filtered["elevation_km"] * 1000
    filtered["marker_color"] = filtered["category"].map(SATELLITE_COLORS).fillna("#9ca3af")

    records = filtered[SATELLITE_STORE_COLUMNS].to_dict("records")
    return {
        "satellites": records,
        "categories": categories,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _satellite_update_label(store_data: dict[str, Any] | None) -> str:
    """Return the banner text for the last satellite position update."""
    if not store_data:
        return "Last satellite update: pending"
    updated_at = store_data.get("updated_at")
    if not updated_at:
        return "Last satellite update: unavailable"
    timestamp = datetime.fromisoformat(updated_at).astimezone()
    return f"Last satellite update: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"


def _country_highlight_trace(hover_iso3: str | None = None) -> go.Choropleth:
    """Reserved overlay used to outline the hovered country without rebuilding the globe."""
    has_hover = bool(hover_iso3 and hover_iso3 in _iso3_index)
    return go.Choropleth(
        locations=[hover_iso3] if has_hover else [],
        locationmode="ISO-3",
        z=[1] if has_hover else [],
        colorscale=[
            [0, CHOROPLETH_COLORS["hover_fill"]],
            [1, CHOROPLETH_COLORS["hover_fill"]],
        ],
        showscale=False,
        marker_line_color=CHOROPLETH_COLORS["hover_line_color"],
        marker_line_width=CHOROPLETH_COLORS["hover_line_width"],
        hoverinfo="skip",
        showlegend=False,
        name="Country highlight",
    )


def _hovered_country_iso3(hover_data: dict[str, Any] | None) -> str | None:
    """Return the ISO-3 code of the hovered country, if one is present."""
    if not hover_data or not hover_data.get("points"):
        return None
    for point in hover_data["points"]:
        location = point.get("location")
        if location and location in _iso3_index:
            return location
    return None


def build_figure() -> go.Figure:
    """Build the globe figure with country outlines only."""
    if df.empty:
        locations: list[str] = []
        customdata = []
    else:
        locations = df["iso3"].tolist()
        customdata = df[CUSTOMDATA_COLUMNS].to_numpy()

    # Constant z + transparent colorscale: no population fill / no colorbar.
    z_values = [0] * len(locations)

    figure = go.Figure(
        data=go.Choropleth(
            locations=locations,
            locationmode="ISO-3",
            z=z_values,
            customdata=customdata,
            hovertemplate=HOVERTEMPLATE,
            colorscale=CHOROPLETH_COLORS["colorscale"],
            showscale=False,
            marker_line_color=CHOROPLETH_COLORS["marker_line_color"],
            marker_line_width=CHOROPLETH_COLORS["marker_line_width"],
            name="Countries",
            showlegend=False,
        )
    )
    figure.add_trace(_country_highlight_trace())

    figure.update_layout(
        margin=GEO_STYLE["margin"],
        uirevision=GLOBE_UIREVISION,
        geo=dict(
            showframe=True,
            showcoastlines=True,
            showland=True,
            landcolor="rgba(30, 41, 59, 0.35)",
            showocean=True,
            oceancolor="rgba(15, 23, 42, 0.6)",
            showcountries=False,
            projection_type=GLOBE_PROJECTION,
            bgcolor=GEO_STYLE["bgcolor"],
            uirevision=GLOBE_UIREVISION,
        ),
        paper_bgcolor=GEO_STYLE["paper_bgcolor"],
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(15, 23, 42, 0.7)",
            bordercolor=COLORS["border"],
            borderwidth=1,
            font=dict(color=COLORS["text"], size=12),
        ),
    )
    return figure


def _labeled_row(label: str, value: Any) -> html.Div:
    """Return a label/value row used by the side panels."""
    return html.Div(
        [
            html.Span(f"{label}: ", style=LABEL_STYLE),
            value if isinstance(value, Component) else html.Span(str(value)),
        ],
        style={"marginBottom": "8px"},
    )


def _external_link(label: str, href: str) -> html.A:
    """Return an external-link anchor with shared styling."""
    return html.A(
        label,
        href=href,
        target="_blank",
        rel="noopener noreferrer",
        style=LINK_STYLE,
    )


def _format_news_timestamp(raw: str) -> str:
    """Format a stored ISO timestamp for the news list."""
    if not raw:
        return "Date unavailable"
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    return value.strftime("%d %b %Y %H:%M UTC")


def _render_news_article(article: dict[str, Any]) -> html.Div:
    """Return one maritime news card."""
    image = (article.get("image") or "").strip()
    summary = (article.get("summary") or "").strip()
    source = article.get("source") or article.get("domain") or "News"
    meta = f"{source} · {_format_news_timestamp(article.get('published_at') or '')}"
    body: list[Component] = [
        html.A(
            article.get("title") or "Untitled",
            href=article.get("url") or "#",
            target="_blank",
            rel="noopener noreferrer",
            style={**LINK_STYLE, "fontWeight": "600", "fontSize": "16px"},
        ),
        html.Div(meta, style={"color": COLORS["muted"], "fontSize": "12px", "marginTop": "4px"}),
    ]
    if summary:
        body.append(
            html.P(
                summary,
                style={"color": COLORS["text"], "fontSize": "13px", "margin": "8px 0 0 0"},
            )
        )
    children: list[Component] = []
    if image:
        children.append(
            html.Img(
                src=image,
                alt="",
                style={
                    "width": "96px",
                    "height": "72px",
                    "objectFit": "cover",
                    "borderRadius": "8px",
                    "flexShrink": "0",
                    "backgroundColor": COLORS["border"],
                },
            )
        )
    children.append(html.Div(body, style={"minWidth": 0, "flex": "1"}))
    return html.Div(
        children,
        style={
            "display": "flex",
            "gap": "12px",
            "backgroundColor": COLORS["card"],
            "border": f"1px solid {COLORS['border']}",
            "borderRadius": "12px",
            "padding": "12px",
            "marginBottom": "10px",
        },
    )


def _render_news_list(articles: list[dict[str, Any]], query: str) -> list[Component]:
    """Filter and render maritime news cards."""
    needle = query.strip().lower()
    filtered = [
        article
        for article in articles
        if not needle
        or needle in (article.get("title") or "").lower()
        or needle in (article.get("source") or "").lower()
        or needle in (article.get("summary") or "").lower()
    ]
    if not filtered:
        message = "No maritime headlines matched that search." if articles else "No maritime headlines loaded yet."
        return [html.P(message, style={"color": COLORS["muted"]})]
    return [_render_news_article(article) for article in filtered]


def _news_status_text(payload: dict[str, Any]) -> str:
    """Return a short status line for the news panel."""
    count = len(payload.get("articles") or [])
    fetched_at = _format_news_timestamp(payload.get("fetched_at") or "")
    origin = "cached" if payload.get("from_cache") else "live"
    errors = payload.get("errors") or []
    status = f"{count} headlines · {origin} · {fetched_at}"
    if errors:
        extra = errors[0]
        if len(extra) > 140:
            extra = extra[:137] + "…"
        if len(errors) > 1:
            extra += f" (+{len(errors) - 1} more)"
        status += " · " + extra
    return status


def _maritime_news_section() -> html.Div:
    """Return the Maritime News tab body."""
    return html.Div(
        id="maritime-news-section",
        style=HIDDEN_STYLE,
        children=[
            dcc.Interval(
                id="maritime-news-interval",
                interval=MARITIME_NEWS_INTERVAL_MS,
                n_intervals=0,
            ),
            dcc.Store(id="maritime-news-store", data={"articles": [], "errors": []}),
            html.Div(
                style=CONTENT_ROW_STYLE,
                children=[
                    html.Div(
                        [
                            dcc.Input(
                                id="maritime-news-search",
                                type="search",
                                placeholder="Search headlines…",
                                debounce=True,
                                style={
                                    "width": "100%",
                                    "boxSizing": "border-box",
                                    "marginBottom": "12px",
                                    "padding": "10px 12px",
                                    "borderRadius": "8px",
                                    "border": f"1px solid {COLORS['border']}",
                                    "backgroundColor": COLORS["card"],
                                    "color": COLORS["text"],
                                },
                            ),
                            dcc.Loading(
                                id="maritime-news-loading",
                                type="default",
                                color=COLORS["accent"],
                                children=html.Div(
                                    [
                                        html.Div(
                                            id="maritime-news-fetch-flag",
                                            style={"display": "none"},
                                        ),
                                        html.Div(
                                            id="maritime-news-list",
                                            children=[
                                                html.P(
                                                    "Open this tab to load maritime headlines.",
                                                    style={"color": COLORS["muted"]},
                                                )
                                            ],
                                        ),
                                    ],
                                    style={
                                        "height": GRAPH_HEIGHT,
                                        "overflowY": "auto",
                                        "paddingRight": "4px",
                                    },
                                ),
                            ),
                        ],
                        style={**MAP_CONTAINER_STYLE, "flex": "4 1 720px"},
                    ),
                    html.Div(
                        style=PANEL_CONTAINER_STYLE,
                        children=[
                            html.H3("Maritime news", style={"marginTop": 0}),
                            html.P(
                                "Headlines are loaded by API from GDELT DOC 2.0 and "
                                "public maritime RSS feeds (gCaptain, Splash247, Marine "
                                "Insight, Offshore Energy, and Seatrade Maritime). "
                                "MarineTraffic news is a website feature on the free "
                                "plan, not a public news API.",
                                style={"color": COLORS["muted"]},
                            ),
                            html.Div(
                                id="maritime-news-status",
                                style={
                                    "color": COLORS["muted"],
                                    "fontSize": "13px",
                                    "marginBottom": "12px",
                                },
                                children="News has not been fetched yet.",
                            ),
                            html.Button(
                                "Refresh news",
                                id="maritime-news-refresh",
                                n_clicks=0,
                                type="button",
                                style={
                                    "backgroundColor": COLORS["accent"],
                                    "color": COLORS["background"],
                                    "border": "none",
                                    "borderRadius": "8px",
                                    "padding": "8px 14px",
                                    "cursor": "pointer",
                                    "fontWeight": "600",
                                },
                            ),
                            html.Div(
                                style={"marginTop": "16px"},
                                children=[
                                    html.Div("Sources", style=LABEL_STYLE),
                                    html.Ul(
                                        [
                                            html.Li(_external_link("GDELT Project", "https://www.gdeltproject.org/")),
                                            html.Li(_external_link("gCaptain", "https://gcaptain.com/")),
                                            html.Li(_external_link("Splash247", "https://splash247.com/")),
                                            html.Li(
                                                _external_link("Marine Insight", "https://www.marineinsight.com/")
                                            ),
                                            html.Li(
                                                _external_link("Offshore Energy", "https://www.offshore-energy.biz/")
                                            ),
                                            html.Li(
                                                _external_link(
                                                    "Seatrade Maritime",
                                                    "https://www.seatrade-maritime.com/",
                                                )
                                            ),
                                        ],
                                        style={"paddingLeft": "18px", "margin": "8px 0 0 0"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _data_source_note() -> html.Div:
    """Return the data-source attribution line under the subtitle."""
    children: list[Any] = [html.Span("Data sources: ", style={"fontWeight": "600"})]
    for index, (label, href) in enumerate(DATA_SOURCE_LINKS):
        if index:
            children.append(html.Span(" + "))
        children.append(_external_link(label, href))
    return html.Div(
        children,
        style={
            "textAlign": "center",
            "color": COLORS["muted"],
            "fontSize": "12px",
            "marginBottom": "10px",
            "lineHeight": "1.6",
        },
    )


def _info_rows(row: pd.Series) -> list[Any]:
    """Render labeled country-detail rows for the side panel."""
    children = []
    for label, key in FIELD_LABELS:
        value = str(row[key])
        if key == "un_organizations" and value not in (MISSING, "None"):
            children.append(
                _labeled_row(
                    label,
                    html.Ul(
                        [html.Li(org.strip()) for org in value.split(";")],
                        style={"margin": "4px 0 8px 0", "paddingLeft": "20px"},
                    ),
                )
            )
            continue
        children.append(_labeled_row(label, value))
    return children


def _singapore_mission_section(row: pd.Series) -> list[Any]:
    """Render Singapore embassy/consulate details for one country."""
    children = [
        html.H4(
            "Singapore mission",
            style={"marginBottom": "8px", "marginTop": "18px"},
        )
    ]

    if row["consulate_name"] == MISSING:
        return children + [
            html.P(
                row["consulate_note"],
                style={"color": COLORS["muted"], "marginTop": 0},
            )
        ]

    children.extend(
        [
            _labeled_row("Mission", row["consulate_name"]),
            _labeled_row("Location", row["consulate_address"]),
            _labeled_row("Official link", _external_link("Open official page", row["consulate_link"])),
        ]
    )
    if row["consulate_note"]:
        children.append(
            html.P(
                row["consulate_note"],
                style={"color": COLORS["muted"], "marginTop": 0},
            )
        )
    return children


def render_panel(iso3: str | None) -> list[Any]:
    """Return country-panel children for the given ISO-3 code, or a prompt."""
    if df.empty or iso3 is None or iso3 not in _iso3_index:
        return [
            html.H3("Country details", style={"marginTop": 0}),
            html.P(
                "Hover over a country on the globe to see its details.",
                style={"color": COLORS["muted"]},
            ),
        ]
    row = _iso3_index[iso3]
    return [
        html.H3(row["name"], style={"marginTop": 0}),
        *_info_rows(row),
        *_singapore_mission_section(row),
    ]


def build_loading_layout() -> html.Div:
    """Return the loading screen layout shown while fetching data."""
    return html.Div(
        style={
            **LAYOUT_STYLE,
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "height": "100vh",
        },
        children=[
            dcc.Interval(
                id="init-interval",
                interval=100,
                n_intervals=0,
                max_intervals=1,
            ),
            html.H1(
                APP_TITLE,
                style={"textAlign": "center", "marginBottom": "20px"},
            ),
            html.Div(
                [
                    # Simple pulsing dots loader
                    html.Div(
                        "●  ●  ●",
                        style={
                            "color": COLORS["accent"],
                            "fontSize": "24px",
                            "marginBottom": "16px",
                            "letterSpacing": "8px",
                        },
                    ),
                    html.P(
                        "Loading country data and diplomatic missions...",
                        style={"color": COLORS["muted"], "fontSize": "14px"},
                    ),
                    html.P(
                        "This may take a moment while we fetch from REST Countries, "
                        "World Bank, and Singapore MFA.",
                        style={
                            "color": COLORS["muted"],
                            "fontSize": "12px",
                            "textAlign": "center",
                            "maxWidth": "400px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                },
            ),
        ],
    )


def build_main_layout(banner_messages: list[str]) -> html.Div:
    """Return the main app layout after data is loaded."""
    return html.Div(
        style=LAYOUT_STYLE,
        children=[
            html.H1(
                APP_TITLE,
                style={"textAlign": "center", "marginBottom": "4px"},
            ),
            html.P(
                "Hover over any country to explore its key information.",
                style=SUBTITLE_STYLE,
            ),
            _data_source_note(),
            html.Div(
                "Satellite positions update live every 3 minutes.",
                style={
                    "textAlign": "center",
                    "color": COLORS["accent"],
                    "fontSize": "14px",
                    "marginBottom": "10px",
                    "fontWeight": "bold",
                },
            ),
            dcc.Interval(
                id="satellite-interval",
                interval=SATELLITE_INTERVAL_MS,
                n_intervals=0,
            ),
            dcc.Store(id="satellite-store", data={"satellites": [], "categories": SATELLITE_CATEGORIES}),
            build_api_error_banner(banner_messages),
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "flex-end",
                    "marginBottom": "12px",
                },
                children=[
                    html.Div(
                        id="satellite-update-text",
                        style={"color": COLORS["muted"], "fontSize": "13px"},
                        children="Last satellite update: pending",
                    ),
                ],
            ),
            html.Div(
                dcc.Tabs(
                    id="map-view-tabs",
                    value=MAP_VIEW_TAB_GLOBE,
                    children=[
                        dcc.Tab(label="Globe (Basic Country Info)", value=MAP_VIEW_TAB_GLOBE),
                        dcc.Tab(label="Maritime Map", value=MAP_VIEW_TAB_MARITIME),
                        dcc.Tab(label="Maritime News", value=MAP_VIEW_TAB_MARITIME_NEWS),
                        dcc.Tab(label="3D Satellite", value=MAP_VIEW_TAB_SATELLITE_3D),
                    ],
                    colors=TAB_COLORS,
                    style={"width": "fit-content"},
                ),
                style=MAP_VIEW_TABS_STYLE,
                className="map-view-tabs",
            ),
            html.Div(
                id="map-section",
                style=CONTENT_ROW_STYLE,
                children=[
                    html.Div(
                        dcc.Loading(
                            id="map-loading",
                            type="default",
                            color=COLORS["accent"],
                            children=dcc.Graph(
                                id="world-map",
                                figure=build_figure(),
                                style={"height": GRAPH_HEIGHT},
                                config=GRAPH_CONFIG,
                            ),
                        ),
                        style=MAP_CONTAINER_STYLE,
                    ),
                    html.Div(
                        id="info-panel",
                        style=PANEL_CONTAINER_STYLE,
                        children=render_panel(None),
                    ),
                ],
            ),
            html.Div(
                id="satellite-3d-section",
                style=HIDDEN_STYLE,
                children=[
                    html.Div(
                        style=CONTENT_ROW_STYLE,
                        children=[
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(
                                                id="cesium-container",
                                                style={
                                                    "height": GRAPH_HEIGHT,
                                                    "width": "100%",
                                                    "border": f"1px solid {COLORS['border']}",
                                                    "borderRadius": "12px",
                                                    "overflow": "hidden",
                                                },
                                            ),
                                            html.Div(
                                                [
                                                    html.Div(
                                                        "Legend",
                                                        style={
                                                            "fontWeight": "600",
                                                            "marginBottom": "8px",
                                                        },
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Span(
                                                                style={
                                                                    "display": "inline-block",
                                                                    "width": "10px",
                                                                    "height": "10px",
                                                                    "borderRadius": "999px",
                                                                    "backgroundColor": SATELLITE_COLORS["Space Stations"],
                                                                    "marginRight": "8px",
                                                                }
                                                            ),
                                                            html.Span("Space Stations"),
                                                        ],
                                                        style={"marginBottom": "6px", "fontSize": "12px"},
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Span(
                                                                style={
                                                                    "display": "inline-block",
                                                                    "width": "10px",
                                                                    "height": "10px",
                                                                    "borderRadius": "999px",
                                                                    "backgroundColor": SATELLITE_COLORS["Weather"],
                                                                    "marginRight": "8px",
                                                                }
                                                            ),
                                                            html.Span("Weather"),
                                                        ],
                                                        style={"fontSize": "12px"},
                                                    ),
                                                ],
                                                style={
                                                    "position": "absolute",
                                                    "top": "14px",
                                                    "left": "14px",
                                                    "zIndex": "10",
                                                    "backgroundColor": "rgba(15, 23, 42, 0.86)",
                                                    "border": f"1px solid {COLORS['border']}",
                                                    "borderRadius": "10px",
                                                    "padding": "10px 12px",
                                                    "color": COLORS["text"],
                                                    "pointerEvents": "none",
                                                },
                                            ),
                                        ],
                                        style={"position": "relative"},
                                    ),
                                    html.Div(
                                        id="cesium-render-flag",
                                        style={"display": "none"},
                                    ),
                                ],
                                style=MAP_CONTAINER_STYLE,
                            ),
                            html.Div(
                                id="satellite-info-panel",
                                style=PANEL_CONTAINER_STYLE,
                                children=[
                                    html.H3("Satellite details", style={"marginTop": 0}),
                                    html.P(
                                        "Satellite positions update in this 3D view every 3 minutes.",
                                        style={"color": COLORS["muted"]},
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            ),
            html.Div(
                id="maritime-section",
                style=HIDDEN_STYLE,
                children=[
                    html.Div(
                        style=CONTENT_ROW_STYLE,
                        children=[
                            html.Div(
                                html.Iframe(
                                    id="maritime-embed",
                                    src=MARITIME_EMBED_URL,
                                    style={
                                        "width": "100%",
                                        "height": GRAPH_HEIGHT,
                                        "border": f"1px solid {COLORS['border']}",
                                        "borderRadius": "12px",
                                        "backgroundColor": COLORS["card"],
                                    },
                                ),
                                style={**MAP_CONTAINER_STYLE, "flex": "4 1 720px"},
                            ),
                            html.Div(
                                style=PANEL_CONTAINER_STYLE,
                                children=[
                                    html.H3("Global vessel map", style={"marginTop": 0}),
                                    html.P(
                                        "Interactive AIS map embedded from MarineTraffic. "
                                        "Search, filter, and zoom across vessels without "
                                        "loading them into this app.",
                                        style={"color": COLORS["muted"]},
                                    ),
                                    _external_link("Open MarineTraffic", MARITIME_PAGE_URL),
                                ],
                            ),
                        ],
                    )
                ],
            ),
            _maritime_news_section(),
        ],
    )


app = Dash(
    __name__,
    suppress_callback_exceptions=True,
    external_scripts=[CESIUM_SCRIPT_URL],
    external_stylesheets=[CESIUM_CSS_URL],
)
app.title = APP_TITLE
# Must be set before Cesium.js resolves Workers / NaturalEarth assets.
app.index_string = f"""
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <script>window.CESIUM_BASE_URL = "{CESIUM_BASE_URL}";</script>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
"""

@app.callback(
    Output("app-container", "children"),
    Input("init-interval", "n_intervals"),
    prevent_initial_call=True,
)
def init_app(_: int) -> html.Div:
    """Load data on app start and switch from loading to main layout."""
    load_result = ensure_data_loaded()
    return build_main_layout(load_result.banner_messages)


@app.callback(
    Output("satellite-store", "data"),
    Output("satellite-update-text", "children"),
    Input("satellite-interval", "n_intervals"),
)
def refresh_satellite_state(
    _n_intervals: int,
) -> tuple[dict[str, Any], str]:
    """Refresh satellite store data and the last-update banner text."""
    store_data = _build_satellite_store()
    return store_data, _satellite_update_label(store_data)


@app.callback(
    Output("world-map", "figure"),
    Input("map-view-tabs", "value"),
)
def update_map_projection(
    _view: str,
) -> go.Figure:
    """Build the basic globe view when the active tab changes."""
    return build_figure()


@app.callback(
    Output("world-map", "figure", allow_duplicate=True),
    Input("world-map", "hoverData"),
    prevent_initial_call=True,
)
def highlight_hovered_country(hover_data: dict[str, Any] | None) -> Patch:
    """Outline the hovered country without replacing the globe figure."""
    iso3 = _hovered_country_iso3(hover_data)
    patched = Patch()
    if iso3:
        patched["data"][COUNTRY_HIGHLIGHT_TRACE_INDEX]["locations"] = [iso3]
        patched["data"][COUNTRY_HIGHLIGHT_TRACE_INDEX]["z"] = [1]
    else:
        patched["data"][COUNTRY_HIGHLIGHT_TRACE_INDEX]["locations"] = []
        patched["data"][COUNTRY_HIGHLIGHT_TRACE_INDEX]["z"] = []
    return patched


@app.callback(
    Output("map-section", "style"),
    Output("satellite-3d-section", "style"),
    Output("maritime-section", "style"),
    Output("maritime-news-section", "style"),
    Input("map-view-tabs", "value"),
)
def toggle_view_sections(
    active_tab: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Show only the section that matches the selected tab."""
    return (
        CONTENT_ROW_STYLE if active_tab == MAP_VIEW_TAB_GLOBE else {**CONTENT_ROW_STYLE, **HIDDEN_STYLE},
        {"display": "block"} if active_tab == MAP_VIEW_TAB_SATELLITE_3D else HIDDEN_STYLE,
        {"display": "block"} if active_tab == MAP_VIEW_TAB_MARITIME else HIDDEN_STYLE,
        {"display": "block"} if active_tab == MAP_VIEW_TAB_MARITIME_NEWS else HIDDEN_STYLE,
    )


@app.callback(
    Output("maritime-news-store", "data"),
    Output("maritime-news-status", "children"),
    Output("maritime-news-fetch-flag", "children"),
    Input("map-view-tabs", "value"),
    Input("maritime-news-interval", "n_intervals"),
    Input("maritime-news-refresh", "n_clicks"),
    prevent_initial_call=True,
)
def load_maritime_news(
    active_tab: str,
    _n_intervals: int,
    n_clicks: int,
) -> tuple[dict[str, Any] | Any, str | Any, str | Any]:
    """Fetch maritime headlines when the news tab is open or refresh is clicked."""
    force_refresh = ctx.triggered_id == "maritime-news-refresh" and bool(n_clicks)
    if active_tab != MAP_VIEW_TAB_MARITIME_NEWS and not force_refresh:
        return no_update, no_update, no_update
    payload = fetch_maritime_news(force=force_refresh)
    return payload, _news_status_text(payload), payload.get("fetched_at") or ""


@app.callback(
    Output("maritime-news-list", "children"),
    Input("maritime-news-store", "data"),
    Input("maritime-news-search", "value"),
    prevent_initial_call=True,
)
def render_maritime_news_list(
    payload: dict[str, Any] | None,
    query: str | None,
) -> list[Any]:
    """Render stored maritime headlines, filtered by the search box."""
    articles = list((payload or {}).get("articles") or [])
    return _render_news_list(articles, query or "")


@app.callback(Output("info-panel", "children"), Input("world-map", "hoverData"))
def update_panel(hover_data: dict[str, Any] | None) -> list[Any]:
    """Update the country side panel from globe hover data."""
    return render_panel(_hovered_country_iso3(hover_data))


@app.callback(
    Output("satellite-info-panel", "children"),
    Input("satellite-store", "data"),
)
def update_satellite_panel(
    satellite_store: dict[str, Any] | None,
) -> list[Any]:
    """Render summary details for the 3D satellite view."""
    count = len((satellite_store or {}).get("satellites", []))
    return [
        html.H3("Satellite details", style={"marginTop": 0}),
        html.P(f"Visible satellites: {count}", style={"color": COLORS["muted"]}),
        html.P(
            "Satellite markers are shown only in the 3D Satellite tab.",
            style={"color": COLORS["muted"]},
        ),
    ]


app.clientside_callback(
    ClientsideFunction(namespace="satellite3d", function_name="render"),
    Output("cesium-render-flag", "children"),
    Input("satellite-store", "data"),
    Input("map-view-tabs", "value"),
)


app.layout = html.Div(id="app-container", children=build_loading_layout())


if __name__ == "__main__":
    app.run(debug=DEBUG, host=HOST, port=PORT)
