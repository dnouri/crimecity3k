"""Tests for municipality data download and validation.

Tests the critical invariants for Phase 6:
- Exactly 290 Swedish municipalities in boundary data
- Population data for all 290 municipalities
- All event location_names (excluding counties) match municipalities
"""

from pathlib import Path

import pytest

# Mark as requiring network access for CI configuration
pytestmark = pytest.mark.network


class TestMunicipalityBoundaries:
    """Tests for municipality GeoJSON boundary data."""

    def test_geojson_has_290_features(self, municipality_geojson: dict) -> None:
        """GeoJSON contains exactly 290 Swedish municipalities."""
        assert len(municipality_geojson["features"]) == 290

    def test_geojson_has_required_properties(self, municipality_geojson: dict) -> None:
        """Each feature has kommun_kod, kommun_namn, and geometry."""
        for feature in municipality_geojson["features"]:
            props = feature["properties"]
            assert "id" in props, "Missing kommun_kod (id)"
            assert "kom_namn" in props, "Missing kommun_namn"
            assert len(props["id"]) == 4, f"Invalid kommun_kod: {props['id']}"
            assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")

    def test_geojson_has_unique_kommun_codes(self, municipality_geojson: dict) -> None:
        """All kommun_kod values are unique."""
        codes = [f["properties"]["id"] for f in municipality_geojson["features"]]
        assert len(codes) == len(set(codes))


class TestMunicipalityPopulation:
    """Tests for SCB population data."""

    def test_population_csv_has_290_rows(self, population_data: list[dict]) -> None:
        """Population data contains exactly 290 municipalities."""
        assert len(population_data) == 290

    def test_population_data_has_required_fields(self, population_data: list[dict]) -> None:
        """Each row has kommun_kod, kommun_namn, and population."""
        for row in population_data:
            assert "kommun_kod" in row
            assert "kommun_namn" in row
            assert "population" in row
            assert isinstance(row["population"], int)
            assert row["population"] > 0

    def test_population_total_reasonable(self, population_data: list[dict]) -> None:
        """Total population is approximately Sweden's population (~10.5 million)."""
        total = sum(row["population"] for row in population_data)
        assert 10_000_000 < total < 11_500_000, f"Total population {total:,} seems wrong"


class TestNameMatching:
    """Tests for matching event location_names to municipalities."""

    def test_all_event_locations_match_municipalities(
        self,
        municipality_geojson: dict,
        event_location_names: set[str],
    ) -> None:
        """Every municipality-level event location matches a municipality."""
        from crimecity3k.municipality_data import normalize_name

        geojson_names = {
            normalize_name(f["properties"]["kom_namn"]) for f in municipality_geojson["features"]
        }

        # Filter to municipality-level events (exclude "* län")
        municipality_locations = {
            normalize_name(loc) for loc in event_location_names if not loc.endswith(" län")
        }

        unmatched = municipality_locations - geojson_names
        assert not unmatched, f"Unmatched locations: {unmatched}"

    def test_normalize_name_handles_case_differences(self) -> None:
        """Name normalization handles known case differences."""
        from crimecity3k.municipality_data import normalize_name

        # These are the 5 known case differences from spike
        test_cases = [
            ("Dals-Ed", "dals-ed"),
            ("Dals-ed", "dals-ed"),
            ("Lilla Edet", "lilla edet"),
            ("Lilla edet", "lilla edet"),
            ("Upplands Väsby", "upplands väsby"),
            ("Upplands väsby", "upplands väsby"),
        ]
        for input_name, expected in test_cases:
            assert normalize_name(input_name) == expected


# Fixtures that will be provided by conftest.py or this module


@pytest.fixture(scope="module")
def municipality_geojson() -> dict:
    """Load or download municipality GeoJSON."""
    from crimecity3k.municipality_data import download_municipality_boundaries

    data = download_municipality_boundaries()
    return data


@pytest.fixture(scope="module")
def population_data() -> list[dict]:
    """Load or download population data from SCB."""
    from crimecity3k.municipality_data import download_population_data

    return download_population_data()


@pytest.fixture(scope="module")
def event_location_names() -> set[str]:
    """Get all unique location_names from events data."""
    import duckdb

    events_path = Path("data/events.parquet")
    if not events_path.exists():
        pytest.skip("events.parquet not found")

    conn = duckdb.connect()
    result = conn.execute(f"""
        SELECT DISTINCT location_name
        FROM '{events_path}'
        WHERE location_name IS NOT NULL
    """).fetchall()
    conn.close()

    return {r[0] for r in result}
