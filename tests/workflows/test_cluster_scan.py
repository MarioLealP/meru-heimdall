import json
import uuid
from pathlib import Path

import httpx2
import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from heimdall.activities.cluster_scan import Activities
from heimdall.clients.kube import Cluster
from heimdall.clients.tokens import TokenSource
from heimdall.core.snapshot import Item, Snapshot
from heimdall.workflows.cluster_scan import ClusterScan

SNAP = Snapshot(items=[Item(type="app", key="echo", name="echo")], relations=[])


@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter) as env:
        yield env


async def run(env: WorkflowEnvironment, report) -> dict:
    @activity.defn(name="look")
    async def look() -> Snapshot:
        return SNAP

    queue = f"q-{uuid.uuid4()}"
    async with Worker(env.client, task_queue=queue, workflows=[ClusterScan], activities=[look, report]):
        return await env.client.execute_workflow(ClusterScan.run, id=f"scan-{uuid.uuid4()}", task_queue=queue)


async def test_a_scan_reports_what_it_saw_under_its_run_id(env: WorkflowEnvironment) -> None:
    reports = []

    @activity.defn(name="report")
    async def report(scan_id: str, snap: Snapshot) -> dict:
        reports.append((scan_id, snap))
        if len(reports) == 1:
            raise RuntimeError("Thoth restarting")  # retried - as the same scan
        return {"items": {"created": 1}}

    assert await run(env, report) == {"items": {"created": 1}}
    assert reports[0] == reports[1]
    assert reports[0][0].startswith("k8s-")
    assert reports[0][1] == SNAP


async def test_a_refused_scan_fails_the_run_without_retrying(env: WorkflowEnvironment) -> None:
    tries = []

    @activity.defn(name="report")
    async def report(scan_id: str, snap: Snapshot) -> dict:
        tries.append(scan_id)
        raise ApplicationError("Thoth refused the items", non_retryable=True)

    with pytest.raises(WorkflowFailureError):
        await run(env, report)
    assert len(tries) == 1


async def test_the_real_activities_answer_to_their_names_on_a_worker(env: WorkflowEnvironment, tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("pod-token\n")
    reported = []

    def kubernetes(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=json.dumps({"metadata": {}, "items": []}))

    def outside(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token/":
            return httpx2.Response(200, json={"access_token": "t1"})
        reported.append((request.url.path, request.headers["authorization"]))
        return httpx2.Response(200, json={"created": 0})

    async with (
        httpx2.AsyncClient(transport=httpx2.MockTransport(kubernetes)) as kube,
        httpx2.AsyncClient(transport=httpx2.MockTransport(outside)) as http,
    ):
        activities = Activities(
            cluster=Cluster(http=kube, api_url="https://k8s", token_file=token_file),
            cluster_name="clockmost",
            http=http,
            thoth_url="http://thoth",
            tokens=TokenSource(http=http, token_url="https://auth/token/", client_id="thoth", token_file=token_file),
        )
        queue = f"q-{uuid.uuid4()}"
        async with Worker(
            env.client, task_queue=queue, workflows=[ClusterScan], activities=[activities.look, activities.report]
        ):
            answers = await env.client.execute_workflow(ClusterScan.run, id=f"scan-{uuid.uuid4()}", task_queue=queue)

    assert answers == {"items": {"created": 0}, "relations": {"created": 0}}
    assert [call[1] for call in reported] == ["Bearer t1", "Bearer t1"]
