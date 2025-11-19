# CrimeCity3K - V1 Implementation TODO

**Project Goal:** Interactive web map visualizing Swedish police events (2022-2025) aggregated to H3 hexagonal cells with population normalization.

**Development Approach:** Test-Driven Development (TDD) with red-green-refactor cycles, SQL-driven pipeline with qck templates, Pydantic config management.

**Test Fixture:** Week of 2024-01-15 to 2024-01-22 (476 events, 51 types, 154 locations) - representative sample from middle of dataset.

**Architecture Pattern:** Follows aviation-anomaly's proven patterns for SQL execution, configuration management, and testing.

---

## Phase 0: Project Foundation & Setup ✅ COMPLETE

**Goal:** Establish project structure, dependencies, test infrastructure, and configuration system. All subsequent work builds on this foundation.

**Duration:** 2-3 hours (Actual: ~3 hours)

**Acceptance Criteria:**
- [x] Project structure follows SQL-driven pipeline pattern
- [x] All dependencies installed and locked (including qck)
- [x] config.toml created with validation
- [x] pytest runs successfully (infrastructure tests pass) - 11 tests passing
- [x] DuckDB with H3 and spatial extensions loads
- [x] Git initialized with proper .gitignore
- [x] Test fixture created and committed (476 events)
- [x] **BONUS:** GitHub Actions CI workflow added
- [x] **BONUS:** Pre-commit hooks configured to run `make check`

### Tasks

- [x] **0.1: Create pyproject.toml**
  - Use `uv` package manager for dependency management
  - Required dependencies:
    - `duckdb>=1.1.0` - Columnar SQL engine
    - `fastapi>=0.117.0` - Web API framework
    - `uvicorn>=0.37.0` - ASGI server
    - `qck>=0.1.0` - SQL template processor (Jinja2 for SQL)
    - `pydantic>=2.10.0` - Config validation
    - `tqdm>=4.67.0` - Progress bars
  - Dev dependencies:
    - `pytest>=8.0.0` - Test framework
    - `pytest-cov>=6.0.0` - Coverage reporting
    - `pytest-xdist>=3.6.0` - Parallel test execution
    - `ruff>=0.8.0` - Linting + formatting
    - `mypy>=1.13.0` - Type checking
  - Python version: `>=3.13`
  - Package name: `crimecity3k`
  - Commit: "chore: add pyproject.toml with dependencies"

- [x] **0.2: Create directory structure**
  ```
  crimecity3k/
  ├── crimecity3k/          # Python package
  │   ├── __init__.py
  │   ├── config.py         # Pydantic config models
  │   ├── data_access.py    # DuckDB connection management
  │   ├── h3_processing.py  # H3 aggregation logic
  │   ├── api.py            # FastAPI server (stub for now)
  │   ├── pmtiles.py        # PMTiles generation (stub for now)
  │   ├── logging.py        # Logging utilities
  │   └── sql/              # SQL templates
  │       ├── population_to_h3.sql
  │       ├── h3_aggregation.sql
  │       └── h3_to_geojson.sql
  ├── tests/
  │   ├── __init__.py
  │   ├── conftest.py       # Shared fixtures
  │   ├── fixtures/         # Test data
  │   ├── test_config.py
  │   ├── test_h3_processing.py
  │   └── test_api.py
  ├── static/               # Web frontend (empty for now)
  ├── data/
  │   ├── .gitkeep          # Track directory
  │   └── events.parquet    # (user provides, gitignored)
  ├── tmp/                  # Spike scripts (keep for reference)
  ├── .github/
  │   └── workflows/
  │       └── ci.yml        # GitHub Actions CI (added in Phase 0)
  ├── config.toml           # Configuration file
  ├── pyproject.toml
  ├── Makefile
  ├── README.md
  ├── TODO.md               # This file
  └── .gitignore
  ```
  - Commit: "chore: create project directory structure"

- [x] **0.3: Initialize Git and .gitignore**
  - Ignore patterns:
    - `data/*.parquet` (except test fixtures)
    - `data/*.gpkg`
    - `data/h3/`
    - `data/tiles/`
    - `.venv/`
    - `__pycache__/`
    - `*.pyc`
    - `.coverage`
    - `htmlcov/`
    - `.pytest_cache/`
    - `.mypy_cache/`
    - `.ruff_cache/`
    - `*.tmp` (temp files from atomic writes)
  - Initial commit: "chore: initialize git repository"

- [x] **0.4: Create config.toml**
  - Follow aviation-anomaly pattern for configuration management
  - Structure:
    ```toml
    # CrimeCity3K Configuration

    # Base directory for all data files
    data_dir = "data"

    [aggregation]
    # H3 resolutions to compute
    resolutions = [4, 5, 6]
    # Minimum population to display (privacy threshold)
    min_population_threshold = 100

    [duckdb]
    # DuckDB performance tuning
    memory_limit = "4GB"
    threads = 2
    temp_directory = "/tmp/duckdb"
    max_temp_directory_size = "50GB"

    [export]
    # Export configuration
    geojson_compression = true
    pmtiles_max_zoom = 10
    ```
  - Commit: "config: add config.toml with default settings"

- [x] **0.5: Create config.py with Pydantic models**
  - Pattern: Type-safe configuration loading with validation
  - Implementation:
    ```python
    import tomllib
    from pathlib import Path
    from pydantic import BaseModel, Field, field_validator

    class AggregationConfig(BaseModel):
        """Configuration for H3 aggregation."""

        resolutions: list[int] = Field(default=[4, 5, 6])
        min_population_threshold: int = Field(default=100)

        @field_validator("resolutions")
        @classmethod
        def validate_resolutions(cls, v: list[int]) -> list[int]:
            """Ensure resolutions are valid H3 values."""
            if not all(4 <= r <= 6 for r in v):
                raise ValueError("Resolutions must be between 4 and 6")
            return v

    class DuckDBConfig(BaseModel):
        """Configuration for DuckDB execution."""

        memory_limit: str = Field(default="4GB")
        threads: int = Field(default=2)
        temp_directory: str = Field(default="/tmp/duckdb")
        max_temp_directory_size: str = Field(default="50GB")

    class ExportConfig(BaseModel):
        """Configuration for data export."""

        geojson_compression: bool = Field(default=True)
        pmtiles_max_zoom: int = Field(default=10)

    class Config(BaseModel):
        """Main configuration."""

        data_dir: Path = Field(default=Path("data"))
        aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
        duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)
        export: ExportConfig = Field(default_factory=ExportConfig)

        @classmethod
        def from_file(cls, path: Path | str) -> "Config":
            """Load configuration from TOML file."""
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"Config not found: {path}")

            with open(path, "rb") as f:
                data = tomllib.load(f)

            return cls(**data)
    ```
  - Commit: "feat: add Pydantic config loading"

