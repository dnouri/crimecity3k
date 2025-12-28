"""Municipality spatial processing functions.

This module provides functions for aggregating crime events to Swedish
municipality boundaries with population-normalized rates. Uses SQL templates
for core transformations, with Python providing orchestration and error handling.
"""

import logging
from pathlib import Path

from qck import qck  # type: ignore[import-untyped]

from crimecity3k.config import Config
from crimecity3k.data_access import create_configured_connection
from crimecity3k.event_types import get_category_types

logger = logging.getLogger(__name__)


def aggregate_events_to_municipalities(
    events_file: Path,
    population_file: Path,
    output_file: Path,
    config: Config | None = None,
) -> None:
    """Aggregate crime events to Swedish municipalities.

    Executes the municipality_aggregation.sql template to transform police events
    into municipality-level aggregates with pre-computed category counts and
    population-normalized rates. Uses the same 8-category structure as H3
    aggregation for frontend compatibility.

    Key differences from H3 aggregation:
    - JOIN by location_name (case-insensitive) instead of h3_latlng_to_cell()
    - LEFT JOIN ensures all 290 municipalities appear (even with 0 events)
    - Uses official SCB population data instead of H3 population grid
    - Excludes county-level events (location_name ends with " län")

    Args:
        events_file: Path to events Parquet file
        population_file: Path to municipality population CSV
        output_file: Path for output Parquet file (created by this function)
        config: Configuration object (loads from config.toml if None)

    Raises:
        FileNotFoundError: If events or population file doesn't exist
        RuntimeError: If SQL execution fails (wraps underlying exception)

    Example:
        >>> from pathlib import Path
        >>> aggregate_events_to_municipalities(
        ...     Path("data/events.parquet"),
        ...     Path("data/municipalities/population.csv"),
        ...     Path("data/municipalities/events.parquet"),
        ... )
    """
    if config is None:
        config = Config.from_file("config.toml")

    if not events_file.exists():
        raise FileNotFoundError(f"Events file not found: {events_file}")
    if not population_file.exists():
        raise FileNotFoundError(f"Population file not found: {population_file}")

    # Atomic write pattern: write to temp file, rename on success
    temp_file = output_file.with_suffix(".tmp")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Locate SQL template relative to this module
    sql_path = Path(__file__).parent / "sql" / "municipality_aggregation.sql"

    # Build parameters for Jinja2 template rendering
    params = {
        "events_file": str(events_file),
        "population_file": str(population_file),
        "output_file": str(temp_file),  # Write to .tmp first
        "category_types": get_category_types(),  # For Jinja CASE generation
    }

    logger.info("Aggregating events to municipalities")
    logger.info(f"  Events:     {events_file}")
    logger.info(f"  Population: {population_file}")
    logger.info(f"  Output:     {output_file}")

    # Execute SQL with configured connection (no special extensions needed)
    conn = create_configured_connection(config, extensions=[])
    try:
        # qck renders Jinja2 template and executes SQL
        qck(str(sql_path), params=params, connection=conn)

        # Atomic rename on success
        temp_file.rename(output_file)

        # Log result summary
        stats_result = conn.execute(f"""
            SELECT
                COUNT(*) as municipalities,
                SUM(total_count) as total_events,
                SUM(CASE WHEN total_count > 0 THEN 1 ELSE 0 END) as with_events
            FROM '{output_file}'
        """).fetchone()
        assert stats_result is not None
        municipalities, total_events, with_events = stats_result

        logger.info(
            f"  Result: {municipalities} municipalities, {total_events:,} events, "
            f"{with_events} municipalities with events"
        )

    except Exception as e:
        # Clean up temp file on any error
        if temp_file.exists():
            temp_file.unlink()
        logger.error(f"Municipality aggregation failed: {e}")
        raise RuntimeError(f"Failed to aggregate events to municipalities: {e}") from e
    finally:
        conn.close()
