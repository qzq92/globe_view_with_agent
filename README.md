# globe_view_with_agent

An interactive **World Map Country Dashboard** built with Python and Plotly Dash.
Hover over any country on the world map to see its key information:

- Land area
- Population
- Capital
- Government type
- Leader
- Major news outlet
- UN and other international organization memberships
- Singapore embassy/consulate location and official contact link

The hovered country also populates a synced side info panel.

## Data sources

- **Land area, population, capital, government type, leader, major news outlet,
  and organization memberships** are read from the
  [REST Countries API v5](https://restcountries.com/) using an API key stored in
  `.env` as `REST_COUNTRIES_API_KEY`. When REST Countries does not provide area,
  population, or capital, the loader falls back to the
  [World Bank Open Data API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)
  for those fields.
- Successful API responses are cached locally under `data/cache/` for 24 hours,
  so repeat startups skip the network when the cache is still fresh.
- Fields that are unavailable from the API response show `N/A`.
- **Singapore embassy/consulate information** comes from
  [`data/consulates_singapore.json`](data/consulates_singapore.json). Countries
  without a curated entry show `No Singapore mission listed`.

> Note: `truststore` is included so the app uses your operating system's
> certificate store. This lets the HTTPS API calls succeed on networks with
> corporate TLS inspection, where Python's bundled certificates would be rejected.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

1. Create a `.env` file in the project root:

```env
REST_COUNTRIES_API_KEY=your_api_key_here
```

2. Install dependencies:

```bash
uv sync
```

## Run

```bash
uv run python app.py
```

Then open http://127.0.0.1:8050 in your browser.

## Extending Singapore mission data

To add or correct a Singapore-based embassy, high commission, or consulate, edit
[`data/consulates_singapore.json`](data/consulates_singapore.json). Each entry is
keyed by ISO-3 code:

```json
{
  "USA": {
    "mission_name": "Embassy of the United States of America in Singapore",
    "address": "27 Napier Road, Singapore 258508",
    "official_link": "https://sg.usembassy.gov/",
    "note": ""
  }
}
```

Use the `official_link` field for the mission's official website or contact page.
If a country has no entry, the dashboard will display `No Singapore mission listed`.

## Validating Singapore mission data

Run the consulate validator before relying on new or edited mission entries:

```bash
uv run python scripts/validate_consulates_singapore.py
```

The script validates the JSON schema, checks ISO-3 codes against the dashboard
country data, verifies official links are reachable, and warns if the linked page
does not appear Singapore-related. To run only local checks without HTTP requests:

```bash
uv run python scripts/validate_consulates_singapore.py --offline
```

## CI

GitHub Actions runs on every push and pull request to `main`/`master`:

- **Dependency vulnerability audit** — `uv run --with pip-audit pip-audit` scans the locked environment for known CVEs
- **Pylint** — lint checks on `scripts/`
- **Offline consulate validation** — schema and ISO-3 checks without network calls

Run the audit locally:

```bash
uv sync --all-groups
uv run --with pip-audit pip-audit --progress-spinner off --skip-editable
uv run pylint scripts
```
