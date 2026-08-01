# globe_view_with_agent

An interactive **World Map Country Dashboard** built with Python and Plotly Dash.
It combines country facts, Singapore diplomatic missions, and live satellite
tracking in one browser UI.

## What the app does

Open the dashboard, wait for data to load, then explore in three views:

| Tab | Purpose |
| --- | --- |
| **Map** | Flat world map (natural-earth). Transparent country fills with outline highlight on hover. |
| **Globe** | Same country outlines on an orthographic globe projection. |
| **3D Satellite** | CesiumJS 3D globe of tracked satellites (space stations and weather). |

### Country exploration

Hover any country on Map or Globe to see:

- Land area and population
- Capital and government type
- Head of state, head of government, and foreign minister (UN Protocol list)
- Major cities (CountriesNow API)
- Major news outlet
- UN and other international organization memberships
- Singapore embassy/consulate location and official contact link

The hovered country also fills a synced side info panel.

## Screenshots

- Image folder: [`img/`](img/)
- Map view sample: [`img/map_view.jpg`](img/map_view.jpg)
- Globe + satellite sample: [`img/Globeview_satellite.jpg`](img/Globeview_satellite.jpg)

### Satellite tracking

Space Stations and Weather satellites appear as markers on Map/Globe and as
entities in the 3D Satellite tab. Positions refresh about every **3 minutes**.
A category checklist filters which groups are shown, and the banner shows when
positions were last updated. Hover a satellite marker on Map/Globe to highlight
it and show enriched metadata (NORAD ID, altitude, country, owner, purpose).

## How it works (surface level)

1. **Startup** — The app shows a loading screen, then loads country and mission
   data once per process (`data_loader` + helpers). API responses are cached
   under `data/cache/` so repeat startups skip the network when the cache is fresh.
2. **Country UI** — Plotly choropleth callbacks sync map hover data with the
   side panel. Map vs Globe only changes the geo projection.
3. **Satellite pipeline** — `helpers/satellite.py` fetches TLEs from Celestrak,
   computes current lat/lon/altitude with Skyfield, and merges open metadata from
   the UCS Satellite Database. Shared state (`dcc.Store`) feeds both 2D overlays
   and the 3D tab from the same filtered dataset.
4. **3D view** — CesiumJS is loaded from CDN; `assets/satellite3d.js` renders
   entities when the 3D Satellite tab is active.

```text
APIs / PDFs / JSON  -->  data_loader / helpers  -->  Dash layout + callbacks
Celestrak TLEs + UCS -->  helpers/satellite.py  -->  Map/Globe + Cesium 3D tab
```

## How it's built