- [x] **0.6: Create data_access.py for DuckDB connection management**
  - Pattern: Centralized DuckDB connection with config application
  - Implementation:
    ```python
    import duckdb
    from crimecity3k.config import Config

    def create_configured_connection(
        config: Config,
        extensions: list[str] | None = None
    ) -> duckdb.DuckDBPyConnection:
        """Create DuckDB connection with standard configuration.

        Applies memory limits, threading, and loads extensions.

        Args:
            config: Configuration object
            extensions: Optional list of extensions to load (e.g., ["h3", "spatial"])

        Returns:
            Configured DuckDB connection
        """
        conn = duckdb.connect()

        # Apply DuckDB settings from config
        conn.execute(f"SET memory_limit = '{config.duckdb.memory_limit}'")
        conn.execute(f"SET threads = {config.duckdb.threads}")
        conn.execute(f"SET temp_directory = '{config.duckdb.temp_directory}'")
        conn.execute(f"SET max_temp_directory_size = '{config.duckdb.max_temp_directory_size}'")

        # Enable progress bar for long operations
        conn.execute("SET enable_progress_bar = true")
        conn.execute("SET enable_progress_bar_print = true")

        # Load extensions (improved in implementation to handle core vs community)
        if extensions:
            for ext in extensions:
                conn.execute(f"INSTALL {ext} FROM community")
                conn.execute(f"LOAD {ext}")

        return conn
    ```
  - **Note:** Implementation improved to distinguish core extensions (spatial) from community (h3)
  - Commit: "feat: add DuckDB connection management"

- [x] **0.7: Create test fixture**
  - Extract events from 2024-01-15 to 2024-01-22 (476 events)
  - Save as `tests/fixtures/events_2024_01_15-22.parquet`
  - This fixture is checked into git (small, ~20-30 KB)
  - Command to generate:
    ```bash
    uv run python -c "
    import duckdb
    conn = duckdb.connect()
    conn.execute('''
        COPY (
          SELECT * FROM ''data/events.parquet''
          WHERE datetime >= ''2024-01-15''
            AND datetime < ''2024-01-22''
        ) TO ''tests/fixtures/events_2024_01_15-22.parquet''
        (FORMAT PARQUET, COMPRESSION ZSTD)
    ''')
    "
    ```
  - Commit: "test: add test fixture for 2024-01-15 to 2024-01-22"

- [x] **0.8: Create tests/conftest.py with shared fixtures**
  - Pattern: Reusable fixtures for DuckDB and sample data
  - Implementation:
    ```python
    import pytest
    import duckdb
    from pathlib import Path
    from crimecity3k.config import Config
    from crimecity3k.data_access import create_configured_connection

    @pytest.fixture
    def test_config():
        """Create test configuration with safe defaults."""
        config = Config()
        # Override for tests
        config.aggregation.resolutions = [5]
        config.duckdb.memory_limit = "1GB"
        config.duckdb.threads = 1
        config.duckdb.temp_directory = "/tmp/test_duckdb"
        return config

    @pytest.fixture
    def duckdb_conn(test_config):
        """In-memory DuckDB with h3 and spatial extensions."""
        conn = create_configured_connection(
            test_config,
            extensions=["h3", "spatial"]
        )
        yield conn
        conn.close()

    @pytest.fixture
    def sample_events(duckdb_conn):
        """Load test fixture events into DuckDB."""
        fixture_path = Path(__file__).parent / "fixtures" / "events_2024_01_15-22.parquet"
        duckdb_conn.execute(f"""
            CREATE TABLE events AS
            SELECT * FROM '{fixture_path}'
        """)
        return duckdb_conn
    ```
  - Commit: "test: add pytest fixtures"

- [x] **0.9: Create infrastructure tests**
  - File: `tests/test_config.py`
    ```python
    def test_config_loads_from_file():
        """Test config.toml loads successfully."""
        from crimecity3k.config import Config
        config = Config.from_file("config.toml")
        assert config.data_dir == Path("data")
        assert 4 in config.aggregation.resolutions

    def test_config_validates_resolutions():
        """Test resolution validation."""
        from crimecity3k.config import AggregationConfig
        with pytest.raises(ValueError):
            AggregationConfig(resolutions=[99])  # Invalid
    ```
  - File: `tests/test_data_access.py`
    ```python
    def test_duckdb_h3_extension(duckdb_conn):
        """Test H3 extension loads."""
        result = duckdb_conn.execute(
            "SELECT h3_latlng_to_cell(59.3293, 18.0686, 5)"
        ).fetchone()[0]
        assert result is not None
        assert isinstance(result, int)

    def test_sample_events_fixture(sample_events):
        """Test sample events loads correctly."""
        count = sample_events.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0]
        assert count == 476
    ```
  - Run: `uv run pytest tests/ -v`
  - **Actual:** 11 passing tests (expanded coverage)
  - Commit: "test: add infrastructure tests"

- [x] **0.10: Create stub Makefile**
  - Pattern: Phony targets + pipeline pattern rules
  - Minimal Makefile for Phase 0:
    ```makefile
    # Configuration
    CONFIG := config.toml

    # Directories
    DATA_DIR := data
    H3_DIR := $(DATA_DIR)/h3
    TILES_DIR := $(DATA_DIR)/tiles

    # Code dependencies (SQL files trigger rebuilds)
    SQL_DIR := crimecity3k/sql

    .PHONY: install check test clean

    install:
    	uv sync

    check:
    	uv run ruff check crimecity3k tests  # (updated to exclude tmp/)
    	uv run ruff format --check crimecity3k tests
    	uv run mypy crimecity3k tests

    test:
    	uv run pytest tests/ -v -n auto --cov=crimecity3k --cov-report=html --cov-report=term  # (added HTML report)

    clean:
    	rm -rf $(H3_DIR) $(TILES_DIR)
    	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
    	find . -type f -name "*.tmp" -delete
    ```
  - Commit: "build: add Makefile with basic targets"

**Phase 0 Complete When:**
- [x] `make install` succeeds
- [x] `make test` shows 4+ passing tests (11 tests passing with 91% coverage)
- [x] `make check` passes linting and type checking
- [x] config.toml loads successfully
- [x] DuckDB connection works with H3 and spatial extensions
- [x] Git has clean history (squashed by user)
- [x] **BONUS:** GitHub Actions CI workflow validates all PRs and pushes

**Improvements Made:**
- Distinguished core DuckDB extensions (spatial) from community extensions (h3)
- Added HTML coverage reports for better debugging
- Excluded tmp/ directory from linting (spike scripts)
- Added comprehensive type annotations with Generator for fixtures
- GitHub Actions workflow with uv caching for faster CI runs
- Pre-commit hooks configured to run `make check` before every commit (using pre-commit framework)

---

## Phase 1: Population Data Pipeline ✅ COMPLETE

**Goal:** Download SCB population data, convert to H3 cells using SQL templates, and make available for testing. Establishes the SQL-driven pattern.

**Duration:** 3-4 hours (Actual: ~4 hours)

**Acceptance Criteria:**
- [x] Population data downloaded and cached
- [x] SQL file `population_to_h3.sql` created and tested
- [x] Python function executes SQL with qck
- [x] Conversion to H3 cells (r4, r5, r6) working
- [x] Output schema validated
- [x] Makefile tracks SQL as dependency
- [x] Atomic write pattern implemented

### Tasks

