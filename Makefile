# CrimeCity3K Makefile

# Configuration
CONFIG := config.toml

# Directories
DATA_DIR := data
H3_DIR := $(DATA_DIR)/h3
TILES_DIR := $(DATA_DIR)/tiles

# Upstream data source (polisen-se-events-history GitHub release)
EVENTS_PARQUET_URL := https://github.com/dnouri/polisen-se-events-history/releases/download/data-latest/events.parquet

# Code dependencies (SQL files trigger rebuilds)
SQL_DIR := crimecity3k/sql

# Default target
.DEFAULT_GOAL := help

# Phony targets
.PHONY: help install check format test test-unit test-e2e serve clean \
        test-fixtures fetch-events fetch-events-force \
        pipeline-population pipeline-h3 pipeline-geojson pipeline-pmtiles pipeline-all

# ═══════════════════════════════════════════════════════════════════════════════
# DEVELOPMENT TARGETS
# ═══════════════════════════════════════════════════════════════════════════════

help: ## Show this help message
	@echo "CrimeCity3K - Swedish Police Events Map"
	@echo ""
	@echo "Development:"
	@grep -E '^[a-zA-Z0-9_-]+:.*## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ""
	@echo "Data Pipeline:"
	@echo "  fetch-events         Download events.parquet from upstream release"
	@echo "  fetch-events-force   Force re-download events.parquet"
	@echo "  pipeline-all         Build complete pipeline (population + events + tiles)"
	@echo "  pipeline-population  Build H3 population data (r4, r5, r6)"
	@echo "  pipeline-h3          Aggregate events to H3 cells"
	@echo "  pipeline-geojson     Export to GeoJSONL format"
	@echo "  pipeline-pmtiles     Generate PMTiles (requires Tippecanoe)"
	@echo ""
	@echo "Deployment:"
	@echo "  deploy               Build and deploy to production server"
	@echo "  build-container      Build container image with git SHA tag"
	@echo "  upload-container     Upload tarball to server and load image"
	@echo "  deploy-container     Stop old container, start new one"
	@echo "  install-service      Install systemd user service (one-time)"
	@echo "  deploy-status        Check deployment status on server"
	@echo "  deploy-logs          View container logs (follow mode)"
	@echo ""
	@echo "Examples:"
	@echo "  make fetch-events  # Download events data from upstream"
	@echo "  make install       # Install all dependencies"
	@echo "  make test          # Run all tests"
	@echo "  make serve         # Start local server at http://localhost:8080"
	@echo "  make pipeline-all  # Build complete data pipeline"
	@echo "  make deploy        # Deploy to production"

install: ## Install project dependencies with uv
	@echo "Installing dependencies..."
	uv sync --all-extras
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install
	@echo "Installing Playwright browsers..."
	uv run playwright install chromium
	@echo "✓ Installation complete"

check: ## Run linting and type checking
	uv run ruff check crimecity3k tests
	uv run ruff format --check crimecity3k tests
	uv run mypy crimecity3k tests

format: ## Auto-format code with ruff
	@echo "Formatting code..."
	uv run ruff format crimecity3k tests
	@echo "Fixing lint issues..."
	uv run ruff check --fix crimecity3k tests
	@echo "✓ Code formatted"

test: ## Run all tests with coverage
	uv run pytest tests/ -n auto --cov=crimecity3k --cov-report=html --cov-report=term

test-unit: ## Run unit tests only (fast, no browser)
	uv run pytest tests/ -v -n auto -m "not e2e" --cov=crimecity3k --cov-report=term

test-e2e: test-fixtures ## Run E2E browser tests with Playwright
	uv run pytest tests/test_frontend_e2e.py -v -m e2e

test-fixtures: ## Generate PMTiles fixtures for E2E tests (requires tippecanoe)
	@if ! command -v tippecanoe >/dev/null 2>&1; then \
		echo "Error: tippecanoe not found. Install with: sudo apt install tippecanoe"; \
		exit 1; \
	fi
	uv run python scripts/generate_tile_fixtures.py

serve: ## Start local development server at http://localhost:8080
	uv run python -m crimecity3k.api.main --port 8080

clean: ## Remove generated files and caches
	rm -rf $(H3_DIR) $(TILES_DIR)
	rm -f $(DATA_DIR)/events.parquet
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.tmp" -delete
	rm -rf .mypy_cache .ruff_cache htmlcov .coverage

