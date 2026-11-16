"""What one look at the cluster tells Thoth (D100, D101), as a pure function of what was listed.

- Every Deployment, StatefulSet, DaemonSet and CronJob is a `workload` item, keyed
  `<cluster>/<namespace>/<kind>/<name>`. The cluster scan owns no workload fields yet, so it only says "seen".
- A Meru app is seen when its own namespace (the one named like the app, labelled `meru.clockmost.com/app: <name>`)
  has a Deployment with a ready pod, or a CronJob that isn't suspended (D117: Charon, Anubis) - `running: true`.
  Also seen, `running: false`, when the only thing there is a Deployment scaled to 0 on purpose (a game server
  between sessions): Thoth calls it stopped. A Deployment that wants pods but has none ready isn't seen - that's a
  broken app, not a stopped one.
- A host binary (`workload: false`: nothing of it runs in k3s) is seen once the host has installed a signed release:
  the host's installer labels the app's namespaces `meru.clockmost.com/host-binary: installed` after the binary
  passed its checks. `running: null` - the cluster can't see the host process. Without the label it stays planned, so
  a stuck onboarding still shows.
- Only a confirm, every time: Thoth refuses an app Shikigami never declared (D100).
- Every workload in a namespace labelled for an app - its build namespace too - is `part-of` that app (D55).
"""

from pydantic import BaseModel, ConfigDict, Field

from heimdall.clients.kube import Namespace, Workload

APP_LABEL = "meru.clockmost.com/app"
APP_KINDS = {"deployment", "cronjob"}  # what an app runs as; a StatefulSet alone is its database, not the app
HOST_BINARY_LABEL = "meru.clockmost.com/host-binary"
INSTALLED = "installed"


class Item(BaseModel):
    """One thing Thoth is told was seen."""

    model_config = ConfigDict(frozen=True)

    type: str
    key: str
    name: str
    attributes: dict[str, str | bool | None] = Field(default_factory=dict)


class End(BaseModel):
    """One end of a relation, named by the item's type and key."""

    model_config = ConfigDict(frozen=True)

    type: str
    key: str


class Relation(BaseModel):
    """A link between two items; `from` on the wire."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, serialize_by_alias=True)

    type: str
    from_: End = Field(alias="from")
    to: End
    attributes: dict[str, str] = Field(default_factory=dict)


class Snapshot(BaseModel):
    """Everything one scan saw; also the payload between the two activities."""

    model_config = ConfigDict(frozen=True)

    items: list[Item]
    relations: list[Relation]


def workload_key(cluster: str, w: Workload) -> str:
    """Return the workload's key in Thoth."""
    return f"{cluster}/{w.namespace}/{w.kind}/{w.name}"


def _apps_seen(
    namespaces: list[Namespace], workloads: list[Workload], app_of: dict[str, str]
) -> dict[str, bool | None]:
    """Each app seen, and whether it runs: true, false (scaled to 0 on purpose) or None (a host binary)."""
    own = [w for w in workloads if w.kind in APP_KINDS and app_of.get(w.namespace) == w.namespace]
    running = {w.namespace for w in own if w.ready > 0}
    parked = {w.namespace for w in own if w.kind == "deployment" and w.replicas == 0} - running
    installed = {
        app_of[ns.name] for ns in namespaces if ns.name in app_of and ns.labels.get(HOST_BINARY_LABEL) == INSTALLED
    }
    seen: dict[str, bool | None] = dict.fromkeys(installed - running - parked)
    seen |= dict.fromkeys(parked, False)
    seen |= dict.fromkeys(running, True)
    return seen


def build(cluster: str, namespaces: list[Namespace], workloads: list[Workload]) -> Snapshot:
    """Turn what was listed into the snapshot, following the rules at the top of this module."""
    app_of = {ns.name: ns.labels[APP_LABEL] for ns in namespaces if APP_LABEL in ns.labels}
    items = [
        Item(type="app", key=app, name=app, attributes={"running": running})
        for app, running in sorted(_apps_seen(namespaces, workloads, app_of).items())
    ]
    relations = []
    for w in sorted(workloads, key=lambda w: workload_key(cluster, w)):
        key = workload_key(cluster, w)
        items.append(Item(type="workload", key=key, name=w.name))
        if app := app_of.get(w.namespace):
            relations.append(Relation(type="part-of", from_=End(type="workload", key=key), to=End(type="app", key=app)))
    return Snapshot(items=items, relations=relations)