- [x] **1.1: Create SQL file: crimecity3k/sql/population_to_h3.sql**
  - Pattern: Jinja2 template with documented parameters
  - Implementation:
    ```sql
    -- Population grid to H3 aggregation
    --
    -- Parameters:
    --   {{input_file}}: Path to population GeoPackage (1km grid)
    --   {{output_file}}: Path to output Parquet file
    --   {{resolution}}: H3 resolution (4, 5, or 6)
    --
    -- Converts SCB 1km grid cells to H3 hexagons by:
    -- 1. Computing grid cell centroids
    -- 2. Converting centroids to H3 cells
    -- 3. Aggregating population by H3 cell

    COPY (
        WITH grid_centroids AS (
            SELECT
                ST_Y(ST_Centroid(geom)) as latitude,
                ST_X(ST_Centroid(geom)) as longitude,
                Totalt as population,
                Kvinnor as female,
                Man as male
            FROM '{{ input_file }}'
            WHERE Totalt > 0  -- Skip unpopulated cells
        ),

        h3_mapped AS (
            SELECT
                h3_latlng_to_cell(latitude, longitude, {{ resolution }}) as h3_cell,
                population,
                female,
                male
            FROM grid_centroids
        )

        SELECT
            h3_cell,
            SUM(population) as population,
            SUM(female) as female,
            SUM(male) as male
        FROM h3_mapped
        GROUP BY h3_cell
        HAVING SUM(population) > 0

    ) TO '{{ output_file }}' (FORMAT PARQUET, COMPRESSION ZSTD)
    ```
  - Commit: "feat: add population_to_h3.sql template"
  - **IMPROVEMENT:** Added ST_Transform for SWEREF99 TM to WGS84 coordinate conversion
  - **IMPROVEMENT:** Used h3_latlng_to_cell_string() for VARCHAR output instead of UBIGINT
  - **IMPROVEMENT:** Fixed column names to match actual SCB schema (beftotalt, kvinna, man, sp_geometry)

- [x] **1.2: Create h3_processing.py with population conversion function**
  - Pattern: Python function that executes SQL via qck
  - Implementation (in `crimecity3k/h3_processing.py`):
    ```python
    """H3 spatial processing functions."""

    import logging
    from pathlib import Path
    from qck import qck

    from crimecity3k.config import Config
    from crimecity3k.data_access import create_configured_connection

    logger = logging.getLogger(__name__)

    def convert_population_to_h3(
        input_file: Path,
        output_file: Path,
        resolution: int,
        config: Config | None = None,
    ) -> None:
        """Convert SCB population grid to H3 cells.

        Executes population_to_h3.sql template with parameters.
        Uses atomic write pattern (write to .tmp, rename on success).

        Args:
            input_file: Path to population GeoPackage (1km grid)
            output_file: Path to output Parquet file
            resolution: H3 resolution (4, 5, or 6)
            config: Configuration object (loads from file if None)

        Raises:
            FileNotFoundError: If input file doesn't exist
            RuntimeError: If SQL execution fails
        """
        if config is None:
            config = Config.from_file("config.toml")

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Atomic write pattern: write to temp file first
        temp_file = output_file.with_suffix(".tmp")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Locate SQL template
        sql_path = Path(__file__).parent / "sql" / "population_to_h3.sql"

        # Build parameters for template
        params = {
            "input_file": str(input_file),
            "output_file": str(temp_file),
            "resolution": resolution,
        }

        logger.info(f"Converting population to H3 resolution {resolution}")
        logger.info(f"Input: {input_file}")
        logger.info(f"Output: {output_file}")

        # Execute SQL with configured connection
        conn = create_configured_connection(config, extensions=["h3", "spatial"])
        try:
            qck(str(sql_path), params=params, connection=conn)

            # Atomic rename on success
            temp_file.rename(output_file)

            # Log result
            count = conn.execute(f"SELECT COUNT(*) FROM '{output_file}'").fetchone()[0]
            logger.info(f"Population conversion complete: {count} H3 cells")

        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            logger.error(f"Population conversion failed: {e}")
            raise RuntimeError(f"Failed to convert population to H3: {e}") from e
        finally:
            conn.close()
    ```
  - Commit: "feat: add population H3 conversion function"
  - **IMPROVEMENT:** Added type assertions for mypy satisfaction

- [x] **1.3: Write test for population conversion (TDD - RED)**
  - File: `tests/test_h3_processing.py`
  - Test using real SCB data (download in test if needed):
    ```python
    import pytest
    from pathlib import Path
    from crimecity3k.h3_processing import convert_population_to_h3

    @pytest.mark.integration
    def test_population_to_h3_conversion(test_config, tmp_path):
        """Test population conversion to H3 cells."""
        # This test downloads real SCB data (cached after first run)
        input_file = Path("data/population_1km_2024.gpkg")

        if not input_file.exists():
            pytest.skip("Population data not downloaded yet")

        output_file = tmp_path / "population_r5.parquet"

        # Run conversion
        convert_population_to_h3(
            input_file=input_file,
            output_file=output_file,
            resolution=5,
            config=test_config
        )

        # Verify output exists
        assert output_file.exists()

        # Verify output schema and data quality
        import duckdb
        conn = duckdb.connect()
        conn.execute("INSTALL h3 FROM community; LOAD h3")

        result = conn.execute(f"""
            SELECT
                COUNT(*) as cell_count,
                SUM(population) as total_pop,
                MIN(population) as min_pop,
                MAX(population) as max_pop
            FROM '{output_file}'
        """).fetchone()

        cell_count, total_pop, min_pop, max_pop = result

        # Verify reasonable values
        assert cell_count > 2000, "Should have 2000+ H3 cells for Sweden"
        assert total_pop > 10_000_000, "Sweden has ~10.5M people"
        assert min_pop > 0, "No zero-population cells (filtered in SQL)"
        assert max_pop < 1_000_000, "No cell should have 1M+ people"

        conn.close()
    ```
  - Expected to FAIL (or skip) - population data not downloaded yet
  - Commit: "test: add population conversion test (RED)"
  - **IMPROVEMENT:** Created three tests instead of one (schema validation, error handling, atomic write)

- [x] **1.4: Add population download to Makefile**
  - Add download rule:
    ```makefile
    # Download SCB population data (cached, one-time)
    $(DATA_DIR)/population_1km_2024.gpkg:
    	@echo "═══ Downloading SCB population data ═══"
    	@mkdir -p $(DATA_DIR)
    	curl -L "https://geodata.scb.se/geoserver/stat/wfs?\
    service=WFS&REQUEST=GetFeature&version=1.1.0&\
    TYPENAMES=stat:befolkning_1km_2024&outputFormat=geopackage" \
    	-o $@
    	@echo "✓ Population data downloaded: $@ ($$(du -h $@ | cut -f1))"
    ```
  - Test: `make data/population_1km_2024.gpkg`
  - Verify: `ls -lh data/population_1km_2024.gpkg` (should be ~34 MB)
  - Commit: "build: add population data download rule"
  - **VERIFIED:** Download successful, 34MB as expected

