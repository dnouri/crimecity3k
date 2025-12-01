"""FastAPI application for CrimeCity3K event drill-down API.

Provides:
- /api/events: Query events by H3 cell with filtering and search
- /api/types: Get category→types hierarchy for filter UI
- /health: Health check endpoint
- Static file serving for frontend and PMTiles
"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles

from crimecity3k.api.categories import CATEGORY_TYPES
from crimecity3k.api.schemas import (
    EventResponse,
    EventsListResponse,
    HealthResponse,
    TypeHierarchy,
)

# API metadata for OpenAPI docs
app = FastAPI(
    title="CrimeCity3K API",
    description="Swedish police events drill-down API with full-text search",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Check API health and return basic stats."""
    # TODO: Implement actual database connection and event count
    return HealthResponse(status="healthy", events_count=0)


@app.get("/api/types", response_model=TypeHierarchy, tags=["Events"])
async def get_types() -> TypeHierarchy:
    """Get category→types hierarchy for filter UI.

    Returns all 8 categories with their associated event types.
    The 'other' category is populated dynamically from database.
    """
    # Include 'other' with empty list - will be populated by queries module
    categories = {**CATEGORY_TYPES, "other": []}
    return TypeHierarchy(categories=categories)


@app.get("/api/events", response_model=EventsListResponse, tags=["Events"])
async def get_events(
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
    # TODO: Implement actual database query in Task 5.4
    # This stub returns mock data for frontend development
    mock_event = EventResponse(
        event_id="stub-1",
        event_datetime=datetime.now(),
        type="Stöld",
        category="property",
        location_name="Stockholm",
        summary="Stub event for frontend development",
        html_body="Detailed description would go here.",
        police_url="https://polisen.se/aktuellt/handelser/stub/",
        latitude=59.329,
        longitude=18.068,
    )
    return EventsListResponse(
        total=1,
        page=page,
        per_page=per_page,
        events=[mock_event],
    )


def create_app(
    root_dir: Path | None = None,
    tiles_dir: Path | None = None,
) -> FastAPI:
    """Create configured FastAPI app with static file mounts.

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

    # Mount static files
    static_dir = root_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Mount PMTiles
    if tiles_dir.exists():
        app.mount(
            "/data/tiles/pmtiles",
            StaticFiles(directory=tiles_dir),
            name="tiles",
        )

    return app


# For running directly with uvicorn
if __name__ == "__main__":
    import uvicorn

    create_app()
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="info")
