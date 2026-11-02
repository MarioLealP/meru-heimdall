import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from heimdall.snapshot import Item, Snapshot
from heimdall.workflows import ClusterScan

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
    assert reports[0][0].startswith("k8s-") and reports[0][1] == SNAP


async def test_a_refused_scan_fails_the_run_without_retrying(env: WorkflowEnvironment) -> None:
    tries = []

    @activity.defn(name="report")
    async def report(scan_id: str, snap: Snapshot) -> dict:
        tries.append(scan_id)
        raise ApplicationError("Thoth refused the items", non_retryable=True)

    with pytest.raises(WorkflowFailureError):
        await run(env, report)
    assert len(tries) == 1
