"""DuckDB full-text search setup and utilities.

Provides FTS indexing for Swedish police event data with Swedish stemming.
The FTS index enables fast text search across event type, summary, and html_body.

FTS Index Behavior:
- Index persists with file-based DuckDB connections
- For in-memory connections, index must be created at startup
- Uses Swedish stemmer for better matching of Swedish word forms
- BM25 ranking for relevance-based result ordering
"""

from typing import Any

import duckdb


def create_fts_index(conn: duckdb.DuckDBPyConnection) -> None:
    """Create full-text search index on events table.

    Creates an FTS index with Swedish stemming on the type, summary, and
    html_body columns. Uses event_id as the document identifier.

    The index is idempotent - calling this function multiple times is safe.
    If the index already exists, it will be dropped and recreated.

    Args:
        conn: DuckDB connection with events table and FTS extension loaded

    Note:
        Requires FTS extension to be installed and loaded before calling.
        The events table must have columns: event_id, type, summary, html_body
    """
    # Drop existing index if present (makes function idempotent)
    try:
        conn.execute("PRAGMA drop_fts_index('events')")
    except duckdb.CatalogException:
        # Index doesn't exist, that's fine
        pass

    # Create FTS index with Swedish stemmer
    conn.execute("""
        PRAGMA create_fts_index(
            'events',
            'event_id',
            'type', 'summary', 'html_body',
            stemmer='swedish'
        )
    """)


def search_events(
    conn: duckdb.DuckDBPyConnection,
    query: str,
) -> list[dict[str, Any]]:
    """Search events using full-text search.

    Searches across type, summary, and html_body fields using BM25 ranking.
    Results are ordered by relevance score (highest first).

    Args:
        conn: DuckDB connection with FTS index created
        query: Search query string (supports Swedish stemming)

    Returns:
        List of dicts with event_id and score, ordered by relevance.
        Empty list if no matches found.

    Example:
        >>> results = search_events(conn, "stöld")
        >>> for r in results:
        ...     print(f"Event {r['event_id']}: score {r['score']:.3f}")
    """
    if not query or not query.strip():
        return []

    # Escape single quotes in query to prevent SQL injection
    safe_query = query.replace("'", "''")

    result = conn.execute(f"""
        SELECT
            event_id,
            fts_main_events.match_bm25(event_id, '{safe_query}') AS score
        FROM events
        WHERE score IS NOT NULL
        ORDER BY score DESC
    """).fetchall()

    return [{"event_id": row[0], "score": row[1]} for row in result]
