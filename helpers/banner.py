"""Dashboard banner components."""

from __future__ import annotations

from dash import html

from config.dashboard import ERROR_BANNER_STYLE


def build_api_error_banner(messages: list[str]) -> html.Div:
    if not messages:
        return html.Div(id="api-error-banner", style={"display": "none"})

    return html.Div(
        id="api-error-banner",
        style=ERROR_BANNER_STYLE,
        children=[
            html.Strong("Unable to connect to required data sources"),
            html.Ul(
                [html.Li(message) for message in messages],
                style={"margin": "8px 0 0 0", "paddingLeft": "20px"},
            ),
        ],
    )
