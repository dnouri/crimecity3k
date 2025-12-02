"""FastAPI application for CrimeCity3K event drill-down API.

Provides:
- /api/events: Query events by H3 cell with filtering and search
- /api/types: Get category→types hierarchy for filter UI
- /health: Health check endpoint
- Static file serving for frontend and PMTiles (with HTTP Range support)

Usage:
    python -m crimecity3k.api.main [--port 8080]
    # Or via make:
    make serve
"""

import argparse
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

import duckdb
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from crimecity3k.api.categories import CATEGORY_TYPES
from crimecity3k.api.fts import create_fts_index
from crimecity3k.api.queries import (
    get_event_count,
    get_type_hierarchy,
    is_valid_h3_cell,
    query_events,
)
from crimecity3k.api.schemas import (
    EventResponse,
    EventsListResponse,
    HealthResponse,
    TypeHierarchy,
)

# Default H3 resolution for drill-down queries
DEFAULT_H3_RESOLUTION = 5


def init_database(events_parquet: Path) -> duckdb.DuckDBPyConnection:
    """Initialize DuckDB with events data, H3 cells, and FTS index.

    Args:
        events_parquet: Path to events.parquet file

    Returns:
        Configured DuckDB connection

    Raises:
        FileNotFoundError: If events parquet file doesn't exist
    """
    if not events_parquet.exists():
        raise FileNotFoundError(f"Events file not found: {events_parquet}")

    conn = duckdb.connect()

    # Install and load required extensions
    conn.execute("INSTALL h3 FROM community; LOAD h3")
    conn.execute("INSTALL fts; LOAD fts")

    # Load events with computed H3 cell (hex string format)
    conn.execute(f"""
        CREATE TABLE events AS
        SELECT
            *,
            h3_latlng_to_cell_string(latitude, longitude, {DEFAULT_H3_RESOLUTION}) AS h3_cell
        FROM '{events_parquet}'
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    # Create FTS index for search
    create_fts_index(conn)

    return conn


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifespan - initialize and cleanup database."""
    root_dir: Path = getattr(app.state, "root_dir", Path(__file__).parent.parent.parent)
    events_path = root_dir / "data" / "events.parquet"

    try:
        print(f"Initializing database from {events_path}...")
        app.state.db = init_database(events_path)
        count = get_event_count(app.state.db)
        print(f"✓ Database ready with {count:,} events")
    except FileNotFoundError as e:
        print(f"⚠ Warning: {e}")
        print("  API will run but /api/events will return 503")
        app.state.db = None

    yield

    # Cleanup
    if app.state.db:
        app.state.db.close()


# API metadata for OpenAPI docs
app = FastAPI(
    title="CrimeCity3K API",
    description="Swedish police events drill-down API with full-text search",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


def get_db(request: Request) -> duckdb.DuckDBPyConnection:
    """Get database connection from app state.

    Args:
        request: FastAPI request object

    Returns:
        DuckDB connection

    Raises:
        HTTPException: If database not initialized
    """
    db: duckdb.DuckDBPyConnection | None = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(request: Request) -> HealthResponse:
    """Check API health and return basic stats."""
    try:
        db = get_db(request)
        count = get_event_count(db)
        return HealthResponse(status="healthy", events_count=count)
    except HTTPException:
        # Database not initialized - still healthy but no events
        return HealthResponse(status="healthy", events_count=0)


@app.get("/api/types", response_model=TypeHierarchy, tags=["Events"])
async def get_types(request: Request) -> TypeHierarchy:
    """Get category→types hierarchy for filter UI.

    Returns all 8 categories with their associated event types.
    The 'other' category is populated dynamically from database.
    """
    try:
        db = get_db(request)
        hierarchy = get_type_hierarchy(db)
        return TypeHierarchy(categories=hierarchy)
    except HTTPException:
        # Database not initialized - return static categories
        categories = {**CATEGORY_TYPES, "other": []}
        return TypeHierarchy(categories=categories)


@app.get("/api/events", response_model=EventsListResponse, tags=["Events"])
async def get_events(
    request: Request,
    h3_cell: Annotated[str, Query(description="H3 cell ID to query events for")],
    start_date: Annotated[date | None, Query(description="Filter start date")] = None,
    end_date: Annotated[date | None, Query(description="Filter end date")] = None,
    categories: Annotated[
        list[str] | None,
        Query(description="Filter by categories (e.g., 'traffic', 'violence')"),
    ] = None,
    types: Annotated[list[str] | None, Query(description="Filter by specific event types")] = None,
    search: Annotated[
        str | None, Query(description="Full-text search query (Swedish stemming)")
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Events per page (max 100)")] = 50,
) -> EventsListResponse:
    """Query events within an H3 cell with optional filtering.

    Supports filtering by date range, categories, types, and full-text search.
    Results are paginated with configurable page size (max 100).

    Search uses Swedish stemming so "stöld" matches "stölder" etc.
    """
    # Validate H3 cell
    if not is_valid_h3_cell(h3_cell):
        raise HTTPException(status_code=400, detail=f"Invalid H3 cell ID: {h3_cell}")

    db = get_db(request)

    try:
        result = query_events(
            conn=db,
            h3_cell=h3_cell,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            types=types,
            search=search,
            page=page,
            per_page=per_page,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Convert to response model
    events = [
        EventResponse(
            event_id=e["event_id"],
            event_datetime=e["event_datetime"],
            type=e["type"],
            category=e["category"],
            location_name=e["location_name"],
            summary=e["summary"],
            html_body=e["html_body"],
            police_url=e["police_url"],
            latitude=e["latitude"],
            longitude=e["longitude"],
        )
        for e in result["events"]
    ]

    return EventsListResponse(
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        events=events,
    )


def create_app(
    root_dir: Path | None = None,
    tiles_dir: Path | None = None,
) -> FastAPI:
    """Create configured FastAPI app with static file mounts.

    Mounts static files with HTTP Range request support (required for PMTiles).

    Args:
        root_dir: Directory containing static/ folder. Defaults to project root.
        tiles_dir: Directory containing PMTiles. Defaults to root_dir/data/tiles/pmtiles.

    Returns:
        Configured FastAPI application
    """
    if root_dir is None:
        root_dir = Path(__file__).parent.parent.parent

    if tiles_dir is None:
        tiles_dir = root_dir / "data" / "tiles" / "pmtiles"

    # Store root_dir for lifespan to find events.parquet
    app.state.root_dir = root_dir

    # Mount static files (Starlette's StaticFiles supports HTTP Range requests)
    static_dir = root_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Mount PMTiles directory (needs Range support for efficient tile fetching)
    if tiles_dir.exists():
        app.mount(
            "/data/tiles/pmtiles",
            StaticFiles(directory=tiles_dir),
            name="tiles",
        )

    # Mount data directory for other data files
    data_dir = root_dir / "data"
    if data_dir.exists():
        app.mount("/data", StaticFiles(directory=data_dir), name="data")

    return app


def main() -> None:
    """Run the development server."""
    import uvicorn

    parser = argparse.ArgumentParser(description="CrimeCity3K development server")
    parser.add_argument(
        "--port", "-p", type=int, default=8080, help="Port to serve on (default: 8080)"
    )
    parser.add_argument(
        "--host",
        "-H",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    print("Starting CrimeCity3K server...")
    print(f"View at: http://{args.host}:{args.port}/static/index.html")
    print(f"API docs: http://{args.host}:{args.port}/docs")
    print("Press Ctrl+C to stop\n")

    create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