- [x] **1.5: Add population-to-H3 conversion rules to Makefile**
  - Pattern: Pattern rule with SQL file dependency
  - Add variables for SQL tracking:
    ```makefile
    # SQL file dependencies (tracked for automatic rebuilds)
    POPULATION_SQL := $(SQL_DIR)/population_to_h3.sql
    ```
  - Add pattern rule:
    ```makefile
    # Population to H3 conversion (pattern rule for any resolution)
    $(H3_DIR)/population_r%.parquet: $(DATA_DIR)/population_1km_2024.gpkg $(POPULATION_SQL) $(CONFIG)
    	@echo "═══ Converting population to H3 resolution $* ═══"
    	@mkdir -p $(H3_DIR)
    	uv run python -c " \
    from pathlib import Path; \
    from crimecity3k.h3_processing import convert_population_to_h3; \
    from crimecity3k.config import Config; \
    config = Config.from_file('$(CONFIG)'); \
    convert_population_to_h3( \
        Path('$(DATA_DIR)/population_1km_2024.gpkg'), \
        Path('$@'), \
        $*, \
        config \
    ); \
    "
    	@echo "✓ Complete: $@"
    ```
  - Note: Changing SQL file or config triggers rebuild
  - Test: `make data/h3/population_r5.parquet`
  - Should build successfully
  - Commit: "build: add population H3 conversion pattern rule"
  - **IMPROVEMENT:** Used pattern rule `$(H3_DIR)/population_r%.parquet` instead of three separate rules
  - **VERIFIED:** Dependency tracking works (tested by touching SQL file and verifying rebuild)

- [x] **1.6: Test should now PASS (TDD - GREEN)**
  - Run: `make test`
  - Previous test should now pass
  - Verify: `uv run pytest tests/test_h3_processing.py::test_population_to_h3_conversion -v`
  - Commit: "test: population conversion test now passing (GREEN)"
  - **NOTE:** Required two iterations - first fix column names, then fix coordinate transformation

- [x] **1.7: Add data quality tests (TDD - REFACTOR)**
  - Expand `tests/test_h3_processing.py`:
    ```python
    def test_population_sweden_coverage(test_config):
        """Verify population data covers all of Sweden."""
        import duckdb
        conn = duckdb.connect()

        result = conn.execute("""
            SELECT
                MIN(h3_cell_to_lat(h3_cell)) as min_lat,
                MAX(h3_cell_to_lat(h3_cell)) as max_lat,
                MIN(h3_cell_to_lng(h3_cell)) as min_lon,
                MAX(h3_cell_to_lng(h3_cell)) as max_lon
            FROM 'data/h3/population_r5.parquet'
        """).fetchone()

        # Sweden bounds (approximately)
        assert 55 < result[0] < 56, "Southernmost cells"
        assert 67 < result[1] < 70, "Northernmost cells"
        assert 10 < result[2] < 12, "Westernmost cells"
        assert 23 < result[3] < 25, "Easternmost cells"

    def test_no_population_lost_in_conversion(test_config):
        """Verify total population matches input."""
        import duckdb
        conn = duckdb.connect()

        # Total from input GeoPackage
        input_total = conn.execute("""
            SELECT SUM(Totalt) FROM 'data/population_1km_2024.gpkg'
            WHERE Totalt > 0
        """).fetchone()[0]

        # Total from H3 output
        output_total = conn.execute("""
            SELECT SUM(population) FROM 'data/h3/population_r5.parquet'
        """).fetchone()[0]

        # Should match exactly (no population lost in aggregation)
        assert input_total == output_total
    ```
  - Run: `make test`
  - Commit: "test: add population data quality checks"
  - **VERIFIED:** Both tests passing (population conservation and Sweden geographic coverage)

- [x] **1.8: Add convenience target for all population conversions**
  - Add to Makefile:
    ```makefile
    # Convenience targets
    .PHONY: pipeline-population

    # Build population H3 files for all configured resolutions
    pipeline-population: \
    	$(H3_DIR)/population_r4.parquet \
    	$(H3_DIR)/population_r5.parquet \
    	$(H3_DIR)/population_r6.parquet
    ```
  - Test: `make pipeline-population`
  - Should build all 3 resolutions
  - Commit: "build: add pipeline-population target"
  - **VERIFIED:** Pipeline builds all three resolutions with nice summary output

**Phase 1 Complete When:**
- [x] `make pipeline-population` generates all 3 files
- [x] All tests pass (`make test`) - 16 tests passing
- [x] SQL file changes trigger rebuilds - verified by touching SQL file
- [x] Config changes trigger rebuilds - config in dependency list
- [x] Population files are ~10-50 KB each - r4=8KB, r5=24KB, r6=96KB
- [x] Can query: `SELECT COUNT(*) FROM 'data/h3/population_r5.parquet'` - verified
- [x] Atomic writes work (no .tmp files left on success) - tested explicitly

**Improvements Made:**
- Fixed SCB schema assumptions (beftotalt, kvinna, man, sp_geometry columns)
- Added ST_Transform for SWEREF99 TM → WGS84 coordinate conversion
- Used h3_latlng_to_cell_string() for VARCHAR H3 cells instead of UBIGINT
- Added `always_xy=true` parameter for correct longitude/latitude ordering
- Created three integration tests instead of one
- Added data quality tests (population conservation, geographic coverage)
- Pattern rule instead of three separate rules for better maintainability

---

## Phase 2: H3 Event Aggregation with Population Join

**Goal:** Aggregate crime events to H3 cells and join with population data using SQL template. This is the core analytical transformation.

**Duration:** 4-5 hours

**Acceptance Criteria:**
- [ ] SQL file `h3_aggregation.sql` created and tested
- [ ] Events aggregated to H3 cells with type lists
- [ ] Population joined successfully
- [ ] Normalized rates calculated correctly
- [ ] Output schema validated
- [ ] Integration test with full pipeline

### Tasks

- [ ] **2.1: Create SQL file: crimecity3k/sql/h3_aggregation.sql**
  - Pattern: Multi-CTE SQL with population join
  - Implementation:
    ```sql
    -- Event aggregation to H3 cells with population join
    --
    -- Parameters:
    --   {{events_file}}: Path to events Parquet
    --   {{population_file}}: Path to population H3 Parquet
    --   {{output_file}}: Path to output Parquet
    --   {{resolution}}: H3 resolution (4, 5, or 6)
    --   {{min_population}}: Minimum population threshold (default: 100)
    --
    -- Aggregates events to H3 cells and joins with population data
    -- to compute both absolute counts and normalized rates.

    COPY (
        WITH events_h3 AS (
            -- Map events to H3 cells
            SELECT
                h3_latlng_to_cell(latitude, longitude, {{ resolution }}) as h3_cell,
                event_id,
                type,
                datetime
            FROM '{{ events_file }}'
        ),

        events_aggregated AS (
            -- Aggregate events by cell
            SELECT
                h3_cell,
                COUNT(*) as event_count,
                COUNT(DISTINCT type) as event_types_count,
                LIST(type ORDER BY type) as types_list
            FROM events_h3
            GROUP BY h3_cell
        ),

        population AS (
            -- Load population data for this resolution
            SELECT
                h3_cell,
                population
            FROM '{{ population_file }}'
        ),

        merged AS (
            -- Join events with population
            SELECT
                e.h3_cell,
                e.event_count,
                e.event_types_count,
                e.types_list,
                COALESCE(p.population, 0.0) as population,
                -- Calculate normalized rate (per 10,000 residents)
                CASE
                    WHEN COALESCE(p.population, 0) >= {{ min_population }}
                    THEN (e.event_count::DOUBLE / p.population) * 10000.0
                    ELSE 0.0
                END as rate_per_10000,
                -- Add cell centroid coordinates
                h3_cell_to_lat(e.h3_cell) as latitude,
                h3_cell_to_lng(e.h3_cell) as longitude
            FROM events_aggregated e
            LEFT JOIN population p ON e.h3_cell = p.h3_cell
        )

        SELECT
            h3_cell,
            event_count,
            event_types_count,
            types_list,
            population,
            rate_per_10000,
            latitude,
            longitude
        FROM merged
        ORDER BY event_count DESC

    ) TO '{{ output_file }}' (FORMAT PARQUET, COMPRESSION ZSTD)
    ```
  - Commit: "feat: add h3_aggregation.sql template"

