"""DuckDB connection management with configuration."""

import duckdb

from crimecity3k.config import Config


def create_configured_connection(
    config: Config,
    extensions: list[str] | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create DuckDB connection with standard configuration.

    Applies memory limits, threading, and loads extensions.

    Args:
        config: Configuration object
        extensions: Optional list of extensions to load (e.g., ["h3", "spatial"])

    Returns:
        Configured DuckDB connection

    Example:
        >>> from crimecity3k.config import Config
        >>> config = Config.from_file("config.toml")
        >>> conn = create_configured_connection(config, extensions=["h3", "spatial"])
        >>> result = conn.execute("SELECT h3_latlng_to_cell(59.3293, 18.0686, 5)").fetchone()
    """
    conn = duckdb.connect()

    # Apply DuckDB settings from config
    conn.execute(f"SET memory_limit = '{config.duckdb.memory_limit}'")
    conn.execute(f"SET threads = {config.duckdb.threads}")
    conn.execute(f"SET temp_directory = '{config.duckdb.temp_directory}'")
    conn.execute(f"SET max_temp_directory_size = '{config.duckdb.max_temp_directory_size}'")

    # Enable progress bar for long operations
    conn.execute("SET enable_progress_bar = true")
    conn.execute("SET enable_progress_bar_print = true")

    # Load extensions
    if extensions:
        # Core extensions (built-in): spatial, json, etc.
        # Community extensions: h3
        core_extensions = {"spatial", "json", "parquet", "httpfs"}

        for ext in extensions:
            try:
                if ext in core_extensions:
                    # Core extensions: install without FROM community
                    conn.execute(f"INSTALL {ext}")
                else:
                    # Community extensions
                    conn.execute(f"INSTALL {ext} FROM community")
                conn.execute(f"LOAD {ext}")
            except Exception:
                # If install fails, try to just load (may already be installed)
                try:
                    conn.execute(f"LOAD {ext}")
                except Exception:
                    # If load also fails, re-raise the original install error
                    raise

    return conn
