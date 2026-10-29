"""Run the backend for development, and start it again whenever its code or prepared data changes.

uvicorn's own --reload is not used: on Windows it stops the old server with a console Ctrl+C, which
also stops everything else started from the same window, the frontend and the launcher included.

Usage: uv run python backend/scripts/dev_server.py [port]
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from watchfiles import run_process

BACKEND = Path(__file__).resolve().parents[1]
# Rasters are left out: they are large, and are opened from disk on each request anyway.
WATCHED = [
    BACKEND / "csa_portal", BACKEND / "data", BACKEND / "boundaries", BACKEND / "catalogue.json",
    BACKEND / "forecast_layers.json",
]


def serve(port: int) -> None:
    # 0.0.0.0 so other machines on the same network can reach the API.
    uvicorn.run(
        "csa_portal.main:create_app", factory=True, app_dir=str(BACKEND), host="0.0.0.0", port=port
    )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9988
    run_process(*[path for path in WATCHED if path.exists()], target=serve, args=(port,))
