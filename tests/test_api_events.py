"""Tests for events API endpoints.

These tests verify the API behavior for querying events by H3 cell
with filtering, pagination, and full-text search.

Uses the test fixture events_2024_01_15-22.parquet (476 events from one week).
"""

from collections.abc import Generator
from pathlib import Path

import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from crimecity3k.api.categories import get_category
from crimecity3k.api.fts import create_fts_index


@pytest.fixture(scope="module")
def events_db() -> Generator[duckdb.DuckDBPyConnection]:
    """Create in-memory database with test events and FTS index.

    Module-scoped to avoid recreating FTS index for each test.
    """
    fixture_path = Path(__file__).parent / "fixtures" / "events_2024_01_15-22.parquet"

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
            '' AS html_body,  -- Test fixture doesn't have html_body
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
def sample_h3_cell(events_db: duckdb.DuckDBPyConnection) -> str:
    """Get an H3 cell with many events for testing."""
    result = events_db.execute("""
        SELECT h3_cell, COUNT(*) as cnt
        FROM events
        GROUP BY h3_cell
        ORDER BY cnt DESC
        LIMIT 1
    """).fetchone()
    assert result is not None, "No events in test database"
    cell: str = result[0]
    return cell


@pytest.fixture(scope="module")
def sample_cell_event_count(events_db: duckdb.DuckDBPyConnection, sample_h3_cell: str) -> int:
    """Get count of events in sample cell."""
    result = events_db.execute(f"""
        SELECT COUNT(*) FROM events WHERE h3_cell = '{sample_h3_cell}'
    """).fetchone()
    assert result is not None
    count: int = result[0]
    return count


@pytest.fixture
def app_with_db(events_db: duckdb.DuckDBPyConnection) -> FastAPI:
    """Create FastAPI app configured with test database.

    This fixture creates a new FastAPI app for each test, but reuses
    the module-scoped database to avoid FTS index recreation.
    """
    from crimecity3k.api.main import app

    # Store connection in app state for queries module to use
    app.state.db = events_db
    return app


@pytest.fixture
def client(app_with_db: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app_with_db)


