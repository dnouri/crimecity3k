"""Tests for PMTiles generation with Tippecanoe.

These tests verify the PMTiles generation pipeline for crime map tiles.
Following aviation-anomaly patterns for Tippecanoe integration.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


def test_get_zoom_range_for_resolution() -> None:
    """Test zoom range calculation based on H3 resolution.

    Maps H3 resolution to appropriate Mapbox zoom levels:
    - r4 (coarse, ~25km) -> z4-8
    - r5 (medium, ~8km) -> z5-9
    - r6 (fine, ~3km) -> z6-10
    """
    from crimecity3k.pmtiles import get_zoom_range_for_resolution

    assert get_zoom_range_for_resolution(4) == (4, 8)
    assert get_zoom_range_for_resolution(5) == (5, 9)
    assert get_zoom_range_for_resolution(6) == (6, 10)


def test_build_tippecanoe_command() -> None:
    """Test Tippecanoe command construction with expected flags."""
    from crimecity3k.pmtiles import build_tippecanoe_command

    cmd = build_tippecanoe_command(
        input_file=Path("input.geojsonl.gz"),
        output_file=Path("output.pmtiles"),
        min_zoom=5,
        max_zoom=9,
    )

    # Core command structure
    assert cmd[0] == "tippecanoe"
    assert "-o" in cmd
    assert "output.pmtiles" in cmd

    # Zoom levels
    assert "--minimum-zoom=5" in cmd
    assert "--maximum-zoom=9" in cmd

    # Input file last
    assert cmd[-1] == "input.geojsonl.gz"

    # Performance flags
    cmd_str = " ".join(cmd)
    assert "--drop-densest-as-needed" in cmd_str
    assert "--force" in cmd_str


def test_build_tippecanoe_command_with_attributes() -> None:
    """Test command includes attribute preservation for filtering."""
    from crimecity3k.pmtiles import build_tippecanoe_command

    cmd = build_tippecanoe_command(
        input_file=Path("input.geojsonl.gz"),
        output_file=Path("output.pmtiles"),
        min_zoom=5,
        max_zoom=9,
        preserve_attributes=["total_count", "traffic_count", "rate_per_10000"],
    )

    cmd_str = " ".join(cmd)
    assert "--include total_count" in cmd_str
    assert "--include traffic_count" in cmd_str
    assert "--include rate_per_10000" in cmd_str


def test_build_tippecanoe_command_geojsonl_parallel() -> None:
    """Test -P flag added for GeoJSONL input (parallel parsing)."""
    from crimecity3k.pmtiles import build_tippecanoe_command

    # GeoJSONL file gets -P flag
    cmd_gz = build_tippecanoe_command(
        input_file=Path("input.geojsonl.gz"),
        output_file=Path("output.pmtiles"),
        min_zoom=5,
        max_zoom=9,
    )
    assert "-P" in cmd_gz

    # Regular GeoJSON does not
    cmd_json = build_tippecanoe_command(
        input_file=Path("input.geojson"),
        output_file=Path("output.pmtiles"),
        min_zoom=5,
        max_zoom=9,
    )
    assert "-P" not in cmd_json


def test_check_tippecanoe_installed() -> None:
    """Test checking for Tippecanoe availability."""
    from crimecity3k.pmtiles import check_tippecanoe_installed

    with patch("subprocess.run") as mock_run:
        # Simulate Tippecanoe installed
        mock_run.return_value = Mock(returncode=0)
        assert check_tippecanoe_installed() is True

        # Simulate Tippecanoe not installed
        mock_run.side_effect = FileNotFoundError
        assert check_tippecanoe_installed() is False


def test_generate_pmtiles_tippecanoe_not_installed(tmp_path: Path) -> None:
    """Test graceful failure when Tippecanoe not installed."""
    from crimecity3k.pmtiles import generate_pmtiles

    input_file = tmp_path / "input.geojsonl.gz"
    output_file = tmp_path / "output.pmtiles"

    # Create minimal GeoJSONL
    import gzip

    with gzip.open(input_file, "wt") as f:
        f.write('{"type":"Feature","geometry":null,"properties":{}}\n')

    with patch("crimecity3k.pmtiles.check_tippecanoe_installed", return_value=False):
        with pytest.raises(RuntimeError, match="Tippecanoe is not installed"):
            generate_pmtiles(input_file, output_file, resolution=5)


def test_generate_pmtiles_missing_input(tmp_path: Path) -> None:
    """Test error on missing input file."""
    from crimecity3k.pmtiles import generate_pmtiles

    input_file = tmp_path / "nonexistent.geojsonl.gz"
    output_file = tmp_path / "output.pmtiles"

    with pytest.raises(FileNotFoundError):
        generate_pmtiles(input_file, output_file, resolution=5)


def test_generate_pmtiles_success(tmp_path: Path) -> None:
    """Test successful PMTiles generation (mocked)."""
    from crimecity3k.pmtiles import generate_pmtiles

    input_file = tmp_path / "input.geojsonl.gz"
    output_file = tmp_path / "output.pmtiles"

    # Create minimal GeoJSONL with one feature
    import gzip

    feature = json.dumps(
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[18.0, 59.3], [18.1, 59.3], [18.1, 59.4], [18.0, 59.4], [18.0, 59.3]]
                ],
            },
            "properties": {
                "h3_cell": "85088663fffffff",
                "total_count": 10,
                "traffic_count": 5,
                "rate_per_10000": 100.0,
            },
        }
    )
    with gzip.open(input_file, "wt") as f:
        f.write(feature + "\n")

    with patch("crimecity3k.pmtiles.check_tippecanoe_installed", return_value=True):
        with patch("subprocess.run") as mock_run:
            # Simulate successful Tippecanoe execution
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            # Create fake output so stat() works
            output_file.write_bytes(b"fake pmtiles content")

            result = generate_pmtiles(input_file, output_file, resolution=5)

            assert result == output_file
            mock_run.assert_called_once()

            # Verify command structure
            cmd = mock_run.call_args[0][0]
            assert "tippecanoe" in cmd[0]


def test_generate_pmtiles_preserves_crime_attributes(tmp_path: Path) -> None:
    """Test that crime statistics attributes are in preserve list."""
    from crimecity3k.pmtiles import generate_pmtiles

    input_file = tmp_path / "input.geojsonl.gz"
    output_file = tmp_path / "output.pmtiles"

    import gzip

    feature = json.dumps(
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[18.0, 59.3], [18.1, 59.3], [18.1, 59.4], [18.0, 59.4], [18.0, 59.3]]
                ],
            },
            "properties": {
                "h3_cell": "85088663fffffff",
                "total_count": 10,
                "traffic_count": 5,
                "property_count": 2,
                "violence_count": 1,
                "rate_per_10000": 100.0,
            },
        }
    )
    with gzip.open(input_file, "wt") as f:
        f.write(feature + "\n")

    with patch("crimecity3k.pmtiles.check_tippecanoe_installed", return_value=True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            output_file.write_bytes(b"fake pmtiles")

            generate_pmtiles(input_file, output_file, resolution=5)

            # Verify key attributes are preserved
            cmd = mock_run.call_args[0][0]
            cmd_str = " ".join(cmd)

            assert "--include h3_cell" in cmd_str
            assert "--include total_count" in cmd_str
            assert "--include rate_per_10000" in cmd_str


@pytest.mark.integration
@pytest.mark.skipif(
    subprocess.run(["which", "tippecanoe"], capture_output=True).returncode != 0,
    reason="Tippecanoe not installed",
)
def test_generate_pmtiles_integration(tmp_path: Path) -> None:
    """Integration test with actual Tippecanoe (if installed)."""
    from crimecity3k.pmtiles import generate_pmtiles

    input_file = tmp_path / "test.geojsonl.gz"
    output_file = tmp_path / "test.pmtiles"

    # Create valid GeoJSONL
    import gzip

    feature = json.dumps(
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[18.0, 59.3], [18.1, 59.3], [18.1, 59.4], [18.0, 59.4], [18.0, 59.3]]
                ],
            },
            "properties": {
                "h3_cell": "85088663fffffff",
                "total_count": 100,
                "traffic_count": 50,
                "rate_per_10000": 1000.0,
            },
        }
    )
    with gzip.open(input_file, "wt") as f:
        f.write(feature + "\n")

    # Generate PMTiles
    result = generate_pmtiles(input_file, output_file, resolution=5)

    # Verify output exists and has content
    assert result.exists()
    assert result.stat().st_size > 0
