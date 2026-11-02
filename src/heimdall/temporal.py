"""Heimdall's Temporal connection - mTLS + an Authentik token swapped before it expires (D70) - and its Schedule."""

import asyncio

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import TLSConfig

from heimdall.config import Settings
from heimdall.tokens import EARLY, TokenSource
from heimdall.workflows import ClusterScan

REFRESH_EVERY = EARLY // 2  # look more often than the renewal window is long (see Shikigami's temporal.py)
SCHEDULE_ID = "cluster-scan"


async def connect(settings: Settings, tokens: TokenSource) -> Client:
    tls = settings.tls_dir
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        api_key=await tokens.get(),  # sent as "authorization: Bearer <token>"
        tls=TLSConfig(
            server_root_ca_cert=(tls / "ca.crt").read_bytes(),
            client_cert=(tls / "tls.crt").read_bytes(),
            client_private_key=(tls / "tls.key").read_bytes(),
            domain=settings.temporal_server_name,
        ),
        data_converter=pydantic_data_converter,
    )


async def keep_token_fresh(client: Client, tokens: TokenSource) -> None:
    while True:
        await asyncio.sleep(REFRESH_EVERY)
        client.api_key = await tokens.get()


def schedule(settings: Settings) -> Schedule:
    """Every `scan_every`; a scan still running when the next is due makes that one skip, never pile up."""
    return Schedule(
        action=ScheduleActionStartWorkflow(
            ClusterScan.run,
            id=SCHEDULE_ID,
            task_queue=settings.task_queue,
            execution_timeout=settings.scan_every,
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=settings.scan_every)]),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )


async def ensure_schedule(client: Client, settings: Settings) -> None:
    """Create the Schedule, or bring an existing one in line with this version (interval, workflow)."""
    wanted = schedule(settings)
    try:
        await client.create_schedule(SCHEDULE_ID, wanted)
    except ScheduleAlreadyRunningError:

        def update(_: ScheduleUpdateInput) -> ScheduleUpdate:
            return ScheduleUpdate(schedule=wanted)

        await client.get_schedule_handle(SCHEDULE_ID).update(update)
