# CrimeCity3K

Interactive web map visualizing Swedish police events (2022-2025) aggregated to H3 hexagonal cells with population normalization.

## Features

- **H3 Hexagonal Aggregation**: Events aggregated to multiple resolutions (4, 5, 6)
- **Population Normalization**: Crime rates per 10,000 residents using official SCB data
- **SQL-Driven Pipeline**: All transformations in SQL templates using DuckDB
- **Vector Tiles**: PMTiles format for efficient web rendering
- **Interactive Map**: MapLibre GL-based visualization

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Run tests
make test

# Build data pipeline
make pipeline-all

# Start development server
make dev
```

## Development

See [TODO.md](TODO.md) for detailed implementation plan.

## Data Sources

- **Police Events**: [polisen.se/api/events](https://polisen.se/api/events)
- **Population Data**: [SCB Geospatial Statistics](https://geodata.scb.se)

## License

Code: Public Domain
Data: Subject to source terms of use
