# CrimeCity3K

[![CI](https://github.com/dnouri/crimecity3k/actions/workflows/ci.yml/badge.svg)](https://github.com/dnouri/crimecity3k/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

Interactive map of Swedish police events with drill-down search, category filtering, and population-normalized crime rates across all 290 municipalities.

## Quick Start

```bash
# Install dependencies
make install

# Fetch events data and build pipeline
make fetch-events
make pipeline-all

# Start local server
make serve
# Open http://localhost:8080/static/index.html
```

**Prerequisites:** Python 3.13+, [uv](https://github.com/astral-sh/uv), [Tippecanoe](https://github.com/felt/tippecanoe)

## Features

**Interactive Map**
- Vector tiles rendered with MapLibre GL JS and PMTiles
- Municipality boundaries with event counts and crime rates
- H3 hexagonal cells for finer granularity at higher zoom levels
- Choropleth coloring by absolute count or rate per 10,000 population

**Event Drill-Down**
- Click any region to browse individual events
- Full-text search with Swedish stemming ("stöld" matches "stölder")
- Filter by 8 crime categories: traffic, property, violence, narcotics, fraud, public order, weapons, other
- Date range presets (7d, 30d, 90d) or custom date picker
- Paginated results with event details and links to police reports

**Responsive Design**
- Desktop: slide-out drawer for event list
- Mobile: bottom sheet with touch-friendly controls
- Keyboard shortcuts (`S` search, `Esc` close, `?` help)

**Privacy Protection**
- Hides individual event details when fewer than 3 events in a region
- Aggregate counts still visible on map

## Architecture

```
crimecity3k/
├── crimecity3k/
│   ├── api/                    # FastAPI backend
│   │   ├── main.py             # App, routes, static file serving
│   │   ├── queries.py          # DuckDB event queries
│   │   ├── fts.py              # Full-text search index
│   │   ├── categories.py       # Event type → category mapping
│   │   └── schemas.py          # Pydantic request/response models
│   ├── municipality_*.py       # Municipality data processing
│   └── sql/
│       └── municipality_aggregation.sql
├── static/                     # Frontend (no build step)
│   ├── index.html
│   ├── app.js                  # MapLibre + drill-down UI (~1400 lines)
│   └── style.css
├── tests/
│   ├── test_*.py               # pytest unit/integration tests
│   └── test_frontend_e2e.py    # Playwright browser tests
├── data/                       # Generated data (gitignored)
│   ├── events.parquet          # Source events
│   ├── municipalities/         # Aggregated parquet files
│   └── tiles/                  # GeoJSONL and PMTiles
└── Makefile                    # Build orchestration
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/events` | Query events by H3 cell or location with filtering |
| `GET /api/types` | Category → event types hierarchy for filter UI |
| `GET /health` | Health check with event count |
| `GET /docs` | Interactive OpenAPI documentation |

**Query parameters for `/api/events`:**
- `h3_cell` or `location_name` (required, mutually exclusive)
- `start_date`, `end_date` — date range filter
- `categories`, `types` — category/type filter
- `search` — full-text search query
- `page`, `per_page` — pagination (max 100 per page)

## Data Pipeline

```
Upstream: polisen-se-events-history (GitHub release)
    ↓ make fetch-events
events.parquet (100k+ police events, 2022-present)
    ↓ municipality_aggregation.sql
Municipality aggregates with category counts + type breakdown
    ↓ GeoJSON export
GeoJSONL (municipalities.geojsonl.gz)
    ↓ Tippecanoe
PMTiles (municipalities.pmtiles)
    ↓
Interactive web map
```

## Development

```bash
make test          # All tests with coverage
make test-unit     # Unit tests only (fast)
make test-e2e      # Playwright browser tests
make check         # Lint (ruff) + type check (mypy)
make format        # Auto-format code
make help          # All available targets
```

## Deployment

```bash
make deploy        # Build container, upload, and deploy
make deploy-status # Check production status
make deploy-logs   # View container logs
```

## Data Sources

- **Police Events**: [polisen-se-events-history](https://github.com/dnouri/polisen-se-events-history) — daily scrapes from polisen.se API
- **Municipality Boundaries**: Swedish Land Survey (Lantmäteriet)
- **Population Data**: Statistics Sweden (SCB), 2024

## License

Code: Public Domain
Data: Subject to source terms of use
