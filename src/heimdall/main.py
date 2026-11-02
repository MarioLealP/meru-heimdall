"""One process per pod: the Temporal worker that runs the scans, and the probes beside it."""

import asyncio
import logging
import ssl

import httpx2
import uvicorn
from temporalio.worker import Worker

from heimdall.activities import Activities
from heimdall.app import make_app
from heimdall.config import Settings
from heimdall.kube import Cluster
from heimdall.temporal import connect, ensure_schedule, keep_token_fresh
from heimdall.tokens import TokenSource
from heimdall.workflows import ClusterScan


async def run() -> None:
    settings = Settings()  # the secret comes from the environment
    cluster_ca = ssl.create_default_context(cafile=settings.kubernetes_dir / "ca.crt")
    async with httpx2.AsyncClient(timeout=30) as http, httpx2.AsyncClient(timeout=30, verify=cluster_ca) as kube:

        def tokens(client_id: str) -> TokenSource:
            return TokenSource(
                http, settings.token_url, client_id, settings.authentik_username, settings.authentik_password
            )

        temporal_tokens = tokens(settings.temporal_client_id)
        client = await connect(settings, temporal_tokens)
        await ensure_schedule(client, settings)
        cluster = Cluster(kube, settings.kubernetes_url, settings.kubernetes_dir / "token")
        activities = Activities(cluster, settings.cluster, http, settings.thoth_url, tokens(settings.thoth_client_id))
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
