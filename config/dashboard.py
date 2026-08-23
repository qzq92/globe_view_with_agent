"""Dash dashboard layout, map, and UI configuration."""

import os

from dotenv import load_dotenv

from config.paths import ENV_FILE

load_dotenv(ENV_FILE)

APP_TITLE = "World Map, Satellite, and Maritime Dashboard"

GLOBE_PROJECTION = "orthographic"
MAP_VIEW_TAB_GLOBE = "globe"
MAP_VIEW_TAB_MARITIME = "maritime"
MAP_VIEW_TAB_MARITIME_NEWS = "maritime-news"
MAP_VIEW_TAB_SATELLITE_3D = "satellite-3d"

MARITIME_PAGE_URL = "https://www.marinetraffic.com/"
DEFAULT_MARITIME_EMBED_URL = (
    "https://www.marinetraffic.com/en/ais/embed/"
    "zoom:3/centery:20/centerx:0/maptype:0/shownames:true/"
    "mmsi:0/shipid:0/fleet:/fleet_id:/vtypes:/showmenu:true/remember:false"
)
MARITIME_EMBED_URL = (
    os.getenv("MARITIME_EMBED_URL", DEFAULT_MARITIME_EMBED_URL).strip()
    or DEFAULT_MARITIME_EMBED_URL
)

DATA_SOURCE_LINKS = (
    ("REST Countries", "https://restcountries.com/"),
    (
        "World Bank",
        "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
    ),
    (
        "UN Protocol",
        "https://www.un.org/dgacm/sites/www.un.org.dgacm/files/"
        "Documents_Protocol/hspmfmlist.pdf",
    ),
    (
        "Singapore MFA",
        "https://www.mfa.gov.sg/visiting-singapore/foreign-representatives-to-singapore/",
    ),
    ("MarineTraffic", MARITIME_PAGE_URL),
    ("GDELT", "https://www.gdeltproject.org/"),
    ("Celestrak", "https://celestrak.org/"),
    (
        "UCS Satellite Database",
        "https://www.ucsusa.org/resources/satellite-database",
    ),
)

CUSTOMDATA_COLUMNS = [
    "name",
    "area_fmt",
    "population_fmt",
    "capital",
    "currency",
    "government",
    "head_of_state",
    "head_of_government",
    "foreign_minister",
    "major_cities",
    "news_outlet",
    "un_organizations",
    "consulate_status",
]

HOVERTEMPLATE = (
    "<b>%{customdata[0]}</b><br>"
    "Land area: %{customdata[1]}<br>"
    "Population: %{customdata[2]}<br>"
    "Capital: %{customdata[3]}<br>"
    "Currency: %{customdata[4]}<br>"
    "Government: %{customdata[5]}<br>"
    "Head of state: %{customdata[6]}<br>"
    "Head of government: %{customdata[7]}<br>"
    "Foreign minister: %{customdata[8]}<br>"
    "Major cities: %{customdata[9]}<br>"
    "Major news outlet: %{customdata[10]}<br>"
    "UN organizations: %{customdata[11]}<br>"
    "Singapore mission: %{customdata[12]}"
    "<extra></extra>"
)

COLORS = {
    "background": "#0f172a",
    "card": "#1e293b",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "accent": "#38bdf8",
    "border": "#334155",
}

CARD_STYLE = {
    "backgroundColor": COLORS["card"],
    "borderRadius": "12px",
    "padding": "20px",
    "color": COLORS["text"],
    "boxShadow": "0 4px 12px rgba(0,0,0,0.25)",
}

LAYOUT_STYLE = {
    "fontFamily": "Segoe UI, Roboto, Helvetica, Arial, sans-serif",
    "backgroundColor": COLORS["background"],
    "minHeight": "100vh",
    "color": COLORS["text"],
    "padding": "24px",
    "boxSizing": "border-box",
}

SUBTITLE_STYLE = {
    "textAlign": "center",
    "color": COLORS["muted"],
    "marginTop": 0,
}

TAB_COLORS = {
    "border": COLORS["border"],
    "primary": COLORS["accent"],
    "background": COLORS["card"],
}

MAP_VIEW_TABS_STYLE = {
    "display": "flex",
    "justifyContent": "center",
    "marginBottom": "16px",
}

CONTENT_ROW_STYLE = {
    "display": "flex",
    "gap": "20px",
    "alignItems": "stretch",
    "flexWrap": "wrap",
}

GRAPH_HEIGHT = "70vh"
GRAPH_CONFIG = {"displayModeBar": False}
HIDDEN_STYLE = {"display": "none"}
MAP_CONTAINER_STYLE = {"flex": "3 1 600px", "minWidth": "320px"}
PANEL_CONTAINER_STYLE = {**CARD_STYLE, "flex": "1 1 280px", "minWidth": "260px"}

CHOROPLETH_COLORS = {
    # Transparent country fills; only outlines convey country boundaries.
    "colorscale": [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
    "marker_line_color": COLORS["border"],
    "marker_line_width": 0.6,
    "hover_fill": "rgba(56, 189, 248, 0.12)",
    "hover_line_color": COLORS["accent"],
    "hover_line_width": 2.2,
}

GEO_STYLE = {
    "bgcolor": "rgba(0,0,0,0)",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
}

FIELD_LABELS = [
    ("Land area", "area_fmt"),
    ("Population", "population_fmt"),
    ("Capital", "capital"),
    ("Currency", "currency"),
    ("Government", "government"),
    ("Head of state", "head_of_state"),
    ("Head of government", "head_of_government"),
    ("Foreign minister", "foreign_minister"),
    ("Major cities", "major_cities"),
    ("Major news outlet", "news_outlet"),
    ("UN organizations", "un_organizations"),
]

LABEL_STYLE = {"fontWeight": "600", "color": COLORS["muted"]}
LINK_STYLE = {"color": COLORS["accent"]}

ERROR_BANNER_STYLE = {
    "backgroundColor": "#451a1a",
    "border": "1px solid #f87171",
    "borderRadius": "8px",
    "color": "#fecaca",
    "padding": "12px 16px",
    "marginBottom": "16px",
    "textAlign": "center",
}

REST_COUNTRIES_API_LABEL = "REST Countries API"
WORLD_BANK_API_LABEL = "World Bank Open Data API"
