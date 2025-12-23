"""Tests for municipality tile generation.

Tests the critical invariants for Task 6.3:
- GeoJSONL output has 290 features with correct properties
- Properties include all required fields (kommun_kod, counts, rate, etc.)
- Geometries are valid Polygon/MultiPolygon
- PMTiles generation works with Tippecanoe
"""

import gzip
import json
from pathlib import Path
from typing import Any

import pytest


class TestMunicipalityGeoJSONExport:
    """Tests for exporting municipality data to GeoJSONL."""

    @pytest.fixture(scope="class")
    def geojsonl_output(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Generate GeoJSONL from municipality data."""
        from crimecity3k.municipality_tiles import export_municipalities_to_geojsonl

        boundaries_path = Path("data/municipalities/boundaries.geojson")
        events_path = Path("data/municipalities/events.parquet")

        if not boundaries_path.exists() or not events_path.exists():
            pytest.skip("Municipality data not found - run pipeline first")

        output_dir = tmp_path_factory.mktemp("tiles")
        output_path = output_dir / "municipalities.geojsonl.gz"

        export_municipalities_to_geojsonl(
            boundaries_file=boundaries_path,
            events_file=events_path,
            output_file=output_path,
        )

        return output_path

    @pytest.fixture(scope="class")
    def features(self, geojsonl_output: Path) -> list[dict[str, Any]]:
        """Parse all features from GeoJSONL output."""
        features = []
        with gzip.open(geojsonl_output, "rt", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    features.append(json.loads(line))
        return features

    def test_output_has_290_features(self, features: list[dict[str, Any]]) -> None:
        """GeoJSONL contains exactly 290 municipality features."""
        assert len(features) == 290

    def test_features_have_required_properties(self, features: list[dict[str, Any]]) -> None:
        """Each feature has all required properties for visualization."""
        required_props = {
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
            "population",
        }

        for feature in features:
            props = set(feature["properties"].keys())
            missing = required_props - props
            assert not missing, f"Missing properties: {missing}"

    def test_features_have_valid_geometry(self, features: list[dict[str, Any]]) -> None:
        """Each feature has valid Polygon or MultiPolygon geometry."""
        for feature in features:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
            assert "coordinates" in feature["geometry"]

    def test_kommun_codes_are_unique(self, features: list[dict[str, Any]]) -> None:
        """All kommun_kod values are unique."""
        codes = [f["properties"]["kommun_kod"] for f in features]
        assert len(codes) == len(set(codes))

    def test_counts_are_integers(self, features: list[dict[str, Any]]) -> None:
        """Count fields are integers."""
        count_fields = [
            "total_count",
            "traffic_count",
            "property_count",
            "violence_count",
            "narcotics_count",
            "fraud_count",
            "public_order_count",
            "weapons_count",
            "other_count",
            "population",
        ]
        for feature in features:
            for field in count_fields:
                value = feature["properties"][field]
                assert isinstance(value, int), f"{field} should be int, got {type(value)}"

    def test_file_is_gzip_compressed(self, geojsonl_output: Path) -> None:
        """Output file is gzip compressed."""
        with open(geojsonl_output, "rb") as f:
            magic = f.read(2)
        assert magic == b"\x1f\x8b", "File should be gzip compressed"


class TestMunicipalityPMTilesGeneration:
    """Tests for PMTiles generation from municipality GeoJSONL."""

    def test_municipality_pmtiles_command(self) -> None:
        """Command for municipality tiles includes correct parameters."""
        from crimecity3k.municipality_tiles import build_municipality_tippecanoe_command

        cmd = build_municipality_tippecanoe_command(
            input_file=Path("municipalities.geojsonl.gz"),
            output_file=Path("municipalities.pmtiles"),
        )

        assert cmd[0] == "tippecanoe"
        assert "-o" in cmd
        assert "municipalities.pmtiles" in cmd
        assert "--layer=municipalities" in cmd
        assert any("minimum-zoom" in arg for arg in cmd)
        assert any("maximum-zoom" in arg for arg in cmd)

    def test_municipality_zoom_levels(self) -> None:
        """Municipality tiles use appropriate zoom levels (3-10)."""
        from crimecity3k.municipality_tiles import build_municipality_tippecanoe_command

        cmd = build_municipality_tippecanoe_command(
            input_file=Path("in.geojsonl.gz"),
            output_file=Path("out.pmtiles"),
        )

        cmd_str = " ".join(cmd)
        assert "--minimum-zoom=3" in cmd_str
        assert "--maximum-zoom=10" in cmd_str

    @pytest.mark.skipif(
        not Path("/usr/bin/tippecanoe").exists() and not Path("/usr/local/bin/tippecanoe").exists(),
        reason="Tippecanoe not installed",
    )
    def test_generate_municipality_pmtiles(self, tmp_path: Path) -> None:
        """Integration test: generate PMTiles from municipality data."""
        from crimecity3k.municipality_tiles import (
            export_municipalities_to_geojsonl,
            generate_municipality_pmtiles,
        )

        boundaries_path = Path("data/municipalities/boundaries.geojson")
        events_path = Path("data/municipalities/events.parquet")

        if not boundaries_path.exists() or not events_path.exists():
            pytest.skip("Municipality data not found")

        geojsonl_path = tmp_path / "municipalities.geojsonl.gz"
        pmtiles_path = tmp_path / "municipalities.pmtiles"

        export_municipalities_to_geojsonl(
            boundaries_file=boundaries_path,
            events_file=events_path,
            output_file=geojsonl_path,
        )

        result = generate_municipality_pmtiles(
            input_file=geojsonl_path,
            output_file=pmtiles_path,
        )

        assert result.exists()
        assert result.stat().st_size > 0


class TestExportFunctionExists:
    """Tests that the export function exists and is callable."""

    def test_export_function_exists(self) -> None:
        """The export_municipalities_to_geojsonl function exists."""
        from crimecity3k.municipality_tiles import export_municipalities_to_geojsonl

        assert callable(export_municipalities_to_geojsonl)

    def test_pmtiles_function_exists(self) -> None:
        """The generate_municipality_pmtiles function exists."""
        from crimecity3k.municipality_tiles import generate_municipality_pmtiles

        assert callable(generate_municipality_pmtiles)

    def test_command_builder_exists(self) -> None:
        """The build_municipality_tippecanoe_command function exists."""
        from crimecity3k.municipality_tiles import build_municipality_tippecanoe_command

        assert callable(build_municipality_tippecanoe_command)
