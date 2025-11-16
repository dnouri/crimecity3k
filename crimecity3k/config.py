"""Configuration management with Pydantic validation."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class AggregationConfig(BaseModel):
    """Configuration for H3 aggregation."""

    resolutions: list[int] = Field(default=[4, 5, 6])
    min_population_threshold: int = Field(default=100)

    @field_validator("resolutions")
    @classmethod
    def validate_resolutions(cls, v: list[int]) -> list[int]:
        """Ensure resolutions are valid H3 values."""
        if not all(4 <= r <= 6 for r in v):
            raise ValueError("Resolutions must be between 4 and 6")
        return v


class DuckDBConfig(BaseModel):
    """Configuration for DuckDB execution."""

    memory_limit: str = Field(default="4GB")
    threads: int = Field(default=2)
    temp_directory: str = Field(default="/tmp/duckdb")
    max_temp_directory_size: str = Field(default="50GB")


class ExportConfig(BaseModel):
    """Configuration for data export."""

    geojson_compression: bool = Field(default=True)
    pmtiles_max_zoom: int = Field(default=10)


class Config(BaseModel):
    """Main configuration."""

    data_dir: Path = Field(default=Path("data"))
    aggregation: AggregationConfig = Field(default_factory=AggregationConfig)
    duckdb: DuckDBConfig = Field(default_factory=DuckDBConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)

    @classmethod
    def from_file(cls, path: Path | str) -> "Config":
        """Load configuration from TOML file.

        Args:
            path: Path to config.toml file

        Returns:
            Validated Config object

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config validation fails
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls(**data)