- [ ] **2.2: Add aggregation function to h3_processing.py**
  - Implementation:
    ```python
    def aggregate_events_to_h3(
        events_file: Path,
        population_file: Path,
        output_file: Path,
        resolution: int,
        config: Config | None = None,
    ) -> None:
        """Aggregate events to H3 cells and join with population.

        Executes h3_aggregation.sql template with parameters.
        Uses atomic write pattern.

        Args:
            events_file: Path to events Parquet
            population_file: Path to population H3 Parquet
            output_file: Path to output Parquet
            resolution: H3 resolution (4, 5, or 6)
            config: Configuration object

        Raises:
            FileNotFoundError: If input files don't exist
            RuntimeError: If SQL execution fails
        """
        if config is None:
            config = Config.from_file("config.toml")

        if not events_file.exists():
            raise FileNotFoundError(f"Events file not found: {events_file}")
        if not population_file.exists():
            raise FileNotFoundError(f"Population file not found: {population_file}")

        # Atomic write pattern
        temp_file = output_file.with_suffix(".tmp")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Locate SQL template
        sql_path = Path(__file__).parent / "sql" / "h3_aggregation.sql"

        # Build parameters
        params = {
            "events_file": str(events_file),
            "population_file": str(population_file),
            "output_file": str(temp_file),
            "resolution": resolution,
            "min_population": config.aggregation.min_population_threshold,
        }

        logger.info(f"Aggregating events to H3 resolution {resolution}")
        logger.info(f"Events: {events_file}")
        logger.info(f"Population: {population_file}")
        logger.info(f"Output: {output_file}")

        # Execute SQL
        conn = create_configured_connection(config, extensions=["h3"])
        try:
            qck(str(sql_path), params=params, connection=conn)

            # Atomic rename
            temp_file.rename(output_file)

            # Log results
            stats = conn.execute(f"""
                SELECT
                    COUNT(*) as cells,
                    SUM(event_count) as total_events,
                    AVG(event_count) as avg_per_cell,
                    SUM(CASE WHEN population > 0 THEN 1 ELSE 0 END) as cells_with_pop
                FROM '{output_file}'
            """).fetchone()

            logger.info(f"Aggregation complete: {stats[0]} cells, {stats[1]} events, {stats[3]} with population")

        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            logger.error(f"Aggregation failed: {e}")
            raise RuntimeError(f"Failed to aggregate events: {e}") from e
        finally:
            conn.close()
    ```
  - Commit: "feat: add event H3 aggregation function"

- [ ] **2.3: Write aggregation tests (TDD - RED then GREEN)**
  - File: `tests/test_h3_aggregation.py`
  - Test with sample data:
    ```python
    def test_h3_aggregation_basic(duckdb_conn, tmp_path, test_config):
        """Test basic H3 aggregation logic."""
        # Create sample events
        duckdb_conn.execute("""
            CREATE TABLE events AS
            SELECT * FROM (VALUES
                ('1', 59.3293, 18.0686, 'Stockholm', 'Stöld', '2024-01-15 10:00:00 +01:00'),
                ('2', 59.3293, 18.0686, 'Stockholm', 'Stöld', '2024-01-15 11:00:00 +01:00'),
                ('3', 55.6050, 13.0038, 'Malmö', 'Brand', '2024-01-15 12:00:00 +01:00')
            ) AS t(event_id, latitude, longitude, location_name, type, datetime)
        """)

        # Save to temp file
        events_file = tmp_path / "events.parquet"
        duckdb_conn.execute(f"COPY events TO '{events_file}' (FORMAT PARQUET)")

        # Create sample population (using real H3 cells for these locations)
        duckdb_conn.execute("""
            CREATE TABLE population AS
            SELECT
                h3_latlng_to_cell(59.3293, 18.0686, 5) as h3_cell,
                867546.0 as population
            UNION ALL
            SELECT
                h3_latlng_to_cell(55.6050, 13.0038, 5) as h3_cell,
                375742.0 as population
        """)

        population_file = tmp_path / "population_r5.parquet"
        duckdb_conn.execute(f"COPY population TO '{population_file}' (FORMAT PARQUET)")

        # Run aggregation
        from crimecity3k.h3_processing import aggregate_events_to_h3
        output_file = tmp_path / "h3_events_r5.parquet"

        aggregate_events_to_h3(
            events_file=events_file,
            population_file=population_file,
            output_file=output_file,
            resolution=5,
            config=test_config
        )

        # Verify output
        result = duckdb_conn.execute(f"""
            SELECT * FROM '{output_file}' ORDER BY event_count DESC
        """).fetchall()

        # Should have 2 cells
        assert len(result) == 2

        # Stockholm cell: 2 events, 1 type
        sthlm = result[0]
        assert sthlm[1] == 2  # event_count
        assert sthlm[2] == 1  # event_types_count
        assert sthlm[3] == ['Stöld', 'Stöld']  # types_list
        assert sthlm[4] == 867546.0  # population

        # Verify rate calculation
        expected_rate = (2 / 867546.0) * 10000
        assert abs(sthlm[5] - expected_rate) < 0.01

    def test_h3_aggregation_full_fixture(sample_events, tmp_path, test_config):
        """Test aggregation with full fixture (476 events)."""
        # This test uses the sample_events fixture
        # Save to file for SQL execution
        events_file = tmp_path / "events.parquet"
        sample_events.execute(f"COPY events TO '{events_file}' (FORMAT PARQUET)")

        # Use real population file
        population_file = Path("data/h3/population_r5.parquet")
        if not population_file.exists():
            pytest.skip("Population file not built yet")

        output_file = tmp_path / "h3_events_r5.parquet"

        from crimecity3k.h3_processing import aggregate_events_to_h3
        aggregate_events_to_h3(
            events_file=events_file,
            population_file=population_file,
            output_file=output_file,
            resolution=5,
            config=test_config
        )

        # Verify all events are aggregated
        import duckdb
        conn = duckdb.connect()
        stats = conn.execute(f"""
            SELECT
                COUNT(*) as cells,
                SUM(event_count) as total_events,
                SUM(CASE WHEN population > 0 THEN 1 ELSE 0 END) as cells_with_pop
            FROM '{output_file}'
        """).fetchone()

        assert stats[1] == 476, "All fixture events should be aggregated"
        assert stats[0] > 100, "Should have 100+ H3 cells"
        assert stats[2] / stats[0] > 0.95, "95%+ cells should have population"
    ```
  - Run: `make test`
  - Commit: "test: add H3 aggregation tests"

