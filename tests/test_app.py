from unittest.mock import AsyncMock, MagicMock

import httpx2
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from heimdall.app import make_app


def client(check_health: AsyncMock) -> MagicMock:
    fake = MagicMock(spec=Client)
    fake.service_client.check_health = check_health
    return fake


async def get(check_health: AsyncMock, path: str) -> httpx2.Response:
    app = make_app(client(check_health))
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://heimdall") as http:
        return await http.get(path)


async def test_the_heartbeat_needs_nothing_else() -> None:
    response = await get(AsyncMock(side_effect=AssertionError("not called")), "/heartbeat")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


async def test_ready_when_temporal_answers() -> None:
    response = await get(AsyncMock(return_value=True), "/ready")
    assert (response.status_code, response.json()) == (200, {"status": "ready"})


async def test_not_ready_when_temporal_is_not_serving() -> None:
    response = await get(AsyncMock(return_value=False), "/ready")
    assert (response.status_code, response.json()) == (503, {"detail": "Temporal not serving"})


async def test_not_ready_when_temporal_cannot_be_reached() -> None:
    failure = RPCError("connection refused", RPCStatusCode.UNAVAILABLE, b"")
    response = await get(AsyncMock(side_effect=failure), "/ready")
    assert (response.status_code, response.json()) == (503, {"detail": "Temporal unreachable: RPCError"})