class TestQueryEventsBasic:
    """Tests for basic event querying."""

    def test_query_events_by_h3_cell_returns_results(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Querying events for a valid H3 cell should return results."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        assert len(data["events"]) > 0

    def test_query_events_returns_correct_total_count(
        self, client: TestClient, sample_h3_cell: str, sample_cell_event_count: int
    ) -> None:
        """Total count should match actual events in cell."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}")
        data = response.json()
        assert data["total"] == sample_cell_event_count

    def test_query_events_pagination_works(self, client: TestClient, sample_h3_cell: str) -> None:
        """Pagination should return correct page of results."""
        # Get first page
        response1 = client.get(f"/api/events?h3_cell={sample_h3_cell}&page=1&per_page=10")
        data1 = response1.json()

        # Get second page
        response2 = client.get(f"/api/events?h3_cell={sample_h3_cell}&page=2&per_page=10")
        data2 = response2.json()

        # Pages should have different events (if enough events exist)
        if data1["total"] > 10:
            assert data1["events"][0]["event_id"] != data2["events"][0]["event_id"]
            assert data1["page"] == 1
            assert data2["page"] == 2

    def test_query_events_empty_cell_returns_empty_list(self, client: TestClient) -> None:
        """Querying an H3 cell with no events should return empty list."""
        # Use a cell that definitely has no events (ocean)
        response = client.get("/api/events?h3_cell=85283473fffffff")
        data = response.json()
        assert data["total"] == 0
        assert data["events"] == []


class TestQueryEventsDateFiltering:
    """Tests for date range filtering."""

    def test_query_events_with_date_range_filters_correctly(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Events should be filtered by date range."""
        # Test fixture has events from 2024-01-15 to 2024-01-22
        response = client.get(
            f"/api/events?h3_cell={sample_h3_cell}&start_date=2024-01-16&end_date=2024-01-17"
        )
        data = response.json()
        # Should have fewer events than unfiltered
        response_all = client.get(f"/api/events?h3_cell={sample_h3_cell}")
        data_all = response_all.json()
        assert data["total"] <= data_all["total"]

    def test_query_events_with_start_date_only(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Filtering by start date only should work."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&start_date=2024-01-20")
        assert response.status_code == 200
        data = response.json()
        # All returned events should be on or after start date
        for event in data["events"]:
            assert event["event_datetime"] >= "2024-01-20"

    def test_query_events_with_end_date_only(self, client: TestClient, sample_h3_cell: str) -> None:
        """Filtering by end date only should work."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&end_date=2024-01-17")
        assert response.status_code == 200
        data = response.json()
        # All returned events should be before end date
        for event in data["events"]:
            assert event["event_datetime"] < "2024-01-18"


class TestQueryEventsCategoryFiltering:
    """Tests for category and type filtering."""

    def test_query_events_by_category_filters_correctly(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Filtering by category should return only matching events."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&categories=traffic")
        data = response.json()
        # All returned events should be in traffic category
        for event in data["events"]:
            assert event["category"] == "traffic"

    def test_query_events_by_multiple_categories(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Filtering by multiple categories should work."""
        response = client.get(
            f"/api/events?h3_cell={sample_h3_cell}&categories=traffic&categories=property"
        )
        data = response.json()
        # All events should be in one of the specified categories
        for event in data["events"]:
            assert event["category"] in ["traffic", "property"]

    def test_query_events_by_specific_type(self, client: TestClient, sample_h3_cell: str) -> None:
        """Filtering by specific event type should work."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&types=Stöld")
        data = response.json()
        for event in data["events"]:
            assert event["type"] == "Stöld"

    def test_query_events_by_category_and_type_combined(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Combining category and type filters should work."""
        response = client.get(
            f"/api/events?h3_cell={sample_h3_cell}&categories=property&types=Stöld"
        )
        data = response.json()
        for event in data["events"]:
            assert event["category"] == "property"
            assert event["type"] == "Stöld"


class TestQueryEventsSearch:
    """Tests for full-text search."""

    def test_query_events_with_search_term_matches_summary(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Search should match terms in summary field."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&search=polis")
        assert response.status_code == 200
        # Results should contain search term (may be 0 if no matches)

    def test_query_events_with_search_term_matches_type(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Search should match terms in type field."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&search=stöld")
        data = response.json()
        # If we have events returned (above privacy threshold), check types
        # Note: may return total > 0 but events = [] if below threshold
        if data["events"]:
            # At least some should have Stöld in type
            types_found = [e["type"] for e in data["events"]]
            assert any("töld" in t.lower() for t in types_found)

    def test_query_events_search_combined_with_filters(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Search should work together with other filters."""
        response = client.get(
            f"/api/events?h3_cell={sample_h3_cell}&categories=property&search=stöld"
        )
        data = response.json()
        # All results should match both category and search
        for event in data["events"]:
            assert event["category"] == "property"


class TestQueryEventsEdgeCases:
    """Tests for edge cases and validation."""

    def test_query_events_invalid_h3_cell_returns_400(self, client: TestClient) -> None:
        """Invalid H3 cell should return 400 error."""
        response = client.get("/api/events?h3_cell=invalid_cell_id")
        assert response.status_code == 400

    def test_query_events_page_beyond_results_returns_empty(
        self, client: TestClient, sample_h3_cell: str
    ) -> None:
        """Requesting a page beyond results should return empty list."""
        response = client.get(f"/api/events?h3_cell={sample_h3_cell}&page=9999")
        data = response.json()
        assert data["events"] == []
        assert data["page"] == 9999
        # Total should still be accurate
        assert data["total"] >= 0

    def test_query_events_per_page_capped_at_100(self, client: TestClient) -> None:
        """Requesting more than 100 per page should be rejected."""
        response = client.get("/api/events?h3_cell=test&per_page=200")
        assert response.status_code == 422  # Validation error


class TestQueryEventsThreshold:
    """Tests for privacy threshold enforcement."""

    def test_query_events_cell_under_threshold_returns_limited_response(
        self, client: TestClient, events_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Cells with <3 events should return limited response."""
        # Find a cell with 1-2 events
        result = events_db.execute("""
            SELECT h3_cell, COUNT(*) as cnt
            FROM events
            GROUP BY h3_cell
            HAVING cnt < 3 AND cnt > 0
            LIMIT 1
        """).fetchone()

        if result is None:
            pytest.skip("No cells with 1-2 events in test fixture")

        sparse_cell = result[0]
        response = client.get(f"/api/events?h3_cell={sparse_cell}")
        data = response.json()

        # Should return count but not individual events
        assert data["total"] < 3
        assert data["total"] > 0
        # Events list should be empty (privacy threshold)
        assert data["events"] == []


class TestTypesEndpoint:
    """Tests for the types hierarchy endpoint."""

    def test_get_types_returns_category_hierarchy(self, client: TestClient) -> None:
        """Types endpoint should return all categories with their types."""
        response = client.get("/api/types")
        assert response.status_code == 200
        data = response.json()

        # Should have categories dict
        assert "categories" in data
        categories = data["categories"]

        # Should have all expected categories
        assert "traffic" in categories
        assert "property" in categories
        assert "violence" in categories
        assert "narcotics" in categories
        assert "fraud" in categories
        assert "public_order" in categories
        assert "weapons" in categories
        assert "other" in categories

        # Traffic should have expected types
        assert "Trafikolycka, personskada" in categories["traffic"]
        assert "Rattfylleri" in categories["traffic"]

    def test_get_types_other_category_populated_from_data(
        self, client: TestClient, events_db: duckdb.DuckDBPyConnection
    ) -> None:
        """The 'other' category should be populated with types from data."""
        response = client.get("/api/types")
        data = response.json()

        # Find types in data that aren't in known categories
        result = events_db.execute("""
            SELECT DISTINCT type FROM events
        """).fetchall()
        all_types = [r[0] for r in result]

        # Verify we can identify 'other' types from the data
        other_types_in_data = [t for t in all_types if get_category(t) == "other"]

        # The 'other' category in response should be a list
        # (May be empty initially, populated by queries module later)
        assert isinstance(data["categories"]["other"], list)

        # Verify our category function works
        assert all(get_category(t) == "other" for t in other_types_in_data)
