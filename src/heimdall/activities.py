"""The scan's two steps, as Temporal activities: look at the cluster, then report it to Thoth."""

import httpx2
from pydantic import BaseModel, ConfigDict
from temporalio import activity
from temporalio.exceptions import ApplicationError

from heimdall import thoth
from heimdall.kube import Cluster
from heimdall.snapshot import Snapshot, build
from heimdall.tokens import TokenSource


class Activities(BaseModel):
    """The activities, with what they need to reach the cluster and Thoth."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    cluster: Cluster
    cluster_name: str
    http: httpx2.AsyncClient
    thoth_url: str
    tokens: TokenSource

    @activity.defn
    async def look(self) -> Snapshot:
        """List the cluster and turn it into a snapshot."""
        snap = build(self.cluster_name, await self.cluster.namespaces(), await self.cluster.workloads())
        apps = sum(1 for i in snap.items if i.type == "app")
        activity.logger.info("saw %d apps, %d workloads", apps, len(snap.items) - apps)
        return snap

    @activity.defn
    async def report(self, scan_id: str, snap: Snapshot) -> dict:
        """Send the snapshot to Thoth; a refusal fails the run without a retry."""
        try:
            answers = await thoth.report(
                self.http, self.thoth_url, await self.tokens.get(), scan_id, self.cluster_name, snap
            )
        except thoth.RefusedError as e:  # the same snapshot would be refused again: fail the run, loudly
            raise ApplicationError(str(e), non_retryable=True) from e
        activity.logger.info("Thoth: %s", answers)
        return answers
