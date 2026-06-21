"""Dash dashboard layout, map, and UI configuration."""

APP_TITLE = "World Map Country Dashboard"

MAP_PROJECTION = "natural earth"
GLOBE_PROJECTION = "orthographic"
MAP_VIEW_TAB_MAP = "map"
MAP_VIEW_TAB_GLOBE = "globe"

CUSTOMDATA_COLUMNS = [
    "name",
    "area_fmt",
    "population_fmt",
    "capital",
    "government",
    "leader",
    "news_outlet",
    "un_organizations",
    "consulate_status",
]

HOVERTEMPLATE = (
    "<b>%{customdata[0]}</b><br>"
    "Land area: %{customdata[1]}<br>"
    "Population: %{customdata[2]}<br>"
    "Capital: %{customdata[3]}<br>"
    "Government: %{customdata[4]}<br>"
    "Leader: %{customdata[5]}<br>"
    "Major news outlet: %{customdata[6]}<br>"
    "UN organizations: %{customdata[7]}<br>"
    "Singapore mission: %{customdata[8]}"
    "<extra></extra>"
)

COLORS = {
    "background": "#0f172a",
    "card": "#1e293b",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "accent": "#38bdf8",
    "border": "#334155",
    "white": "#ffffff",
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
MAP_CONTAINER_STYLE = {"flex": "3 1 600px", "minWidth": "320px"}
PANEL_CONTAINER_STYLE = {**CARD_STYLE, "flex": "1 1 280px", "minWidth": "260px"}

CHOROPLETH_COLORS = {
    "colorscale": "Viridis",
    "colorbar_title": "Population",
    "marker_line_color": COLORS["white"],
    "marker_line_width": 0.4,
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
    ("Government", "government"),
    ("Leader", "leader"),
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
