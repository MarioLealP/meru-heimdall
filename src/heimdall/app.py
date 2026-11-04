"""heimdall's HTTP side: only the probes. The scanning is the Temporal worker's (main.py)."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from temporalio.client import Client
from temporalio.service import RPCError


class Probe(BaseModel):
    """A probe's answer."""

    model_config = ConfigDict(frozen=True)

    status: str


def make_app(client: Client) -> FastAPI:
    """Build the probes' app; `/ready` asks the given Temporal client."""
    app = FastAPI(title="heimdall", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/heartbeat", status_code=200)
    async def heartbeat() -> Probe:
        return Probe(status="ok")

    @app.get("/ready", status_code=200, responses={503: {"description": "Temporal is unreachable or not serving"}})
    async def ready() -> Probe:
        # Temporal's own health check needs no token; it proves the TLS connection works.
        try:
            healthy = await client.service_client.check_health()
        except RPCError as e:  # every failure of the call itself: no connection, TLS, a gRPC error status
            raise HTTPException(503, f"Temporal unreachable: {type(e).__name__}") from e
        if not healthy:
            raise HTTPException(503, "Temporal not serving")
        return Probe(status="ready")

    return app