# ═══════════════════════════════════════════════════════════════════════════════
# UPSTREAM DATA FETCH
# ═══════════════════════════════════════════════════════════════════════════════

# Download events.parquet from polisen-se-events-history GitHub release
$(DATA_DIR)/events.parquet:
	@echo "═══ Downloading events.parquet from GitHub release ═══"
	@mkdir -p $(DATA_DIR)
	curl -L -o $@ $(EVENTS_PARQUET_URL)
	@echo "✓ Downloaded: $@ ($$(du -h $@ | cut -f1))"
	@uv run python -c "import duckdb; print(f'  Events: {duckdb.query(\"SELECT COUNT(*) FROM read_parquet(\\\"$@\\\")\").fetchone()[0]:,}')"

fetch-events: $(DATA_DIR)/events.parquet ## Download events.parquet from upstream release

# Force re-download of events.parquet (bypass make cache)
fetch-events-force: ## Force re-download events.parquet
	@rm -f $(DATA_DIR)/events.parquet
	@$(MAKE) fetch-events

# ═══════════════════════════════════════════════════════════════════════════════
# SCB POPULATION DATA
# ═══════════════════════════════════════════════════════════════════════════════

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
pipeline-all: pipeline-pmtiles
	@echo "═══ Complete pipeline ready ═══"

# ═══════════════════════════════════════════════════════════════════════════════
# Tile Generation Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

# Subdirectories for tiles
GEOJSONL_DIR := $(TILES_DIR)/geojsonl
PMTILES_DIR := $(TILES_DIR)/pmtiles

# Pattern rule: Export H3 aggregated events to GeoJSONL
# Example: make data/tiles/geojsonl/h3_r5.geojsonl.gz
$(GEOJSONL_DIR)/h3_r%.geojsonl.gz: $(H3_DIR)/events_r%.parquet \
                                    $(SQL_DIR)/h3_to_geojson.sql
	@echo "═══ Exporting H3 r$* to GeoJSONL ═══"
	@mkdir -p $(GEOJSONL_DIR)
	uv run python -c "import duckdb; from pathlib import Path; \
		from crimecity3k.tile_generation import export_h3_to_geojson; \
		conn = duckdb.connect(); \
		conn.execute('INSTALL h3 FROM community; LOAD h3; INSTALL spatial; LOAD spatial'); \
		conn.execute(\"CREATE VIEW events AS SELECT * FROM '$(H3_DIR)/events_r$*.parquet'\"); \
		export_h3_to_geojson(conn, 'events', Path('$@')); \
		conn.close()"
	@echo "✓ GeoJSONL export complete: $@ ($$(du -h $@ | cut -f1))"

# Pattern rule: Generate PMTiles from GeoJSONL using Tippecanoe
# Example: make data/tiles/pmtiles/h3_r5.pmtiles
$(PMTILES_DIR)/h3_r%.pmtiles: $(GEOJSONL_DIR)/h3_r%.geojsonl.gz
	@echo "═══ Generating PMTiles for H3 r$* ═══"
	@mkdir -p $(PMTILES_DIR)
	uv run python -c "from pathlib import Path; \
		from crimecity3k.pmtiles import generate_pmtiles; \
		generate_pmtiles(Path('$<'), Path('$@'), $*)"
	@echo "✓ PMTiles complete: $@ ($$(du -h $@ | cut -f1))"

# Convenience target: Build all GeoJSONL exports
.PHONY: pipeline-geojson
pipeline-geojson: $(GEOJSONL_DIR)/h3_r4.geojsonl.gz \
                  $(GEOJSONL_DIR)/h3_r5.geojsonl.gz \
                  $(GEOJSONL_DIR)/h3_r6.geojsonl.gz
	@echo "═══ GeoJSONL export pipeline complete ═══"
	@echo "  R4: $(GEOJSONL_DIR)/h3_r4.geojsonl.gz ($$(du -h $(GEOJSONL_DIR)/h3_r4.geojsonl.gz | cut -f1))"
	@echo "  R5: $(GEOJSONL_DIR)/h3_r5.geojsonl.gz ($$(du -h $(GEOJSONL_DIR)/h3_r5.geojsonl.gz | cut -f1))"
	@echo "  R6: $(GEOJSONL_DIR)/h3_r6.geojsonl.gz ($$(du -h $(GEOJSONL_DIR)/h3_r6.geojsonl.gz | cut -f1))"

