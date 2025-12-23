"""Tests for municipality event aggregation pipeline.

Tests the critical invariants for Task 6.2:
- Aggregation by location_name to municipality (290 rows)
- Category counts sum to total_count (no data loss)
- County events excluded (~25% of events)
- Rate calculation: (events / population) * 10000
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest


class TestMunicipalityAggregation:
    """Tests for the municipality aggregation SQL/pipeline."""

    @pytest.fixture(scope="class")
    def aggregated_data(self) -> list[dict[str, Any]]:
        """Load aggregated municipality events data."""
        parquet_path = Path("data/municipalities/events.parquet")
        if not parquet_path.exists():
            pytest.skip("Municipality events.parquet not found - run pipeline first")

        conn = duckdb.connect()
        result = conn.execute(f"""
            SELECT * FROM '{parquet_path}'
        """).fetchdf()
        conn.close()

        records: list[dict[str, Any]] = result.to_dict("records")
        return records

    @pytest.fixture(scope="class")
    def raw_events_count(self) -> dict[str, int]:
        """Count raw events by type (county vs municipality)."""
        events_path = Path("data/events.parquet")
        if not events_path.exists():
            pytest.skip("events.parquet not found")

        conn = duckdb.connect()
        result = conn.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE location_name LIKE '% län') AS county_events,
                COUNT(*) FILTER (WHERE location_name NOT LIKE '% län') AS municipality_events,
                COUNT(*) AS total_events
            FROM '{events_path}'
            WHERE type NOT LIKE 'Sammanfattning%'
        """).fetchone()
        conn.close()

        assert result is not None
        return {
            "county": result[0],
            "municipality": result[1],
            "total": result[2],
        }

    def test_output_has_290_municipalities(self, aggregated_data: list[dict[str, Any]]) -> None:
        """Output contains exactly 290 municipalities (one row each)."""
        assert len(aggregated_data) == 290

    def test_unique_kommun_codes(self, aggregated_data: list[dict[str, Any]]) -> None:
        """All kommun_kod values are unique."""
        codes = [row["kommun_kod"] for row in aggregated_data]
        assert len(codes) == len(set(codes))

    def test_category_counts_sum_to_total(self, aggregated_data: list[dict[str, Any]]) -> None:
        """Category counts sum to total_count for each municipality."""
        categories = [
            "traffic_count",
            "property_count",
            "violence_count",
            "narcotics_count",
            "fraud_count",
            "public_order_count",
            "weapons_count",
            "other_count",
        ]

        for row in aggregated_data:
            category_sum = sum(row[cat] for cat in categories)
            assert category_sum == row["total_count"], (
                f"Category sum {category_sum} != total_count {row['total_count']} "
                f"for {row['kommun_namn']}"
            )

    def test_county_events_excluded(
        self,
        aggregated_data: list[dict[str, Any]],
        raw_events_count: dict[str, int],
    ) -> None:
        """County-level events (ending in ' län') are excluded."""
        total_aggregated = sum(row["total_count"] for row in aggregated_data)

        assert total_aggregated == raw_events_count["municipality"], (
            f"Aggregated total {total_aggregated:,} != "
            f"expected municipality events {raw_events_count['municipality']:,}"
        )

    def test_population_present_for_all(self, aggregated_data: list[dict[str, Any]]) -> None:
        """All municipalities have population > 0."""
        for row in aggregated_data:
            assert row["population"] > 0, f"Zero population for {row['kommun_namn']}"

    def test_rate_calculation_correct(self, aggregated_data: list[dict[str, Any]]) -> None:
        """Rate per 10,000 calculated correctly."""
        for row in aggregated_data:
            if row["total_count"] > 0 and row["population"] > 0:
                expected_rate = (row["total_count"] / row["population"]) * 10000
                assert abs(row["rate_per_10000"] - expected_rate) < 0.001, (
                    f"Rate mismatch for {row['kommun_namn']}: "
                    f"got {row['rate_per_10000']}, expected {expected_rate:.4f}"
                )

    def test_has_required_columns(self, aggregated_data: list[dict[str, Any]]) -> None:
        """Output has all required columns."""
        required_columns = {
            "kommun_kod",
            "kommun_namn",
            "total_count",
            "traffic_count",
            "property_count",
            "violence_count",
            "narcotics_count",
            "fraud_count",
            "public_order_count",
            "weapons_count",
            "other_count",
            "type_counts",
            "population",
            "rate_per_10000",
        }

        actual_columns = set(aggregated_data[0].keys())
        missing = required_columns - actual_columns

        assert not missing, f"Missing columns: {missing}"


class TestAggregationFunction:
    """Tests for the aggregation function itself."""

    def test_aggregate_function_exists(self) -> None:
        """The aggregate_events_to_municipalities function exists."""
        from crimecity3k.municipality_processing import aggregate_events_to_municipalities

        assert callable(aggregate_events_to_municipalities)