- [ ] **2.4: Add aggregation rules to Makefile**
  - Add SQL variable:
    ```makefile
    H3_AGGREGATION_SQL := $(SQL_DIR)/h3_aggregation.sql
    ```
  - Add pattern rule:
    ```makefile
    # Event aggregation to H3 (depends on events, population, SQL, config)
    $(H3_DIR)/events_r%.parquet: $(DATA_DIR)/events.parquet $(H3_DIR)/population_r%.parquet $(H3_AGGREGATION_SQL) $(CONFIG)
    	@echo "═══ Aggregating events to H3 resolution $* ═══"
    	@mkdir -p $(H3_DIR)
    	uv run python -c " \
    from pathlib import Path; \
    from crimecity3k.h3_processing import aggregate_events_to_h3; \
    from crimecity3k.config import Config; \
    config = Config.from_file('$(CONFIG)'); \
    aggregate_events_to_h3( \
        Path('$(DATA_DIR)/events.parquet'), \
        Path('$(H3_DIR)/population_r$*.parquet'), \
        Path('$@'), \
        $*, \
        config \
    ); \
    "
    	@echo "✓ Complete: $@"
    ```
  - Test: `make data/h3/events_r5.parquet`
  - Verify: File exists and has reasonable size
  - Commit: "build: add event aggregation pattern rule"

- [ ] **2.5: Add pipeline-h3 convenience target**
  - Add to Makefile:
    ```makefile
    .PHONY: pipeline-h3 pipeline-all

    # Build all H3 event aggregations
    pipeline-h3: \
    	$(H3_DIR)/events_r4.parquet \
    	$(H3_DIR)/events_r5.parquet \
    	$(H3_DIR)/events_r6.parquet

    # Full pipeline (population + events, all resolutions)
    pipeline-all: pipeline-h3
    ```
  - Test: `make pipeline-all`
  - Should build all 6 files (3 population + 3 events)
  - Commit: "build: add pipeline convenience targets"

- [ ] **2.6: Add data quality integration test**
  - Test complete pipeline:
    ```python
    @pytest.mark.integration
    def test_pipeline_no_events_lost():
        """Integration test: verify no events lost in pipeline."""
        import duckdb
        conn = duckdb.connect()

        # Count input events
        input_count = conn.execute("""
            SELECT COUNT(*) FROM 'data/events.parquet'
        """).fetchone()[0]

        # Count output events (sum across all resolutions)
        output_count_r5 = conn.execute("""
            SELECT SUM(event_count) FROM 'data/h3/events_r5.parquet'
        """).fetchone()[0]

        # Should match exactly
        assert input_count == output_count_r5, "No events should be lost"

    @pytest.mark.integration
    def test_normalized_rates_make_sense():
        """Verify normalized rates are reasonable."""
        import duckdb
        conn = duckdb.connect()

        # Get some high-rate cells
        high_rate = conn.execute("""
            SELECT h3_cell, event_count, population, rate_per_10000
            FROM 'data/h3/events_r5.parquet'
            WHERE population >= 100
            ORDER BY rate_per_10000 DESC
            LIMIT 10
        """).fetchall()

        for row in high_rate:
            cell, count, pop, rate = row
            # Manual calculation should match
            expected_rate = (count / pop) * 10000
            assert abs(rate - expected_rate) < 0.01, f"Rate calculation mismatch for cell {cell}"
    ```
  - Run: `make test`
  - Commit: "test: add pipeline integration tests"

**Phase 2 Complete When:**
- `make pipeline-all` generates all aggregations
- All tests pass
- SQL file changes trigger rebuilds
- Output files are reasonable size (20-100 KB)
- Can query normalized rates: `SELECT * FROM 'data/h3/events_r5.parquet' ORDER BY rate_per_10000 DESC LIMIT 10`
- Manual spot-check shows expected cities (Stockholm, Malmö, Göteborg)

---

## Phase 3: GeoJSON Export and PMTiles Generation

**Goal:** Export H3 aggregations to GeoJSON format and generate PMTiles for web consumption using SQL template and Tippecanoe integration.

**Duration:** 3-4 hours

**Acceptance Criteria:**
- [ ] SQL file `h3_to_geojson.sql` created
- [ ] GeoJSON export produces valid newline-delimited format
- [ ] PMTiles generated with Tippecanoe
- [ ] Tiles inspectable with PMTiles CLI
- [ ] File sizes reasonable (<10 MB per tileset)
- [ ] Tests verify GeoJSON structure

### Tasks

- [ ] **3.1: Install Tippecanoe (prerequisite)**
  - Required for PMTiles generation
  - Installation (Ubuntu/Debian):
    ```bash
    sudo apt-get update
    sudo apt-get install -y build-essential libsqlite3-dev zlib1g-dev
    git clone https://github.com/felt/tippecanoe.git /tmp/tippecanoe
    cd /tmp/tippecanoe
    make -j
    sudo make install
    ```
  - Verify: `tippecanoe --version`
  - Document in README.md under "System Requirements"

- [ ] **3.2: Create SQL file: crimecity3k/sql/h3_to_geojson.sql**
  - Pattern: GeoJSON generation from H3 cells
  - Implementation:
    ```sql
    -- Export H3 cells to newline-delimited GeoJSON
    --
    -- Parameters:
    --   {{input_file}}: Path to H3 events Parquet
    --   {{output_file}}: Path to output newline-delimited GeoJSON (uncompressed)
    --
    -- Generates one GeoJSON Feature per line for efficient streaming.
    -- Each feature includes H3 cell boundary as polygon geometry.

    COPY (
        SELECT json_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(
                ST_GeomFromText(h3_cell_to_boundary_wkt(h3_cell))
            )::JSON,
            'properties', json_object(
                'h3_cell', h3_cell::VARCHAR,
                'event_count', event_count,
                'event_types_count', event_types_count,
                'types_list', types_list,
                'population', population,
                'rate_per_10000', ROUND(rate_per_10000, 2)
            )
        ) as feature
        FROM '{{ input_file }}'
        ORDER BY event_count DESC
    ) TO '{{ output_file }}' (FORMAT JSON, ARRAY false)
    ```
  - Note: `ARRAY false` produces newline-delimited JSON (one object per line)
  - Commit: "feat: add h3_to_geojson.sql template"

