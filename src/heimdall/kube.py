"""Listing the cluster (D101): namespaces and every Deployment, StatefulSet, DaemonSet and CronJob (D117).

List only - that is all heimdall-reads-cluster allows (Meru/meru rbac/) - with the pod's API token, re-read each call
(the kubelet renews it). Lists come in pages; any page that fails fails the whole look, so a scan is never sent
half-seen.
"""

from pathlib import Path

import httpx2
from pydantic import BaseModel, ConfigDict, Field

from heimdall.incoming import Incoming

PAGE = 500


class _Meta(Incoming):
    name: str
    namespace: str | None = None
    labels: dict[str, str] | None = None


class _Spec(Incoming):
    replicas: int | None = None
    suspend: bool | None = None  # CronJob


class _Status(Incoming):
    ready_replicas: int | None = Field(None, alias="readyReplicas")  # Deployment, StatefulSet; absent when 0
    number_ready: int | None = Field(None, alias="numberReady")  # DaemonSet


class _Object(Incoming):
    metadata: _Meta
    spec: _Spec | None = None
    status: _Status | None = None


class _ListMeta(Incoming):
    continue_: str | None = Field(None, alias="continue")


class _List(Incoming):
    metadata: _ListMeta
    items: list[_Object]


class Namespace(BaseModel):
    """A namespace and its labels."""

    model_config = ConfigDict(frozen=True)

    name: str
    labels: dict[str, str] = Field(default_factory=dict)


class Workload(BaseModel):
    """One Deployment, StatefulSet, DaemonSet or CronJob and how many of its pods are ready.

    A CronJob has no pod between runs, so its `ready` is 1 while it's scheduled (not suspended) and 0 when suspended -
    whether its runs succeed is Zabbix's CronJob check (D108).
    """

    model_config = ConfigDict(frozen=True)

    kind: str  # deployment | statefulset | daemonset | cronjob - Thoth's workload key part
    namespace: str
    name: str
    ready: int  # pods ready


KINDS = {
    "deployment": "/apis/apps/v1/deployments",
    "statefulset": "/apis/apps/v1/statefulsets",
    "daemonset": "/apis/apps/v1/daemonsets",
    "cronjob": "/apis/batch/v1/cronjobs",
}


def _ready(kind: str, spec: _Spec, status: _Status) -> int | None:
    """Pods ready - or, for a CronJob, 1 while it's scheduled."""
    if kind == "cronjob":
        return 0 if spec.suspend else 1
    return status.number_ready if kind == "daemonset" else status.ready_replicas


class Cluster(BaseModel):
    """Read-only lists from the Kubernetes API."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    http: httpx2.AsyncClient
    api_url: str
    token_file: Path

    async def _list(self, path: str) -> list[_Object]:
        found: list[_Object] = []
        params = {"limit": str(PAGE)}
        while True:
            response = await self.http.get(
                f"{self.api_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.token_file.read_text().strip()}"},
            )
            response.raise_for_status()
            page = _List.model_validate_json(response.content)
            found += page.items
            if not page.metadata.continue_:
                return found
            params = {"limit": str(PAGE), "continue": page.metadata.continue_}

    async def namespaces(self) -> list[Namespace]:
        """List every namespace."""
        return [
            Namespace(name=o.metadata.name, labels=o.metadata.labels or {})
            for o in await self._list("/api/v1/namespaces")
        ]

    async def workloads(self) -> list[Workload]:
        """List every workload of each kind in `KINDS`, in every namespace."""
        found = []
        for kind, path in KINDS.items():
            for o in await self._list(path):
                status = o.status or _Status()
                ready = _ready(kind, o.spec or _Spec(), status)
                found.append(
                    Workload(kind=kind, namespace=o.metadata.namespace or "", name=o.metadata.name, ready=ready or 0)
                )
        return found
