"""heimdall's HTTP side: only the probes. The scanning is the Temporal worker's (main.py)."""

from fastapi import FastAPI, HTTPException
from temporalio.client import Client


def make_app(client: Client) -> FastAPI:
    app = FastAPI(title="heimdall", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/heartbeat")
    async def heartbeat() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        # Temporal's own health check needs no token; it proves the TLS connection works.
        try:
            healthy = await client.service_client.check_health()
        except Exception as e:
            raise HTTPException(503, f"Temporal unreachable: {type(e).__name__}") from e
        if not healthy:
            raise HTTPException(503, "Temporal not serving")
        return {"status": "ready"}

    return app
