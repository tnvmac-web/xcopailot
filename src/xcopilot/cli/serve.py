from __future__ import annotations

import click
import uvicorn


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8001, type=int, show_default=True)
@click.option("--reload/--no-reload", default=False)
def serve(host: str, port: int, reload: bool) -> None:
    """Run the X-Copilot API server."""
    uvicorn.run("server.main:app", host=host, port=port, reload=reload)
