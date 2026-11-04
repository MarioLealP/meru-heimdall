import json

import httpx2
import pytest

from heimdall import thoth
from heimdall.snapshot import End, Item, Relation, Snapshot

SNAP = Snapshot(
    items=[
        Item(type="app", key="echo", name="echo"),
        Item(type="workload", key="clockmost/echo/deployment/echo", name="echo"),
    ],
    relations=[
        Relation(
            type="part-of",
            from_=End(type="workload", key="clockmost/echo/deployment/echo"),
            to=End(type="app", key="echo"),
        )
    ],
)


async def test_items_then_links_under_one_scan_id() -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append((request.method, request.url.path, request.headers["authorization"], json.loads(request.content)))
        return httpx2.Response(200, json={"created": 0})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        await thoth.report(http, "http://thoth", "tok", "k8s-run1", "clockmost", SNAP)
    assert [c[:3] for c in calls] == [
        ("PUT", "/v1/scans/k8s-run1/k8s-scan/clockmost/items", "Bearer tok"),
        ("PUT", "/v1/scans/k8s-run1/k8s-scan/clockmost/relations", "Bearer tok"),
    ]
    assert calls[0][3]["items"][0] == {"type": "app", "key": "echo", "name": "echo", "attributes": {}}
    assert calls[1][3]["relations"][0]["from"] == {"type": "workload", "key": "clockmost/echo/deployment/echo"}


async def test_a_refused_snapshot_says_why_and_sends_no_links() -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.url.path)
        return httpx2.Response(422, json={"errors": [{"msg": "items[0] (app stray): not declared"}]})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
        with pytest.raises(thoth.RefusedError, match="not declared"):
            await thoth.report(http, "http://thoth", "tok", "k8s-run1", "clockmost", SNAP)
    assert calls == ["/v1/scans/k8s-run1/k8s-scan/clockmost/items"]
