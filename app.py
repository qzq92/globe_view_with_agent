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

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

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

# Global state for cached data
_load_result: CountryDataLoad | None = None
df: pd.DataFrame = pd.DataFrame()
_iso3_index: dict[str, pd.Series] = {}


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


def build_figure(projection_type: str = MAP_PROJECTION) -> go.Figure:
    is_globe = projection_type == GLOBE_PROJECTION
    if df.empty:
        locations: list[str] = []
        values: list[float] = []
        customdata = []
    else:
        locations = df["iso3"]
        values = df["population"]
        customdata = df[CUSTOMDATA_COLUMNS].to_numpy()

    figure = go.Figure(
        data=go.Choropleth(
            locations=locations,
            locationmode="ISO-3",
            z=values,
            customdata=customdata,
            hovertemplate=HOVERTEMPLATE,
            colorscale=CHOROPLETH_COLORS["colorscale"],
            colorbar_title=CHOROPLETH_COLORS["colorbar_title"],
            marker_line_color=CHOROPLETH_COLORS["marker_line_color"],
            marker_line_width=CHOROPLETH_COLORS["marker_line_width"],
        )
    )
    figure.update_layout(
        margin=GEO_STYLE["margin"],
        geo=dict(
            showframe=is_globe,
            showcoastlines=is_globe,
            projection_type=projection_type,
            bgcolor=GEO_STYLE["bgcolor"],
        ),
        paper_bgcolor=GEO_STYLE["paper_bgcolor"],
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
            build_api_error_banner(banner_messages),
            html.Div(
                dcc.Tabs(
                    id="map-view-tabs",
                    value=MAP_VIEW_TAB_MAP,
                    children=[
                        dcc.Tab(label="Map", value=MAP_VIEW_TAB_MAP),
                        dcc.Tab(label="Globe", value=MAP_VIEW_TAB_GLOBE),
                    ],
                    colors=TAB_COLORS,
                    style={"width": "fit-content"},
                ),
                style=MAP_VIEW_TABS_STYLE,
                className="map-view-tabs",
            ),
            html.Div(
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
        ],
    )


app = Dash(__name__)
app.title = APP_TITLE

# Start with loading layout
app.layout = build_loading_layout()


@app.callback(
    Output("app-container", "children"),
    Input("init-interval", "n_intervals"),
    prevent_initial_call=False,
)
def init_app(_: int) -> html.Div:
    """Load data on app start and switch from loading to main layout."""
    global _load_result

    if _load_result is None:
        print("Loading country data and diplomatic missions...")
        _load_result = load_and_process_data()
        print(f"Loaded {len(df)} countries into dashboard")

    return build_main_layout(_load_result.banner_messages if _load_result else [])


@app.callback(Output("world-map", "figure"), Input("map-view-tabs", "value"))
def update_map_projection(view: str) -> go.Figure:
    projection = (
        GLOBE_PROJECTION if view == MAP_VIEW_TAB_GLOBE else MAP_PROJECTION
    )
    return build_figure(projection)


@app.callback(Output("info-panel", "children"), Input("world-map", "hoverData"))
def update_panel(hover_data: dict[str, Any] | None) -> list[Any]:
    if not hover_data or not hover_data.get("points"):
        return render_panel(None)
    iso3 = hover_data["points"][0].get("location")
    return render_panel(iso3)


# Wrap layout in a container for dynamic updates
app.layout = html.Div(id="app-container", children=app.layout)


if __name__ == "__main__":
    app.run(debug=DEBUG, host=HOST, port=PORT)