The dashboard is a local Python web app. Dependencies are declared in
[`pyproject.toml`](pyproject.toml) and installed with [uv](https://docs.astral.sh/uv/).

| Library | Role in this project |
| --- | --- |
| [Dash](https://dash.plotly.com/) | Web UI — layout, tabs, callbacks, stores, and side panels |
| [Plotly](https://plotly.com/python/) | Choropleth map, globe projection, and 2D satellite markers |
| [CesiumJS](https://cesium.com/platform/cesiumjs/) | 3D Satellite tab (CDN scripts + `assets/satellite3d.js`) |
| [Skyfield](https://rhodesmill.org/skyfield/) | Propagates satellite positions from TLE data |
| [pandas](https://pandas.pydata.org/) | Loads, merges, and formats country and satellite records |
| [requests](https://requests.readthedocs.io/) | HTTP client for APIs, Celestrak, UCS, and MFA |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) | HTML parsing for MFA website scraping |
| [pypdf](https://pypdf.readthedocs.io/) | PDF parsing for Singapore MFA diplomatic list and UN Protocol PDF |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Reads `REST_COUNTRIES_API_KEY` from `.env` at startup |
| [truststore](https://github.com/sethmlarson/truststore) | Uses the OS certificate store for HTTPS (helps on Windows and corporate networks) |

Dash runs on **Flask** and **Werkzeug** (installed transitively). Those versions are
pinned in `pyproject.toml` so known CVEs in older releases are not pulled in.

Development-only tools (installed with `uv sync --all-groups`):

| Library | Role |
| --- | --- |
| [pip-audit](https://pypi.org/project/pip-audit/) | Scans locked dependencies for known vulnerabilities in CI |
| [pylint](https://pylint.readthedocs.io/) | Static analysis for scripts under `scripts/` |

## Data sources

- **Land area, population, capital, government type, major news outlet,
  and organization memberships** are read from the
  [REST Countries API v5](https://restcountries.com/) using an API key stored in
  `.env` as `REST_COUNTRIES_API_KEY`. When REST Countries does not provide area,
  population, or capital, the loader falls back to the
  [World Bank Open Data API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)
  for those fields.
- **Major cities** are fetched from the free [CountriesNow API](https://countriesnow.space/)
  (up to 5 major cities per country).
- **Head of state, head of government, and foreign minister** are parsed from the
  UN Protocol and Liaison Services public list
  ([PDF](https://www.un.org/dgacm/sites/www.un.org.dgacm/files/Documents_Protocol/hspmfmlist.pdf)).
  Results are cached under `data/cache/un_protocol_officials.json`.
- **Satellite positions** use public [Celestrak](https://celestrak.org/) TLE groups
  (Space Stations and Weather). TLEs are cached under `data/cache/satellite/`.
- **Satellite metadata** (country of operator, owner, purpose) is enriched from the
  open [UCS Satellite Database](https://www.ucsusa.org/resources/satellite-database)
  text export when available.
- Successful country API responses are cached locally under `data/cache/` for 24 hours,
  so repeat startups skip the network when the cache is still fresh.
- Fields that are unavailable from the API response show `N/A`.
- **Singapore embassy/consulate information** comes from
  [`data/consulates_singapore.json`](data/consulates_singapore.json). Countries
  without a curated entry show `No Singapore mission listed`.

> Note: On Windows, `helpers/ssl_patch.py` initializes TLS before any HTTP calls.
> Together with `truststore`, this helps API requests succeed on networks with
> corporate TLS inspection, where Python's bundled certificates would be rejected.

## Setup

Requires **Python 3.12** and [uv](https://docs.astral.sh/uv/). The repo includes a
[`.python-version`](.python-version) file so `uv sync` selects 3.12 automatically.

1. Create a `.env` file in the project root:

```env
REST_COUNTRIES_API_KEY=your_api_key_here
```

2. Install dependencies (uv will install Python 3.12 if needed):

```bash
uv python install 3.12
uv sync
```

## Run

```bash
uv run python app.py
```

Then open http://127.0.0.1:8050 in your browser.

First load may take a moment while country APIs, mission data, and satellite TLEs
are fetched (or read from cache).

## Extending Singapore mission data

### Manual editing

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

### Auto-refresh from MFA (automatic on startup)

The app automatically attempts to refresh consulate data from the Singapore Ministry
of Foreign Affairs (MFA) website on startup. To disable this, edit
[`config/api.py`](config/api.py) and set:

```python
AUTO_REFRESH_CONSULATES = False
```

To manually trigger a refresh:

```bash
uv run python -m scripts.fetch_mfa_representatives
```

This fetches from [MFA's Foreign Representatives directory](https://www.mfa.gov.sg/visiting-singapore/foreign-representatives-to-singapore/)
and merges new missions with existing data (preserving manually curated details).

## Validating Singapore mission data

Run the consulate validator before relying on new or edited mission entries:

```bash
uv run python -m scripts.validate_consulates_singapore
```

The script validates the JSON schema, checks ISO-3 codes against the dashboard
country data, verifies official links are reachable, and warns if the linked page
does not appear Singapore-related. To run only local checks without HTTP requests:

```bash
uv run python -m scripts.validate_consulates_singapore --offline
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
