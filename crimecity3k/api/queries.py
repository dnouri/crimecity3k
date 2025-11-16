"""Database query functions for events API.

Executes parameterized queries against DuckDB for event retrieval
with filtering, pagination, and full-text search.
"""

import re
from datetime import date, datetime
from typing import Any

import duckdb

from crimecity3k.api.categories import CATEGORY_TYPES, get_category

# H3 cell ID pattern: 15 hex characters
H3_CELL_PATTERN = re.compile(r"^[0-9a-fA-F]{15}$")


def is_valid_h3_cell(h3_cell: str) -> bool:
    """Check if string is a valid H3 cell ID.

    Args:
        h3_cell: Potential H3 cell ID string

    Returns:
        True if valid H3 cell format
    """
    return bool(H3_CELL_PATTERN.match(h3_cell))


def query_events(
    conn: duckdb.DuckDBPyConnection,
    h3_cell: str | None = None,
    location_name: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    categories: list[str] | None = None,
    types: list[str] | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> dict[str, Any]:
    """Query events within an H3 cell or location with filtering and pagination.

    Args:
        conn: DuckDB connection with events table and FTS index
        h3_cell: H3 cell ID to query (mutually exclusive with location_name)
        location_name: Municipality/location name to query (case-insensitive)
        start_date: Optional filter for events on or after this date
        end_date: Optional filter for events before this date
        categories: Optional list of categories to filter by
        types: Optional list of specific event types to filter by
        search: Optional full-text search query
        page: Page number (1-indexed)
        per_page: Results per page (max 100)

    Returns:
        Dict with total count, page info, and list of events

    Raises:
        ValueError: If neither h3_cell nor location_name provided, or if both provided
    """
    # Validate: exactly one of h3_cell or location_name must be provided
    if h3_cell and location_name:
        raise ValueError("Cannot specify both h3_cell and location_name")
    if not h3_cell and not location_name:
        raise ValueError("Must specify either h3_cell or location_name")

    # Build WHERE conditions and parameters
    conditions: list[str] = []
    params: list[Any] = []

    if h3_cell:
        if not is_valid_h3_cell(h3_cell):
            raise ValueError(f"Invalid H3 cell ID: {h3_cell}")
        conditions.append("h3_cell = ?")
        params.append(h3_cell)
    elif location_name:
        conditions.append("LOWER(location_name) = LOWER(?)")
        params.append(location_name)

    if start_date:
        conditions.append("datetime >= ?")
        params.append(start_date.isoformat())

    if end_date:
        conditions.append("datetime < ?")
        # Add one day to make it exclusive of end date
        params.append((end_date.isoformat()) + "T23:59:59")

    if categories:
        # Map categories to their types
        allowed_types: set[str] = set()
        for cat in categories:
            if cat in CATEGORY_TYPES:
                allowed_types.update(CATEGORY_TYPES[cat])
            elif cat == "other":
                # 'other' is handled specially - we need to find types not in known categories
                pass
        if allowed_types:
            placeholders = ", ".join("?" * len(allowed_types))
            conditions.append(f"type IN ({placeholders})")
            params.extend(allowed_types)

    if types:
        placeholders = ", ".join("?" * len(types))
        conditions.append(f"type IN ({placeholders})")
        params.extend(types)

    # Add FTS search condition if provided
    fts_condition = ""
    if search and search.strip():
        # Escape single quotes for FTS
        safe_search = search.replace("'", "''")
        fts_condition = f"AND fts_main_events.match_bm25(event_id, '{safe_search}') IS NOT NULL"

    where_clause = " AND ".join(conditions)

    # First, get total count
    count_sql = f"""
        SELECT COUNT(*) FROM events
        WHERE {where_clause} {fts_condition}
    """
    result = conn.execute(count_sql, params).fetchone()
    total: int = result[0] if result else 0

    # Calculate offset
    offset = (page - 1) * per_page

    # Query events with pagination
    events_sql = f"""
        SELECT
            event_id,
            datetime,
            type,
            summary,
            html_body,
            url,
            location_name,
            latitude,
            longitude
        FROM events
        WHERE {where_clause} {fts_condition}
        ORDER BY datetime DESC
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, offset])

    results = conn.execute(events_sql, params).fetchall()

    # Build response
    events = []
    for row in results:
        event_type = row[2]
        # Parse datetime - format may be '2024-01-21 7:12:20 +01:00' or ISO
        dt_raw = row[1]
        if isinstance(dt_raw, str):
            # Handle various formats:
            # - '2024-01-21 7:12:20 +01:00' (space before timezone)
            # - '2024-01-21 7:12:20+01:00' (no space before timezone)
            # Extract just the datetime part, ignoring timezone
            # Find where timezone starts (+ or -)
            tz_idx = dt_raw.find("+")
            if tz_idx == -1:
                tz_idx = dt_raw.rfind("-")
                # Make sure we don't catch the date separator
                if tz_idx < 10:
                    tz_idx = -1

            if tz_idx > 0:
                dt_part = dt_raw[:tz_idx].strip()
            else:
                dt_part = dt_raw

            try:
                event_dt = datetime.strptime(dt_part, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Try ISO format as fallback
                try:
                    event_dt = datetime.fromisoformat(dt_raw)
                except ValueError:
                    # Last resort: just use current time
                    event_dt = datetime.now()
        else:
            event_dt = dt_raw

        events.append(
            {
                "event_id": row[0],
                "event_datetime": event_dt,
                "type": event_type,
                "category": get_category(event_type),
                "summary": row[3] or "",
                "html_body": row[4] if row[4] else None,
                "police_url": f"https://polisen.se{row[5]}" if row[5] else "",
                "location_name": row[6] or "",
                "latitude": row[7],
                "longitude": row[8],
            }
        )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "events": events,
    }


def get_type_hierarchy(conn: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Get category→types hierarchy including 'other' types from data.

    Args:
        conn: DuckDB connection with events table

    Returns:
        Dict mapping category names to list of event types
    """
    # Start with known categories
    hierarchy = {cat: list(types) for cat, types in CATEGORY_TYPES.items()}

    # Find 'other' types from actual data
    result = conn.execute("SELECT DISTINCT type FROM events").fetchall()
    all_types = [r[0] for r in result]

    other_types = [t for t in all_types if get_category(t) == "other"]
    hierarchy["other"] = sorted(other_types)

    return hierarchy


def get_event_count(conn: duckdb.DuckDBPyConnection) -> int:
    """Get total event count in database.

    Args:
        conn: DuckDB connection with events table

    Returns:
        Total number of events
    """
    result = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    return result[0] if result else 0
