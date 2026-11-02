"""heimdall: Meru's scan worker - tells Thoth what really runs in the cluster"""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

app = FastAPI(title="heimdall")


@app.get("/heartbeat", response_class=PlainTextResponse)
def heartbeat() -> str:
    """Meru's liveness and readiness probes (nuwa-app's heartbeat.path) - add a /ready once there are dependencies."""
    return "ok"