# Convenience target: Build all PMTiles
.PHONY: pipeline-pmtiles
pipeline-pmtiles: $(PMTILES_DIR)/h3_r4.pmtiles \
                  $(PMTILES_DIR)/h3_r5.pmtiles \
                  $(PMTILES_DIR)/h3_r6.pmtiles
	@echo "═══ PMTiles generation pipeline complete ═══"
	@echo "  R4: $(PMTILES_DIR)/h3_r4.pmtiles ($$(du -h $(PMTILES_DIR)/h3_r4.pmtiles | cut -f1))"
	@echo "  R5: $(PMTILES_DIR)/h3_r5.pmtiles ($$(du -h $(PMTILES_DIR)/h3_r5.pmtiles | cut -f1))"
	@echo "  R6: $(PMTILES_DIR)/h3_r6.pmtiles ($$(du -h $(PMTILES_DIR)/h3_r6.pmtiles | cut -f1))"

# ═══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENT AUTOMATION
# ═══════════════════════════════════════════════════════════════════════════════
#
# Container deployment workflow to production server. Handles building,
# uploading, and deploying containerized application with zero-downtime updates.
#
# QUICK START:
#   make deploy              - Build and deploy to production
#   make deploy-logs         - View container logs on server
#   make install-service     - Install systemd service (one-time setup)
#
# ARCHITECTURE:
#   - Immutable containers: Data baked into image (~372MB deployment)
#   - Rootless Podman: Runs as user daniel, no root privileges required
#   - Systemd user service: Automatic restart, survives reboots
#   - Health checks: Container monitors app health, systemd restarts on failure
#   - Git-based versioning: Each build tagged with commit SHA + timestamp
#
# DEPLOYMENT FLOW:
#   1. Build container with git SHA tag
#   2. Save to tarball (~370MB compressed)
#   3. Upload to server via SCP
#   4. Load image on server
#   5. Stop old container, start new one
#   6. Tag as :production for systemd to reference
#
# ═══════════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────────
# DEPLOYMENT CONFIGURATION
# ───────────────────────────────────────────────────────────────────────────────

DEPLOY_SERVER := daniel@nv-network
DEPLOY_DIR := ~/crimecity3k-deploy
DEPLOY_IMAGE_NAME := crimecity3k
DEPLOY_CONTAINER_NAME := crimecity3k
DEPLOY_GIT_SHA := $(shell git rev-parse --short HEAD)
DEPLOY_TIMESTAMP := $(shell date +%Y%m%d)
DEPLOY_TAG := $(DEPLOY_GIT_SHA)-$(DEPLOY_TIMESTAMP)
DEPLOY_TARBALL := $(DEPLOY_IMAGE_NAME)-$(DEPLOY_TAG).tar

# ───────────────────────────────────────────────────────────────────────────────
# PHONY TARGETS (deployment-specific)
# ───────────────────────────────────────────────────────────────────────────────

.PHONY: deploy build-container upload-container deploy-container \
        install-service deploy-logs deploy-status

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DEPLOYMENT TARGETS
# ═══════════════════════════════════════════════════════════════════════════════

deploy: build-container upload-container deploy-container ## Build and deploy to production
	@echo "════════════════════════════════════════════════════════════"
	@echo "✓ Deployment complete!"
	@echo "  Version:  $(DEPLOY_TAG)"
	@echo "  Server:   $(DEPLOY_SERVER)"
	@echo "  Check:    make deploy-status"
	@echo "  Logs:     make deploy-logs"
	@echo "════════════════════════════════════════════════════════════"

build-container: ## Build container image with git-based tag
	@echo "════════════════════════════════════════════════════════════"
	@echo "Building container: $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG)"
	@echo "════════════════════════════════════════════════════════════"
	podman build --format docker -t $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG) -f Containerfile .
	podman tag $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG) $(DEPLOY_IMAGE_NAME):latest
	@echo ""
	@echo "Saving to tarball: $(DEPLOY_TARBALL)"
	podman save -o $(DEPLOY_TARBALL) $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG)
	@echo ""
	@echo "✓ Build complete"
	@echo "  Image:    $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG)"
	@printf "  Tarball:  %s (%s)\n" "$(DEPLOY_TARBALL)" "$$(du -h $(DEPLOY_TARBALL) | cut -f1)"
	@echo "  SHA:      $(DEPLOY_GIT_SHA)"

