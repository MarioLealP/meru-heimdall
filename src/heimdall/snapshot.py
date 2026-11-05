"""What one look at the cluster tells Thoth (D100, D101), as a pure function of what was listed.

- Every Deployment, StatefulSet, DaemonSet and CronJob is a `workload` item, keyed
  `<cluster>/<namespace>/<kind>/<name>`. The cluster scan owns no workload fields yet, so it only says "seen".
- A Meru app is seen when its own namespace (the one named like the app, labelled `meru.clockmost.com/app: <name>`)
  has a Deployment with a ready pod, or a CronJob that isn't suspended (D117: Charon, Anubis). Only a confirm: Thoth
  refuses an app Shikigami never declared (D100).
- Every workload in a namespace labelled for an app - its build namespace too - is `part-of` that app (D55).
"""

from pydantic import BaseModel, ConfigDict, Field

from heimdall.kube import Namespace, Workload

APP_LABEL = "meru.clockmost.com/app"
APP_KINDS = {"deployment", "cronjob"}  # what an app runs as; a StatefulSet alone is its database, not the app


class Item(BaseModel):
    """One thing Thoth is told was seen."""

    model_config = ConfigDict(frozen=True)

    type: str
    key: str
    name: str
    attributes: dict[str, str] = Field(default_factory=dict)


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


def build(cluster: str, namespaces: list[Namespace], workloads: list[Workload]) -> Snapshot:
    """Turn what was listed into the snapshot, following the rules at the top of this module."""
    app_of = {ns.name: ns.labels[APP_LABEL] for ns in namespaces if APP_LABEL in ns.labels}
    running = {
        w.namespace for w in workloads if w.kind in APP_KINDS and w.ready > 0 and app_of.get(w.namespace) == w.namespace
    }
    items = [Item(type="app", key=app, name=app) for app in sorted(running)]
    relations = []
    for w in sorted(workloads, key=lambda w: workload_key(cluster, w)):
        key = workload_key(cluster, w)
        items.append(Item(type="workload", key=key, name=w.name))
        if app := app_of.get(w.namespace):
            relations.append(Relation(type="part-of", from_=End(type="workload", key=key), to=End(type="app", key=app)))
    return Snapshot(items=items, relations=relations)
