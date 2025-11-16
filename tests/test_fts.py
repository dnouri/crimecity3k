"""Tests for DuckDB full-text search functionality."""

import duckdb
import pytest

from crimecity3k.api.fts import create_fts_index, search_events


@pytest.fixture
def fts_conn() -> duckdb.DuckDBPyConnection:
    """Create DuckDB connection with test events and FTS index."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL fts")
    conn.execute("LOAD fts")

    # Create events table with realistic Swedish police event data
    conn.execute("""
        CREATE TABLE events (
            event_id VARCHAR PRIMARY KEY,
            type VARCHAR,
            summary VARCHAR,
            html_body VARCHAR
        )
    """)

    # Insert test data covering various Swedish crime types
    test_events = [
        ("1", "Stöld", "Cykelstöld vid centralstationen", "En cykel stals vid Stockholm C."),
        ("2", "Stöld/inbrott", "Inbrott i villa", "Tjuvar bröt sig in i villa under natten."),
        ("3", "Misshandel", "Man misshandlad på Kungsgatan", "En man blev misshandlad."),
        ("4", "Narkotikabrott", "Narkotikabeslag i Göteborg", "Polisen beslagtog cannabis."),
        ("5", "Trafikolycka, personskada", "Olycka på E4", "Två bilar kolliderade på motorvägen."),
        ("6", "Rån", "Rån mot butik", "Maskerade män rånade en kiosk."),
    ]

    for event in test_events:
        conn.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?)",
            event,
        )

    return conn


class TestCreateFtsIndex:
    """Tests for FTS index creation."""

    def test_create_fts_index_succeeds(self, fts_conn: duckdb.DuckDBPyConnection) -> None:
        """FTS index creation should succeed on events table."""
        create_fts_index(fts_conn)

        # Verify index exists by attempting a search
        result = fts_conn.execute("""
            SELECT event_id FROM events
            WHERE fts_main_events.match_bm25(event_id, 'stöld') IS NOT NULL
        """).fetchall()

        assert len(result) > 0

    def test_create_fts_index_idempotent(self, fts_conn: duckdb.DuckDBPyConnection) -> None:
        """Creating FTS index twice should not fail."""
        create_fts_index(fts_conn)
        create_fts_index(fts_conn)  # Should not raise


class TestSearchEvents:
    """Tests for FTS search functionality."""

    @pytest.fixture(autouse=True)
    def setup_fts(self, fts_conn: duckdb.DuckDBPyConnection) -> None:
        """Create FTS index before each test."""
        self.conn = fts_conn
        create_fts_index(fts_conn)

    def test_search_matches_type(self) -> None:
        """Search should match event type field."""
        results = search_events(self.conn, "Misshandel")
        event_ids = [r["event_id"] for r in results]
        assert "3" in event_ids

    def test_search_matches_summary(self) -> None:
        """Search should match summary field."""
        results = search_events(self.conn, "centralstationen")
        event_ids = [r["event_id"] for r in results]
        assert "1" in event_ids

    def test_search_matches_html_body(self) -> None:
        """Search should match html_body field."""
        results = search_events(self.conn, "motorvägen")
        event_ids = [r["event_id"] for r in results]
        assert "5" in event_ids

    def test_search_no_results_returns_empty(self) -> None:
        """Search with no matches should return empty list."""
        results = search_events(self.conn, "xyznonexistent")
        assert results == []

    def test_search_swedish_plurals(self) -> None:
        """Swedish stemmer should handle noun plurals."""
        # Both "stöld" and "stölder" should match
        results_singular = search_events(self.conn, "stöld")
        results_plural = search_events(self.conn, "stölder")

        # Should find events mentioning theft
        assert len(results_singular) > 0
        assert len(results_plural) > 0

    def test_search_returns_relevance_scores(self) -> None:
        """Search results should include BM25 relevance scores."""
        results = search_events(self.conn, "stöld")
        assert len(results) > 0
        # Results should have score field
        assert "score" in results[0]
        assert isinstance(results[0]["score"], float)
        assert results[0]["score"] > 0

    def test_search_results_ordered_by_relevance(self) -> None:
        """Search results should be ordered by relevance (highest first)."""
        results = search_events(self.conn, "stöld")
        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)
