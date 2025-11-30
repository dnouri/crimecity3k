# CrimeCity3K Makefile

# Configuration
CONFIG := config.toml

# Directories
DATA_DIR := data
H3_DIR := $(DATA_DIR)/h3
TILES_DIR := $(DATA_DIR)/tiles

# Code dependencies (SQL files trigger rebuilds)
SQL_DIR := crimecity3k/sql

# Phony targets
.PHONY: install check test clean help

# Default target
help:
	@echo "CrimeCity3K - Available targets:"
	@echo "  install      - Install dependencies with uv"
	@echo "  check        - Run linting and type checking"
	@echo "  test         - Run test suite with coverage"
	@echo "  clean        - Remove generated files and caches"
	@echo ""
	@echo "Data download:"
	@echo "  data/population_1km_2024.gpkg  - Download SCB population grid"
	@echo ""
	@echo "Population pipeline:"
	@echo "  pipeline-population            - Build all H3 resolutions (r4, r5, r6)"
	@echo "  data/h3/population_r4.parquet  - Convert to H3 resolution 4 (~25km)"
	@echo "  data/h3/population_r5.parquet  - Convert to H3 resolution 5 (~8km)"
	@echo "  data/h3/population_r6.parquet  - Convert to H3 resolution 6 (~3km)"
	@echo ""
	@echo "Event aggregation pipeline:"
	@echo "  pipeline-h3                    - Aggregate events for all H3 resolutions"
	@echo "  pipeline-all                   - Build complete pipeline (population + events)"
	@echo "  data/h3/events_r4.parquet      - Aggregate to H3 resolution 4 (~25km)"
	@echo "  data/h3/events_r5.parquet      - Aggregate to H3 resolution 5 (~8km)"
	@echo "  data/h3/events_r6.parquet      - Aggregate to H3 resolution 6 (~3km)"

install:
	uv sync --all-extras

check:
	uv run ruff check crimecity3k tests
	uv run ruff format --check crimecity3k tests
	uv run mypy crimecity3k tests

test:
	uv run pytest tests/ -v -n auto --cov=crimecity3k --cov-report=html --cov-report=term

clean:
	rm -rf $(H3_DIR) $(TILES_DIR)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.tmp" -delete
	rm -rf .mypy_cache .ruff_cache htmlcov .coverage

# Download SCB population data (cached, one-time)
$(DATA_DIR)/population_1km_2024.gpkg:
	@echo "═══ Downloading SCB population data ═══"
	@mkdir -p $(DATA_DIR)
	curl -L "https://geodata.scb.se/geoserver/stat/wfs?\
service=WFS&REQUEST=GetFeature&version=1.1.0&\
TYPENAMES=stat:befolkning_1km_2024&outputFormat=geopackage" \
	-o $@
	@echo "✓ Population data downloaded: $@ ($$(du -h $@ | cut -f1))"

# Pattern rule: Convert population grid to H3 cells at specified resolution
# Example: make data/h3/population_r5.parquet builds resolution 5
$(H3_DIR)/population_r%.parquet: $(DATA_DIR)/population_1km_2024.gpkg \
                                  $(SQL_DIR)/population_to_h3.sql \
                                  $(CONFIG)
	@echo "═══ Converting population to H3 resolution $* ═══"
	@mkdir -p $(H3_DIR)
	uv run python -c "from pathlib import Path; \
		from crimecity3k.config import Config; \
		from crimecity3k.h3_processing import convert_population_to_h3; \
		convert_population_to_h3(Path('$<'), Path('$@'), $*, Config.from_file('$(CONFIG)'))"
	@echo "✓ H3 conversion complete: $@ ($$(du -h $@ | cut -f1))"

# Convenience target: Build all population H3 resolutions
.PHONY: pipeline-population
pipeline-population: $(H3_DIR)/population_r4.parquet \
                     $(H3_DIR)/population_r5.parquet \
                     $(H3_DIR)/population_r6.parquet
	@echo "═══ Population pipeline complete ═══"
	@echo "  R4 (~25km): $(H3_DIR)/population_r4.parquet ($$(du -h $(H3_DIR)/population_r4.parquet | cut -f1))"
	@echo "  R5 (~8km):  $(H3_DIR)/population_r5.parquet ($$(du -h $(H3_DIR)/population_r5.parquet | cut -f1))"
	@echo "  R6 (~3km):  $(H3_DIR)/population_r6.parquet ($$(du -h $(H3_DIR)/population_r6.parquet | cut -f1))"

# Pattern rule: Aggregate events to H3 cells with category filtering
# Example: make data/h3/events_r5.parquet builds resolution 5
# Depends on: events data, population data (for normalization), SQL template, config
$(H3_DIR)/events_r%.parquet: $(DATA_DIR)/events.parquet \
                             $(H3_DIR)/population_r%.parquet \
                             $(SQL_DIR)/h3_aggregation.sql \
                             $(CONFIG)
	@echo "═══ Aggregating events to H3 resolution $* ═══"
	@mkdir -p $(H3_DIR)
	uv run python -c "from pathlib import Path; \
		from crimecity3k.config import Config; \
		from crimecity3k.h3_processing import aggregate_events_to_h3; \
		aggregate_events_to_h3(\
			Path('$(DATA_DIR)/events.parquet'), \
			Path('$(H3_DIR)/population_r$*.parquet'), \
			Path('$@'), \
			$*, \
			Config.from_file('$(CONFIG)'))"
	@echo "✓ H3 aggregation complete: $@ ($$(du -h $@ | cut -f1))"

# Convenience target: Build all event H3 aggregations
.PHONY: pipeline-h3
pipeline-h3: $(H3_DIR)/events_r4.parquet \
             $(H3_DIR)/events_r5.parquet \
             $(H3_DIR)/events_r6.parquet
	@echo "═══ Event H3 aggregation pipeline complete ═══"
	@echo "  R4 (~25km): $(H3_DIR)/events_r4.parquet ($$(du -h $(H3_DIR)/events_r4.parquet | cut -f1))"
	@echo "  R5 (~8km):  $(H3_DIR)/events_r5.parquet ($$(du -h $(H3_DIR)/events_r5.parquet | cut -f1))"
	@echo "  R6 (~3km):  $(H3_DIR)/events_r6.parquet ($$(du -h $(H3_DIR)/events_r6.parquet | cut -f1))"

# Convenience target: Build complete pipeline (population + events)
.PHONY: pipeline-all
pipeline-all: pipeline-h3
	@echo "═══ Complete pipeline ready ═══"
