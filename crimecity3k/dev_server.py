"""Development server with HTTP Range request support for PMTiles.

Python's built-in http.server doesn't support Range requests, which PMTiles
requires for efficient tile fetching. This module provides a Starlette-based
server that properly supports byte-range requests.

Usage:
    python -m crimecity3k.dev_server [--port 8080]
    # Or via make:
    make serve
"""

import argparse
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles


def create_app(
    root_dir: Path | None = None,
    tiles_dir: Path | None = None,
) -> Starlette:
    """Create Starlette app serving static files with Range support.

    Args:
        root_dir: Directory containing static/ folder. Defaults to project root.
        tiles_dir: Directory containing PMTiles. Defaults to root_dir/data/tiles/pmtiles.
                   Served at /data/tiles/pmtiles/ to match frontend expectations.

    Returns:
        Configured Starlette application
    """
    if root_dir is None:
        # Default to project root (parent of crimecity3k package)
        root_dir = Path(__file__).parent.parent

    if tiles_dir is None:
        tiles_dir = root_dir / "data" / "tiles" / "pmtiles"

    app = Starlette(
        routes=[
            # Serve static/ directory at /static/
            Mount("/static", StaticFiles(directory=root_dir / "static"), name="static"),
            # Serve PMTiles at expected path
            Mount(
                "/data/tiles/pmtiles",
                StaticFiles(directory=tiles_dir),
                name="tiles",
            ),
            # Serve rest of data/ directory (for other data files if needed)
            Mount("/data", StaticFiles(directory=root_dir / "data"), name="data"),
        ]
    )

    return app


def main() -> None:
    """Run the development server."""
    parser = argparse.ArgumentParser(description="CrimeCity3K development server")
    parser.add_argument(
        "--port", "-p", type=int, default=8080, help="Port to serve on (default: 8080)"
    )
    parser.add_argument(
        "--host", "-H", type=str, default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    args = parser.parse_args()

    print("Starting CrimeCity3K development server...")
    print(f"View at: http://{args.host}:{args.port}/static/index.html")
    print("Press Ctrl+C to stop\n")

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