- [ ] **3.3: Add GeoJSON export function to h3_processing.py**
  - Implementation:
    ```python
    def export_h3_to_geojson(
        input_file: Path,
        output_file: Path,
        compress: bool = True,
        config: Config | None = None,
    ) -> None:
        """Export H3 aggregation to newline-delimited GeoJSON.

        Executes h3_to_geojson.sql template.
        Optionally compresses with gzip.

        Args:
            input_file: Path to H3 events Parquet
            output_file: Path to output GeoJSON file (will add .gz if compress=True)
            compress: Whether to gzip compress output (default: True)
            config: Configuration object
        """
        if config is None:
            config = Config.from_file("config.toml")

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Determine final output path (may add .gz suffix)
        if compress and not str(output_file).endswith('.gz'):
            final_output = output_file.with_suffix(output_file.suffix + '.gz')
        else:
            final_output = output_file

        # Atomic write pattern
        temp_file = final_output.with_suffix(".tmp")
        final_output.parent.mkdir(parents=True, exist_ok=True)

        # For compressed output, write uncompressed first then gzip
        if compress:
            uncompressed_temp = temp_file.with_suffix(".json")
        else:
            uncompressed_temp = temp_file

        # Locate SQL template
        sql_path = Path(__file__).parent / "sql" / "h3_to_geojson.sql"

        # Build parameters
        params = {
            "input_file": str(input_file),
            "output_file": str(uncompressed_temp),
        }

        logger.info(f"Exporting to GeoJSON: {input_file} → {final_output}")

        # Execute SQL
        conn = create_configured_connection(config, extensions=["h3", "spatial"])
        try:
            qck(str(sql_path), params=params, connection=conn)

            # Compress if requested
            if compress:
                import gzip
                import shutil
                with open(uncompressed_temp, 'rb') as f_in:
                    with gzip.open(temp_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                uncompressed_temp.unlink()

            # Atomic rename
            temp_file.rename(final_output)

            # Log size
            size_mb = final_output.stat().st_size / (1024 * 1024)
            logger.info(f"GeoJSON export complete: {final_output.name} ({size_mb:.1f} MB)")

        except Exception as e:
            # Clean up temp files
            if uncompressed_temp.exists():
                uncompressed_temp.unlink()
            if temp_file.exists():
                temp_file.unlink()
            logger.error(f"GeoJSON export failed: {e}")
            raise RuntimeError(f"Failed to export GeoJSON: {e}") from e
        finally:
            conn.close()
    ```
  - Commit: "feat: add GeoJSON export function"

- [ ] **3.4: Add PMTiles generation to pmtiles.py**
  - Pattern: Tippecanoe wrapper with zoom range mapping
  - Implementation (in `crimecity3k/pmtiles.py`):
    ```python
    """PMTiles generation using Tippecanoe."""

    import subprocess
    import logging
    from pathlib import Path

    logger = logging.getLogger(__name__)

    def get_zoom_range(resolution: int) -> tuple[int, int]:
        """Map H3 resolution to appropriate zoom levels.

        Args:
            resolution: H3 resolution (4, 5, or 6)

        Returns:
            Tuple of (min_zoom, max_zoom)
        """
        zoom_ranges = {
            4: (4, 8),   # H3 r4 (~19km) → z4-8
            5: (5, 9),   # H3 r5 (~6km) → z5-9
            6: (6, 10),  # H3 r6 (~3.2km) → z6-10
        }
        return zoom_ranges.get(resolution, (5, 9))

    def generate_pmtiles(
        input_geojson: Path,
        output_pmtiles: Path,
        resolution: int,
        layer_name: str = "h3_events",
    ) -> None:
        """Generate PMTiles from newline-delimited GeoJSON.

        Uses Tippecanoe for vector tile generation.

        Args:
            input_geojson: Path to .geojsonl.gz file
            output_pmtiles: Path to output .pmtiles file
            resolution: H3 resolution (determines zoom levels)
            layer_name: Vector tile layer name (default: "h3_events")

        Raises:
            FileNotFoundError: If input file doesn't exist
            subprocess.CalledProcessError: If Tippecanoe fails
        """
        if not input_geojson.exists():
            raise FileNotFoundError(f"Input GeoJSON not found: {input_geojson}")

        output_pmtiles.parent.mkdir(parents=True, exist_ok=True)

        # Map resolution to zoom levels
        min_zoom, max_zoom = get_zoom_range(resolution)

        logger.info(f"Generating PMTiles: {input_geojson.name} → {output_pmtiles.name}")
        logger.info(f"Zoom range: {min_zoom}-{max_zoom} (H3 r{resolution})")

        # Build Tippecanoe command
        cmd = [
            "tippecanoe",
            "-o", str(output_pmtiles),
            "--force",  # Overwrite existing
            f"--minimum-zoom={min_zoom}",
            f"--maximum-zoom={max_zoom}",
            f"--layer={layer_name}",
            "--drop-densest-as-needed",  # Prevent tile size issues
            "--extend-zooms-if-still-dropping",
            "--no-tile-size-limit",
            "--simplification=10",  # Simplify at lower zooms
            "--generate-ids",  # Add feature IDs
            "-P",  # Read newline-delimited GeoJSON
            str(input_geojson),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Report file size
            size_mb = output_pmtiles.stat().st_size / (1024 * 1024)
            logger.info(f"PMTiles generated: {output_pmtiles.name} ({size_mb:.1f} MB)")

        except subprocess.CalledProcessError as e:
            logger.error(f"Tippecanoe failed: {e.stderr}")
            raise
    ```
  - Commit: "feat: add PMTiles generation function"

- [ ] **3.5: Write GeoJSON export test**
  - File: `tests/test_geojson_export.py`
    ```python
    import json
    import gzip
    import pytest
    from pathlib import Path
    from crimecity3k.h3_processing import export_h3_to_geojson

    def test_geojson_export_format(tmp_path, test_config):
        """Test GeoJSON export produces valid format."""
        # Use a real H3 aggregation file
        input_file = Path("data/h3/events_r5.parquet")
        if not input_file.exists():
            pytest.skip("H3 aggregation not built yet")

        output_file = tmp_path / "h3_r5.geojsonl.gz"

        # Run export
        export_h3_to_geojson(
            input_file=input_file,
            output_file=output_file,
            compress=True,
            config=test_config
        )

        # Verify output exists
        assert output_file.exists()

        # Read and parse first 5 features
        with gzip.open(output_file, 'rt') as f:
            for i in range(5):
                line = f.readline()
                if not line:
                    break

                # Parse JSON
                feature = json.loads(line)

                # Verify GeoJSON structure
                assert feature['type'] == 'Feature'
                assert 'geometry' in feature
                assert 'properties' in feature

                # Geometry should be Polygon
                assert feature['geometry']['type'] == 'Polygon'
                coords = feature['geometry']['coordinates'][0]
                assert len(coords) == 7, "Hexagon + closing point"

                # Properties should include metrics
                props = feature['properties']
                assert 'h3_cell' in props
                assert 'event_count' in props
                assert 'population' in props
                assert 'rate_per_10000' in props
                assert 'types_list' in props

    def test_geojson_coordinate_order(tmp_path, test_config):
        """Verify GeoJSON uses lon, lat order."""
        input_file = Path("data/h3/events_r5.parquet")
        if not input_file.exists():
            pytest.skip("H3 aggregation not built yet")

        output_file = tmp_path / "test.geojsonl.gz"
        export_h3_to_geojson(input_file, output_file, config=test_config)

        # Read first feature
        with gzip.open(output_file, 'rt') as f:
            feature = json.loads(f.readline())

        # Check coordinate order (should be [lon, lat])
        coords = feature['geometry']['coordinates'][0][0]
        lon, lat = coords[0], coords[1]

        # Sweden bounds check
        assert 10 < lon < 25, "Longitude should be 10-25"
        assert 55 < lat < 70, "Latitude should be 55-70"
    ```
  - Run: `make test`
  - Commit: "test: add GeoJSON export tests"

