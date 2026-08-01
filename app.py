"""World Map Country Dashboard.

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
from dash import ClientsideFunction, Dash, Input, Output, dcc, html
from dash.exceptions import PreventUpdate

from config.dashboard import (
    APP_TITLE,
    CHOROPLETH_COLORS,
    COLORS,
    CONTENT_ROW_STYLE,
    CUSTOMDATA_COLUMNS,
    FIELD_LABELS,
    GEO_STYLE,
    GLOBE_PROJECTION,
    GRAPH_CONFIG,
    GRAPH_HEIGHT,
    HOVERTEMPLATE,
    LABEL_STYLE,
    LAYOUT_STYLE,
    LINK_STYLE,
    MAP_CONTAINER_STYLE,
    MAP_PROJECTION,
    MAP_VIEW_TAB_GLOBE,
    MAP_VIEW_TAB_MAP,
    MAP_VIEW_TAB_SATELLITE_3D,
    MAP_VIEW_TABS_STYLE,
    PANEL_CONTAINER_STYLE,
    SUBTITLE_STYLE,
    TAB_COLORS,
)
from config.data import MISSING
from config.server import DEBUG, HOST, PORT
from data_loader import load_country_data, CountryDataLoad
from helpers.banner import build_api_error_banner
from helpers.formatting import format_number
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
SATELLITE_CATEGORIES = ["Space Stations", "Weather"]
SATELLITE_COLORS = {
    "Space Stations": "#ff4d4f",
    "Weather": "#73d13d",
}
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
        result.df["consulate_status"] = result.df.apply(
            lambda row: row["consulate_name"]
            if row["consulate_name"] != MISSING
            else row["consulate_note"],
            axis=1,
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


def _get_satellite_data() -> tuple[pd.DataFrame, datetime | None]:
    """Return shared satellite dataframe refreshed every 3 minutes."""
    global _satellite_df, _satellite_updated_at
    now = datetime.now(UTC)

    if (
        _satellite_updated_at is not None
        and now - _satellite_updated_at < timedelta(seconds=SATELLITE_REFRESH_SECONDS)
    ):
        return _satellite_df.copy(), _satellite_updated_at

    with _satellite_lock:
        now = datetime.now(UTC)
        if (
            _satellite_updated_at is not None
            and now - _satellite_updated_at < timedelta(seconds=SATELLITE_REFRESH_SECONDS)
        ):
            return _satellite_df.copy(), _satellite_updated_at

        _satellite_df = get_satellite_positions()
        _satellite_updated_at = now
        return _satellite_df.copy(), _satellite_updated_at


def _build_satellite_store(selected_categories: list[str] | None) -> dict[str, Any]:
    categories = SATELLITE_CATEGORIES if selected_categories is None else selected_categories
    satellites, updated_at = _get_satellite_data()

    if satellites.empty:
        return {"satellites": [], "categories": categories, "updated_at": None}

    filtered = satellites[satellites["category"].isin(categories)].copy()
    filtered["alt_m"] = filtered["elevation_km"] * 1000
    filtered["marker_color"] = filtered["category"].map(SATELLITE_COLORS).fillna("#9ca3af")

    records = filtered[
        [
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
    ].to_dict("records")
    return {
        "satellites": records,
        "categories": categories,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


def _satellite_update_label(store_data: dict[str, Any] | None) -> str:
    if not store_data:
        return "Last satellite update: pending"
    updated_at = store_data.get("updated_at")
    count = len(store_data.get("satellites", []))
    if not updated_at:
        return f"Last satellite update: unavailable ({count} shown)"
    timestamp = datetime.fromisoformat(updated_at).astimezone()
    return f"Last satellite update: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ({count} shown)"


def _store_to_satellite_df(store_data: dict[str, Any] | None) -> pd.DataFrame:
    if not store_data:
        return pd.DataFrame()
    records = store_data.get("satellites", [])
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def build_figure(
    projection_type: str = MAP_PROJECTION,
    satellite_df: pd.DataFrame | None = None,
    selected_satellite: dict[str, Any] | None = None,
    hover_iso3: str | None = None,
) -> go.Figure:
    is_globe = projection_type == GLOBE_PROJECTION
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

    if satellite_df is not None and not satellite_df.empty:
        selected_norad = None
        if selected_satellite:
            selected_norad = selected_satellite.get("norad_id")

        for category, color in SATELLITE_COLORS.items():
            cat_df = satellite_df[satellite_df["category"] == category]
            if cat_df.empty:
                continue

            sizes = [
                11 if selected_norad and str(row.norad_id) == str(selected_norad) else 7
                for row in cat_df.itertuples()
            ]

            figure.add_trace(
                go.Scattergeo(
                    lon=cat_df["lon"],
                    lat=cat_df["lat"],
                    text=cat_df["name"],
                    customdata=cat_df[
                        [
                            "norad_id",
                            "category",
                            "elevation_km",
                            "country",
                            "owner",
                            "purpose",
                        ]
                    ].to_numpy(),
                    hovertemplate=(
                        "<b>%{text}</b><br><br>"
                        "NORAD: %{customdata[0]}<br>"
                        "Category: %{customdata[1]}<br>"
                        "Altitude: %{customdata[2]:.1f} km<br>"
                        "Country: %{customdata[3]}<br>"
                        "Owner: %{customdata[4]}<br>"
                        "Purpose: %{customdata[5]}<br>"
                        "<extra></extra>"
                    ),
                    mode="markers",
                    marker=dict(
                        size=sizes,
                        color=color,
                        symbol="circle",
                        line=dict(width=1, color="rgba(255, 255, 255, 0.6)"),
                    ),
                    name=category,
                )
            )

    # Keep hover highlight as top-most country trace so it remains visible.
    if hover_iso3 and hover_iso3 in _iso3_index:
        figure.add_trace(
            go.Choropleth(
                locations=[hover_iso3],
                locationmode="ISO-3",
                z=[1],
                colorscale=[
                    [0, CHOROPLETH_COLORS["hover_fill"]],
                    [1, CHOROPLETH_COLORS["hover_fill"]],
                ],
                showscale=False,
                marker_line_color=CHOROPLETH_COLORS["hover_line_color"],
                marker_line_width=CHOROPLETH_COLORS["hover_line_width"],
                hoverinfo="skip",
                showlegend=False,
            )
        )

    figure.update_layout(
        margin=GEO_STYLE["margin"],
        geo=dict(
            showframe=is_globe,
            showcoastlines=True,
            showland=True,
            landcolor="rgba(30, 41, 59, 0.35)",
            showocean=True,
            oceancolor="rgba(15, 23, 42, 0.6)",
            showcountries=False,
            projection_type=projection_type,
            bgcolor=GEO_STYLE["bgcolor"],
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


def _info_rows(row: pd.Series) -> list[Any]:
    children = []
    for label, key in FIELD_LABELS:
        value = str(row[key])
        if key == "un_organizations" and value not in (MISSING, "None"):
            org_items = [html.Li(org.strip()) for org in value.split(";")]
            children.append(
                html.Div(
                    [
                        html.Span(f"{label}: ", style=LABEL_STYLE),
                        html.Ul(
                            org_items,
                            style={
                                "margin": "4px 0 8px 0",
                                "paddingLeft": "20px",
                            },
                        ),
                    ],
                    style={"marginBottom": "8px"},
                )
            )
            continue

        children.append(
            html.Div(
                [
                    html.Span(f"{label}: ", style=LABEL_STYLE),
                    html.Span(value),
                ],
                style={"marginBottom": "8px"},
            )
        )
    return children


def _singapore_mission_section(row: pd.Series) -> list[Any]:
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
            html.Div(
                [
                    html.Span("Mission: ", style=LABEL_STYLE),
                    html.Span(row["consulate_name"]),
                ],
                style={"marginBottom": "8px"},
            ),
            html.Div(
                [
                    html.Span("Location: ", style=LABEL_STYLE),
                    html.Span(row["consulate_address"]),
                ],
                style={"marginBottom": "8px"},
            ),
            html.Div(
                [
                    html.Span("Official link: ", style=LABEL_STYLE),
                    html.A(
                        "Open official page",
                        href=row["consulate_link"],
                        target="_blank",
                        rel="noopener noreferrer",
                        style=LINK_STYLE,
                    ),
                ],
                style={"marginBottom": "8px"},
            ),
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
    if df.empty or iso3 is None or iso3 not in _iso3_index:
        return [
            html.H3("Country details", style={"marginTop": 0}),
            html.P(
                "Hover over a country on the map to see its details.",
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
            dcc.Store(id="selected-satellite-store", data=None),
            build_api_error_banner(banner_messages),
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "gap": "16px",
                    "alignItems": "center",
                    "marginBottom": "12px",
                    "flexWrap": "wrap",
                },
                children=[
                    dcc.Checklist(
                        id="satellite-category-filter",
                        options=[
                            {"label": "Space Stations", "value": "Space Stations"},
                            {"label": "Weather", "value": "Weather"},
                        ],
                        value=SATELLITE_CATEGORIES,
                        inline=True,
                        inputStyle={"marginRight": "6px", "marginLeft": "14px"},
                        labelStyle={"color": COLORS["text"], "fontSize": "14px"},
                    ),
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
                    value=MAP_VIEW_TAB_MAP,
                    children=[
                        dcc.Tab(label="Map", value=MAP_VIEW_TAB_MAP),
                        dcc.Tab(label="Globe", value=MAP_VIEW_TAB_GLOBE),
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
                                figure=build_figure(MAP_PROJECTION),
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
                style={"display": "none"},
                children=[
                    html.Div(
                        style=CONTENT_ROW_STYLE,
                        children=[
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
                                        "Hover a satellite in 2D map/globe to highlight it in 3D.",
                                        style={"color": COLORS["muted"]},
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            ),
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

# Start with loading layout
app.layout = build_loading_layout()


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
    Input("satellite-category-filter", "value"),
)
def refresh_satellite_state(
    _n_intervals: int,
    selected_categories: list[str] | None,
) -> tuple[dict[str, Any], str]:
    store_data = _build_satellite_store(selected_categories)
    return store_data, _satellite_update_label(store_data)


@app.callback(
    Output("world-map", "figure"),
    Input("map-view-tabs", "value"),
    Input("satellite-store", "data"),
    Input("selected-satellite-store", "data"),
    Input("world-map", "hoverData"),
)
def update_map_projection(
    view: str,
    satellite_store: dict[str, Any] | None,
    selected_satellite: dict[str, Any] | None,
    hover_data: dict[str, Any] | None,
) -> go.Figure:
    if view == MAP_VIEW_TAB_SATELLITE_3D:
        # Skip expensive satellite overlay updates while 3D tab is active.
        return build_figure(MAP_PROJECTION)

    hover_iso3 = None
    if hover_data and hover_data.get("points"):
        for point in hover_data["points"]:
            location = point.get("location")
            # Country choropleth points include ISO3 location, satellite markers do not.
            if location and location in _iso3_index:
                hover_iso3 = location
                break

    projection = (
        GLOBE_PROJECTION if view == MAP_VIEW_TAB_GLOBE else MAP_PROJECTION
    )
    satellite_df = _store_to_satellite_df(satellite_store)
    return build_figure(
        projection,
        satellite_df,
        selected_satellite,
        hover_iso3=hover_iso3,
    )


@app.callback(
    Output("map-section", "style"),
    Output("satellite-3d-section", "style"),
    Input("map-view-tabs", "value"),
)
def toggle_view_sections(active_tab: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if active_tab == MAP_VIEW_TAB_SATELLITE_3D:
        return {**CONTENT_ROW_STYLE, "display": "none"}, {"display": "block"}
    return CONTENT_ROW_STYLE, {"display": "none"}


@app.callback(
    Output("selected-satellite-store", "data"),
    Input("world-map", "hoverData"),
)
def sync_selected_satellite(hover_data: dict[str, Any] | None) -> dict[str, Any]:
    if not hover_data or not hover_data.get("points"):
        raise PreventUpdate

    point = hover_data["points"][0]
    if point.get("location"):
        raise PreventUpdate

    custom_data = point.get("customdata", [])
    if len(custom_data) < 6:
        raise PreventUpdate
    return {
        "name": point.get("text", "Unknown"),
        "norad_id": custom_data[0],
        "category": custom_data[1],
        "elevation_km": custom_data[2],
        "country": custom_data[3],
        "owner": custom_data[4],
        "purpose": custom_data[5],
    }


@app.callback(Output("info-panel", "children"), Input("world-map", "hoverData"))
def update_panel(hover_data: dict[str, Any] | None) -> list[Any]:
    if not hover_data or not hover_data.get("points"):
        return render_panel(None)
    iso3 = hover_data["points"][0].get("location")
    return render_panel(iso3)


@app.callback(
    Output("satellite-info-panel", "children"),
    Input("satellite-store", "data"),
    Input("selected-satellite-store", "data"),
)
def update_satellite_panel(
    satellite_store: dict[str, Any] | None,
    selected_satellite: dict[str, Any] | None,
) -> list[Any]:
    count = len((satellite_store or {}).get("satellites", []))
    content: list[Any] = [
        html.H3("Satellite details", style={"marginTop": 0}),
        html.P(f"Visible satellites: {count}", style={"color": COLORS["muted"]}),
    ]
    if selected_satellite:
        content.extend(
            [
                html.H4(selected_satellite.get("name", "Unknown"), style={"marginBottom": "8px"}),
                html.Div(
                    [
                        html.Span("NORAD: ", style=LABEL_STYLE),
                        html.Span(str(selected_satellite.get("norad_id", "Unknown"))),
                    ],
                    style={"marginBottom": "8px"},
                ),
                html.Div(
                    [
                        html.Span("Category: ", style=LABEL_STYLE),
                        html.Span(selected_satellite.get("category", "Unknown")),
                    ],
                    style={"marginBottom": "8px"},
                ),
                html.Div(
                    [
                        html.Span("Altitude: ", style=LABEL_STYLE),
                        html.Span(f"{selected_satellite.get('elevation_km', 0):.1f} km"),
                    ],
                    style={"marginBottom": "8px"},
                ),
                html.Div(
                    [
                        html.Span("Country: ", style=LABEL_STYLE),
                        html.Span(selected_satellite.get("country", "Unknown")),
                    ],
                    style={"marginBottom": "8px"},
                ),
                html.Div(
                    [
                        html.Span("Owner: ", style=LABEL_STYLE),
                        html.Span(selected_satellite.get("owner", "Unknown")),
                    ],
                    style={"marginBottom": "8px"},
                ),
                html.Div(
                    [
                        html.Span("Purpose: ", style=LABEL_STYLE),
                        html.Span(selected_satellite.get("purpose", "Unknown")),
                    ],
                    style={"marginBottom": "8px"},
                ),
            ]
        )
    else:
        content.append(
            html.P(
                "Hover a satellite marker in Map/Globe view to inspect and highlight it in 3D.",
                style={"color": COLORS["muted"]},
            )
        )
    return content


app.clientside_callback(
    ClientsideFunction(namespace="satellite3d", function_name="render"),
    Output("cesium-render-flag", "children"),
    Input("satellite-store", "data"),
    Input("selected-satellite-store", "data"),
    Input("map-view-tabs", "value"),
)


# Wrap layout in a container for dynamic updates
app.layout = html.Div(id="app-container", children=app.layout)


if __name__ == "__main__":
    app.run(debug=DEBUG, host=HOST, port=PORT)
