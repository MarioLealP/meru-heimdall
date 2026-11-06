"""One process per pod: the Temporal worker that runs the scans, and the probes beside it."""

import asyncio
import logging
import ssl

import httpx2
import sentry_sdk
import uvicorn
from temporalio.worker import Worker

from heimdall.activities.cluster_scan import Activities
from heimdall.api.app import make_app
from heimdall.clients.kube import Cluster
from heimdall.clients.temporal import connect, ensure_schedule, keep_token_fresh
from heimdall.clients.tokens import TokenSource
from heimdall.config import Settings
from heimdall.workflows.cluster_scan import ClusterScan


async def run() -> None:
    """Connect, make sure the Schedule exists, then run the worker and the probes until one stops."""
    settings = Settings()  # the secret comes from the environment
    cluster_ca = ssl.create_default_context(cafile=settings.kubernetes_dir / "ca.crt")
    async with httpx2.AsyncClient(timeout=30) as http, httpx2.AsyncClient(timeout=30, verify=cluster_ca) as kube:

        def tokens(client_id: str) -> TokenSource:
            return TokenSource(
                http=http,
                token_url=settings.token_url,
                client_id=client_id,
                token_file=settings.authentik_token_file,
            )

        temporal_tokens = tokens(settings.temporal_client_id)
        client = await connect(settings, temporal_tokens)
        await ensure_schedule(client, settings)
        cluster = Cluster(http=kube, api_url=settings.kubernetes_url, token_file=settings.kubernetes_dir / "token")
        activities = Activities(
            cluster=cluster,
            cluster_name=settings.cluster,
            http=http,
            thoth_url=settings.thoth_url,
            tokens=tokens(settings.thoth_client_id),
        )
        worker = Worker(
            client,
            task_queue=settings.task_queue,
            workflows=[ClusterScan],
            activities=[activities.look, activities.report],
        )
        server = uvicorn.Server(uvicorn.Config(make_app(client), host="0.0.0.0", port=settings.http_port))
        async with asyncio.TaskGroup() as group:
            group.create_task(keep_token_fresh(client, temporal_tokens))
            group.create_task(worker.run())
            group.create_task(server.serve())


def main() -> None:
    """Set up logging and run the pod's process."""
    # Crash reports to GlitchTip (D125): SENTRY_DSN comes from nuwa-app's glitchtip.dsn; unset, the SDK stays off.
    # No local variables or request bodies in a report - either can hold a secret.
    sentry_sdk.init(include_local_variables=False, max_request_body_size="never")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