upload-container: ## Upload container tarball to server and load it
	@echo "════════════════════════════════════════════════════════════"
	@echo "Uploading: $(DEPLOY_TARBALL) → $(DEPLOY_SERVER)"
	@echo "════════════════════════════════════════════════════════════"
	@if [ ! -f "$(DEPLOY_TARBALL)" ]; then \
		echo "✗ Error: $(DEPLOY_TARBALL) not found. Run 'make build-container' first."; \
		exit 1; \
	fi
	scp $(DEPLOY_TARBALL) $(DEPLOY_SERVER):$(DEPLOY_DIR)/
	@echo ""
	@echo "Loading image on server..."
	ssh $(DEPLOY_SERVER) "podman load -i $(DEPLOY_DIR)/$(DEPLOY_TARBALL)"
	@echo ""
	@echo "✓ Upload complete"
	@echo "  Loaded:   $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG)"

deploy-container: ## Deploy container on server (stop old, start new)
	@echo "════════════════════════════════════════════════════════════"
	@echo "Deploying: $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG)"
	@echo "════════════════════════════════════════════════════════════"
	@echo "Stopping existing container (if running)..."
	ssh $(DEPLOY_SERVER) "podman stop $(DEPLOY_CONTAINER_NAME) || true"
	ssh $(DEPLOY_SERVER) "podman rm $(DEPLOY_CONTAINER_NAME) || true"
	@echo ""
	@echo "Tagging as :production for systemd..."
	ssh $(DEPLOY_SERVER) "podman tag $(DEPLOY_IMAGE_NAME):$(DEPLOY_TAG) $(DEPLOY_IMAGE_NAME):production"
	@echo ""
	@echo "Starting new container..."
	ssh $(DEPLOY_SERVER) "podman run -d --name $(DEPLOY_CONTAINER_NAME) -p 127.0.0.1:8001:8000 $(DEPLOY_IMAGE_NAME):production"
	@echo ""
	@echo "Waiting for health check..."
	@sleep 5
	@ssh $(DEPLOY_SERVER) "podman exec $(DEPLOY_CONTAINER_NAME) curl -f http://localhost:8000/health" || \
		(echo "✗ Health check failed!" && exit 1)
	@echo ""
	@echo "✓ Deployment successful"
	@echo "  Container: $(DEPLOY_CONTAINER_NAME)"
	@echo "  Version:   $(DEPLOY_TAG)"
	@echo "  Health:    OK"

install-service: ## Install systemd user service (one-time setup)
	@echo "════════════════════════════════════════════════════════════"
	@echo "Installing systemd service: crimecity3k.service"
	@echo "════════════════════════════════════════════════════════════"
	@echo "Copying service file to server..."
	scp deployment/crimecity3k.service $(DEPLOY_SERVER):~/.config/systemd/user/
	@echo ""
	@echo "Reloading systemd daemon..."
	ssh $(DEPLOY_SERVER) "systemctl --user daemon-reload"
	@echo ""
	@echo "✓ Service installed"
	@echo "  Enable:  ssh $(DEPLOY_SERVER) 'systemctl --user enable crimecity3k'"
	@echo "  Start:   ssh $(DEPLOY_SERVER) 'systemctl --user start crimecity3k'"
	@echo "  Status:  make deploy-status"

# ═══════════════════════════════════════════════════════════════════════════════
# MONITORING AND UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

deploy-status: ## Check deployment status on server
	@echo "════════════════════════════════════════════════════════════"
	@echo "Deployment Status"
	@echo "════════════════════════════════════════════════════════════"
	@echo ""
	@echo "Container status:"
	@ssh $(DEPLOY_SERVER) "podman ps -a --filter name=$(DEPLOY_CONTAINER_NAME)" || true
	@echo ""
	@echo "Systemd service status:"
	@ssh $(DEPLOY_SERVER) "systemctl --user status crimecity3k --no-pager" || true
	@echo ""
	@echo "Recent images:"
	@ssh $(DEPLOY_SERVER) "podman images $(DEPLOY_IMAGE_NAME) --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.Created}}'" || true

deploy-logs: ## View container logs on server (follow mode)
	@echo "Viewing logs from $(DEPLOY_SERVER):$(DEPLOY_CONTAINER_NAME)"
	@echo "Press Ctrl+C to exit"
	@echo "════════════════════════════════════════════════════════════"
	ssh $(DEPLOY_SERVER) "podman logs -f $(DEPLOY_CONTAINER_NAME)"
