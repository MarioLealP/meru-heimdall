"""The scan's two steps, as Temporal activities: look at the cluster, then report it to Thoth."""

import httpx2
from temporalio import activity
from temporalio.exceptions import ApplicationError

from heimdall import thoth
from heimdall.kube import Cluster
from heimdall.snapshot import Snapshot, build
from heimdall.tokens import TokenSource


class Activities:
    def __init__(self, cluster: Cluster, name: str, http: httpx2.AsyncClient, thoth_url: str, tokens: TokenSource):
        self._cluster, self._name = cluster, name
        self._http, self._thoth_url, self._tokens = http, thoth_url, tokens

    @activity.defn
    async def look(self) -> Snapshot:
        snap = build(self._name, await self._cluster.namespaces(), await self._cluster.workloads())
        apps = sum(1 for i in snap.items if i.type == "app")
        activity.logger.info("saw %d apps, %d workloads", apps, len(snap.items) - apps)
        return snap

    @activity.defn
    async def report(self, scan_id: str, snap: Snapshot) -> dict:
        try:
            answers = await thoth.report(
                self._http, self._thoth_url, await self._tokens.get(), scan_id, self._name, snap
            )
        except thoth.Refused as e:  # the same snapshot would be refused again: fail the run, loudly
            raise ApplicationError(str(e), non_retryable=True) from e
        activity.logger.info("Thoth: %s", answers)
        return answers