- [ ] **3.6: Add GeoJSON export and PMTiles rules to Makefile**
  - Add SQL variable:
    ```makefile
    H3_TO_GEOJSON_SQL := $(SQL_DIR)/h3_to_geojson.sql
    ```
  - Add pattern rules:
    ```makefile
    # GeoJSON export
    $(TILES_DIR)/geojsonl/h3_r%.geojsonl.gz: $(H3_DIR)/events_r%.parquet $(H3_TO_GEOJSON_SQL)
    	@echo "═══ Exporting H3 r$* to GeoJSON ═══"
    	@mkdir -p $(TILES_DIR)/geojsonl
    	uv run python -c " \
    from pathlib import Path; \
    from crimecity3k.h3_processing import export_h3_to_geojson; \
    from crimecity3k.config import Config; \
    config = Config.from_file('$(CONFIG)'); \
    export_h3_to_geojson( \
        Path('$(H3_DIR)/events_r$*.parquet'), \
        Path('$@'), \
        compress=True, \
        config=config \
    ); \
    "
    	@echo "✓ Complete: $@"

    # PMTiles generation
    $(TILES_DIR)/pmtiles/h3_r%.pmtiles: $(TILES_DIR)/geojsonl/h3_r%.geojsonl.gz
    	@echo "═══ Generating PMTiles for r$* ═══"
    	@mkdir -p $(TILES_DIR)/pmtiles
    	uv run python -c " \
    from pathlib import Path; \
    from crimecity3k.pmtiles import generate_pmtiles; \
    generate_pmtiles( \
        Path('$(TILES_DIR)/geojsonl/h3_r$*.geojsonl.gz'), \
        Path('$@'), \
        resolution=$* \
    ); \
    "
    	@echo "✓ Complete: $@"
    ```
  - Test: `make data/tiles/pmtiles/h3_r5.pmtiles`
  - Commit: "build: add GeoJSON and PMTiles pattern rules"

- [ ] **3.7: Update pipeline-all target**
  - Extend to include tiles:
    ```makefile
    .PHONY: pipeline-geojson pipeline-pmtiles

    # Build all GeoJSON exports
    pipeline-geojson: \
    	$(TILES_DIR)/geojsonl/h3_r4.geojsonl.gz \
    	$(TILES_DIR)/geojsonl/h3_r5.geojsonl.gz \
    	$(TILES_DIR)/geojsonl/h3_r6.geojsonl.gz

    # Build all PMTiles
    pipeline-pmtiles: \
    	$(TILES_DIR)/pmtiles/h3_r4.pmtiles \
    	$(TILES_DIR)/pmtiles/h3_r5.pmtiles \
    	$(TILES_DIR)/pmtiles/h3_r6.pmtiles

    # Full pipeline
    pipeline-all: pipeline-pmtiles
    ```
  - Test: `make pipeline-all`
  - Should build entire pipeline
  - Commit: "build: extend pipeline-all to include tiles"

- [ ] **3.8: Add PMTiles inspection test**
  - Test PMTiles metadata:
    ```python
    @pytest.mark.integration
    def test_pmtiles_metadata():
        """Verify PMTiles has correct metadata."""
        import subprocess
        import json

        pmtiles_file = "data/tiles/pmtiles/h3_r5.pmtiles"
        if not Path(pmtiles_file).exists():
            pytest.skip("PMTiles not generated yet")

        # Use pmtiles CLI to show metadata
        result = subprocess.run(
            ['pmtiles', 'show', pmtiles_file, '--json'],
            capture_output=True,
            text=True,
            check=True
        )

        metadata = json.loads(result.stdout)

        # Verify zoom levels
        assert metadata['minzoom'] == 5
        assert metadata['maxzoom'] == 9

        # Verify bounds (Sweden)
        bounds = metadata['bounds']
        assert 10 < bounds[0] < 12  # min lon
        assert 55 < bounds[1] < 56  # min lat
        assert 23 < bounds[2] < 25  # max lon
        assert 67 < bounds[3] < 70  # max lat

        # Verify layer
        assert metadata['vector_layers'][0]['id'] == 'h3_events'
    ```
  - Run: `make test` (if pmtiles CLI available)
  - Commit: "test: add PMTiles metadata verification"

**Phase 3 Complete When:**
- `make pipeline-all` generates all tiles
- PMTiles files are 1-10 MB each
- `pmtiles show data/tiles/pmtiles/h3_r5.pmtiles` displays valid metadata
- All tests pass
- GeoJSON is newline-delimited and valid
- Can inspect tiles with QGIS or PMTiles viewer

---

## Phase 4-7: [Continues with FastAPI, Frontend, Deployment, Documentation...]

[Due to length limits, Phases 4-7 would continue with the same pattern:
- Detailed tasks with code examples
- TDD approach (RED-GREEN-REFACTOR)
- SQL files where applicable
- Config usage throughout
- Atomic writes and error handling
- Comprehensive tests
- Makefile integration
- Clear commit points]

---

## Final Implementation Notes

### Key Patterns Applied

1. **SQL-Driven Pipeline**
   - All transformations in `.sql` files
   - Executed via qck with parameters
   - SQL files tracked as Makefile dependencies

2. **Configuration Management**
   - config.toml with Pydantic validation
   - Type-safe config access
   - Config passed to SQL as parameters

3. **Testing**
   - Test behavior, not SQL implementation
   - Use real SQL execution via qck
   - Minimal mocking
   - Integration tests with full pipeline

4. **Atomic Writes**
   - Write to `.tmp` file
   - Rename on success
   - Clean up on error

5. **Makefile Pattern Rules**
   - `%` wildcards for resolutions
   - SQL and config as dependencies
   - Automatic rebuilds on changes

### Development Workflow

1. Write test (RED)
2. Create SQL file
3. Create Python function to execute SQL
4. Add to Makefile
5. Test passes (GREEN)
6. Add data quality tests (REFACTOR)
7. Commit

### Success Criteria

CrimeCity3K v1 is complete when:
- All 7 phases completed
- All tests pass
- Full pipeline builds with `make pipeline-all`
- Web map displays at http://localhost:8000
- Documentation complete
- CI passing
- v1.0.0 tagged

---

**Total Estimated Time:** 20-25 hours for complete v1

**Next Phase:** Continue with Phase 4 (FastAPI), Phase 5 (Frontend), Phase 6 (Deployment), Phase 7 (Documentation) following the same detailed pattern.
