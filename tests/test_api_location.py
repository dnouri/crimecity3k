"""Tests for events API with location_name queries.

These tests verify the API behavior for querying events by location_name
(municipality name) instead of H3 cell - enabling municipality-based
drill-down in the frontend.

Uses the same fixture patterns as test_api_events.py for consistency.
"""

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crimecity3k.api.fts import create_fts_index


@pytest.fixture(scope="module")
def events_db() -> Generator[duckdb.DuckDBPyConnection]:
    """Create in-memory database with test events and FTS index.

    Module-scoped to avoid recreating FTS index for each test.
    """
    fixture_path = Path(__file__).parent / "fixtures" / "data" / "events.parquet"

    conn = duckdb.connect(":memory:")

    # Load extensions
    conn.execute("INSTALL fts")
    conn.execute("LOAD fts")
    conn.execute("INSTALL h3 FROM community")
    conn.execute("LOAD h3")

    # Load events with computed fields
    conn.execute(f"""
        CREATE TABLE events AS
        SELECT
            event_id,
            datetime,
            name,
            type,
            summary,
            '' AS html_body,
            url,
            location_name,
            latitude,
            longitude,
            h3_latlng_to_cell_string(latitude, longitude, 5) AS h3_cell
        FROM '{fixture_path}'
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)

    # Create FTS index
    create_fts_index(conn)

    yield conn
    conn.close()


@pytest.fixture(scope="module")
def sample_location(events_db: duckdb.DuckDBPyConnection) -> str:
    """Get a location_name with many events for testing."""
    result = events_db.execute("""
        SELECT location_name, COUNT(*) as cnt
        FROM events
        WHERE location_name NOT LIKE '% län'
        GROUP BY location_name
        ORDER BY cnt DESC
        LIMIT 1
    """).fetchone()
    assert result is not None, "No events in test database"
    location: str = result[0]
    return location


@pytest.fixture(scope="module")
def sample_location_event_count(events_db: duckdb.DuckDBPyConnection, sample_location: str) -> int:
    """Get count of events in sample location directly from database."""
    result = events_db.execute(
        """
        SELECT COUNT(*) FROM events WHERE LOWER(location_name) = LOWER(?)
    """,
        [sample_location],
    ).fetchone()
    assert result is not None
    count: int = result[0]
    return count


@pytest.fixture
def app_with_db(events_db: duckdb.DuckDBPyConnection) -> Generator[FastAPI]:
    """Configure FastAPI app with test database, cleaning up after.

    Reuses the module-scoped database to avoid FTS index recreation.
    Restores original app.state.db on teardown to prevent test pollution.
    """
    from crimecity3k.api.main import app

    # Save original state and set test database
    original_db = getattr(app.state, "db", None)
    app.state.db = events_db
    yield app
    # Restore original state (prevents pollution to other test modules)
    app.state.db = original_db


@pytest.fixture
def client(app_with_db: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app_with_db)


class TestLocationNameQueries:
    """Tests for querying events by location_name."""

    def test_query_by_location_name_returns_events(
        self, client: TestClient, sample_location: str
    ) -> None:
        """Query by location_name returns events for that municipality."""
        response = client.get("/api/events", params={"location_name": sample_location})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        assert len(data["events"]) > 0

    def test_query_by_location_name_returns_correct_count(
        self,
        client: TestClient,
        sample_location: str,
        sample_location_event_count: int,
    ) -> None:
        """Query by location_name returns correct total count."""
        response = client.get("/api/events", params={"location_name": sample_location})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == sample_location_event_count

    def test_location_name_case_insensitive(self, client: TestClient, sample_location: str) -> None:
        """Location name matching is case-insensitive."""
        # Query with lowercase
        response = client.get("/api/events", params={"location_name": sample_location.lower()})
        assert response.status_code == 200
        lower_count = response.json()["total"]

        # Query with uppercase
        response = client.get("/api/events", params={"location_name": sample_location.upper()})
        assert response.status_code == 200
        upper_count = response.json()["total"]

        # Should be same count
        assert lower_count == upper_count

    def test_location_name_empty_returns_error(self, client: TestClient) -> None:
        """Empty location_name returns 422 validation error."""
        response = client.get("/api/events", params={"location_name": ""})
        assert response.status_code == 422

    def test_location_name_unknown_returns_empty(self, client: TestClient) -> None:
        """Unknown location_name returns empty results."""
        response = client.get("/api/events", params={"location_name": "Nonexistent Municipality"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["events"] == []

    def test_must_provide_h3_cell_or_location_name(self, client: TestClient) -> None:
        """API returns 400 if neither h3_cell nor location_name provided."""
        response = client.get("/api/events")
        assert response.status_code == 400

    def test_cannot_provide_both_h3_cell_and_location_name(
        self, client: TestClient, sample_location: str
    ) -> None:
        """API returns 400 if both h3_cell and location_name provided."""
        response = client.get(
            "/api/events",
            params={
                "h3_cell": "850e35a3fffffff",  # Valid H3 cell
                "location_name": sample_location,
            },
        )
        assert response.status_code == 400


class TestLocationNameFiltering:
    """Tests for filtering by location_name with other filters."""

    def test_location_name_with_date_filter(self, client: TestClient, sample_location: str) -> None:
        """Location name query works with date filtering."""
        response = client.get(
            "/api/events",
            params={
                "location_name": sample_location,
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )
        assert response.status_code == 200

    def test_location_name_with_category_filter(
        self, client: TestClient, sample_location: str
    ) -> None:
        """Location name query works with category filtering."""
        response = client.get(
            "/api/events",
            params={
                "location_name": sample_location,
                "categories": ["traffic"],
            },
        )
        assert response.status_code == 200

    def test_location_name_with_search(self, client: TestClient, sample_location: str) -> None:
        """Location name query works with full-text search."""
        response = client.get(
            "/api/events",
            params={
                "location_name": sample_location,
                "search": "stöld",
            },
        )
        assert response.status_code == 200

    def test_location_name_pagination(self, client: TestClient, sample_location: str) -> None:
        """Location name query works with pagination."""
        response = client.get(
            "/api/events",
            params={
                "location_name": sample_location,
                "page": 1,
                "per_page": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 5
        assert len(data["events"]) <= 5
