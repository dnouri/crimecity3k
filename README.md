# CrimeCity3K

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)

Interactive web map visualizing Swedish police events (2022-2025) aggregated to H3 hexagonal cells with population normalization.

## Features

- **H3 Hexagonal Aggregation**: Events aggregated to multiple resolutions (r4 ~25km, r5 ~8km, r6 ~3km)
- **Population Normalization**: Crime rates per 10,000 residents using official SCB data
- **Category Filtering**: Filter by 8 crime categories (traffic, property, violence, etc.)
- **SQL-Driven Pipeline**: All transformations via DuckDB SQL templates
- **Vector Tiles**: PMTiles format for efficient web rendering
- **Interactive Map**: MapLibre GL JS with automatic resolution switching

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- [Tippecanoe](https://github.com/felt/tippecanoe) for PMTiles generation

### Installation

```bash
git clone <repo-url>
cd crimecity3k
make install
```

### View the Map

```bash
# Start local server
make serve

# Open in browser
# http://localhost:8080/static/index.html
```

### Build Data Pipeline

```bash
# Download population data and build complete pipeline
make pipeline-all
```

## Development

### Testing

```bash
# Run all tests with coverage
make test

# Run unit tests only (fast, no browser)
make test-unit

# Run E2E browser tests
make test-e2e
```

### Code Quality

```bash
# Run linting and type checking
make check

# Auto-format code
make format
```

## Architecture

```
crimecity3k/
├── crimecity3k/           # Python package
│   ├── config.py          # TOML configuration management
│   ├── h3_processing.py   # Population and event H3 aggregation
│   ├── tile_generation.py # GeoJSON export for tiles
│   ├── pmtiles.py         # PMTiles generation via Tippecanoe
│   └── sql/               # DuckDB SQL templates
│       ├── population_to_h3.sql
│       ├── h3_aggregation.sql
│       └── h3_to_geojson.sql
├── static/                # Frontend (no build step)
│   ├── index.html         # HTML structure
│   ├── app.js             # MapLibre + PMTiles (~350 lines)
│   └── style.css          # Responsive CSS
├── tests/                 # pytest test suite
│   ├── test_*.py          # Unit and integration tests
│   └── test_frontend_e2e.py  # Playwright E2E tests
├── data/                  # Generated data (gitignored)
│   ├── h3/                # H3 aggregated Parquet files
│   └── tiles/             # GeoJSONL and PMTiles
└── Makefile               # Build orchestration
```

### Data Pipeline

```
SCB Population Grid (1km²)
    ↓ population_to_h3.sql
H3 Population (r4, r5, r6)
    ↓
Police Events (events.parquet)
    ↓ h3_aggregation.sql + population join
H3 Events with Rates (events_rN.parquet)
    ↓ h3_to_geojson.sql
GeoJSONL (h3_rN.geojsonl.gz)
    ↓ Tippecanoe
PMTiles (h3_rN.pmtiles)
    ↓
Interactive Web Map
```

### Frontend

The frontend is vanilla JavaScript with no build step:
- **MapLibre GL JS**: Map rendering with OSM base tiles
- **PMTiles**: Client-side vector tile decoding
- **Automatic Resolution**: Switches H3 resolution based on zoom level
- **Display Modes**: Absolute counts or normalized rates per 10,000

## Make Targets

```bash
make help              # Show all available targets
make install           # Install dependencies
make test              # Run all tests
make test-unit         # Run unit tests only
make test-e2e          # Run E2E browser tests
make serve             # Start local server
make check             # Linting and type checking
make format            # Auto-format code
make pipeline-all      # Build complete data pipeline
make clean             # Remove generated files
```

## Data Sources

- **Police Events**: [polisen.se/api/events](https://polisen.se/api/events) (2022-2025)
- **Population Data**: [SCB Geospatial Statistics](https://geodata.scb.se) (1km² grid, 2024)

## Known Limitations

### City-Level Coordinates

The Swedish Police API reports events at **city centroid coordinates** rather than actual incident locations. This means all events for Stockholm appear at a single point (59.33°N, 18.07°E), all Malmö events at another point, and so on.

This affects H3 aggregation differently at each resolution:

| City | Metro Pop | r6 Cell Pop | Coverage | Rate Inflation |
|------|-----------|-------------|----------|----------------|
| Stockholm | 975,000 | ~252,000 | 26% | ~3.9x |
| Gothenburg | 608,000 | ~168,000 | 28% | ~3.6x |
| Malmö | 352,000 | ~142,000 | 40% | ~2.5x |
| Lund | 95,000 | ~22,000 | 23% | ~4.3x |

At coarser resolutions (r4 ~1,100km², r5 ~250km²), cells are large enough to capture most of a metro area's population, so rates are reasonably accurate. At r6 (~60km²), the centroid cell contains only 23-40% of the metro population while receiving 100% of events, inflating apparent rates by 2.5-4.3x.

**Current approach**: The frontend displays only r4 and r5. The backend generates r6 for potential future use if better coordinate data becomes available.

**Future improvement**: Geocoding events to actual addresses would enable accurate fine-grained analysis.

## Configuration

Settings are managed via `config.toml`:

```toml
[aggregation]
resolutions = [4, 5, 6]  # H3 resolutions to generate

[duckdb]
memory_limit = "4GB"
threads = 4
```

## License

Code: Public Domain
Data: Subject to source terms of use
