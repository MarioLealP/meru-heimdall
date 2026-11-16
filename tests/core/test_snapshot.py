from heimdall.clients.kube import Namespace, Workload
from heimdall.core.snapshot import HOST_BINARY_LABEL, INSTALLED, End, Relation, build

LABEL = "meru.clockmost.com/app"
NAMESPACES = [
    Namespace(name="tanuki", labels={LABEL: "tanuki"}),
    Namespace(name="tanuki-build", labels={LABEL: "tanuki"}),
    Namespace(name="kitsune", labels={LABEL: "kitsune"}),  # retired: stopped, nothing ready
    Namespace(name="temporal", labels={"meru.clockmost.com/owner": "platform"}),
]


def test_an_app_is_seen_when_its_own_namespace_has_a_ready_deployment() -> None:
    snap = build(
        "clockmost",
        NAMESPACES,
        [
            Workload(kind="deployment", namespace="tanuki", name="tanuki", ready=1),
            Workload(kind="deployment", namespace="tanuki-build", name="runner", ready=1),
            Workload(kind="deployment", namespace="kitsune", name="kitsune", ready=0),
            Workload(kind="statefulset", namespace="temporal", name="temporal-db", ready=1),
        ],
    )
    assert [(i.type, i.key) for i in snap.items] == [
        ("app", "tanuki"),  # kitsune has nothing ready (and isn't scaled to 0); the build namespace doesn't count
        ("workload", "clockmost/kitsune/deployment/kitsune"),
        ("workload", "clockmost/tanuki-build/deployment/runner"),
        ("workload", "clockmost/tanuki/deployment/tanuki"),
        ("workload", "clockmost/temporal/statefulset/temporal-db"),
    ]
    assert [i.attributes for i in snap.items if i.type == "app"] == [{"running": True}]
    assert all(i.attributes == {} for i in snap.items if i.type == "workload")  # workloads: only "seen"


def test_workloads_in_an_apps_namespaces_are_part_of_it() -> None:
    snap = build(
        "clockmost",
        NAMESPACES,
        [
            Workload(kind="deployment", namespace="tanuki-build", name="runner", ready=1),
            Workload(kind="daemonset", namespace="temporal", name="agent", ready=1),
        ],
    )
    assert snap.relations == [
        Relation(
            type="part-of",
            from_=End(type="workload", key="clockmost/tanuki-build/deployment/runner"),
            to=End(type="app", key="tanuki"),
        )
    ]
    assert snap.relations[0].model_dump(by_alias=True)["from"] == {
        "type": "workload",
        "key": "clockmost/tanuki-build/deployment/runner",
    }


def test_a_ready_statefulset_alone_does_not_make_an_app_running() -> None:
    snap = build("clockmost", NAMESPACES, [Workload(kind="statefulset", namespace="tanuki", name="db", ready=1)])
    assert [i.type for i in snap.items] == ["workload"]


def test_a_scheduled_cronjob_makes_an_app_running() -> None:
    namespaces = [
        Namespace(name="charon", labels={LABEL: "charon"}),
        Namespace(name="paused", labels={LABEL: "paused"}),
    ]
    snap = build(
        "clockmost",
        namespaces,
        [
            Workload(kind="cronjob", namespace="charon", name="charon", ready=1),
            Workload(kind="cronjob", namespace="paused", name="paused", ready=0),  # suspended: not seen as the app
        ],
    )
    assert [(i.type, i.key) for i in snap.items] == [
        ("app", "charon"),
        ("workload", "clockmost/charon/cronjob/charon"),
        ("workload", "clockmost/paused/cronjob/paused"),
    ]


def test_an_app_scaled_to_zero_on_purpose_is_seen_not_running() -> None:
    snap = build(
        "clockmost",
        [*NAMESPACES, Namespace(name="factorio", labels={LABEL: "factorio"})],
        [
            Workload(kind="deployment", namespace="factorio", name="factorio", ready=0, replicas=0),
            Workload(kind="deployment", namespace="kitsune", name="kitsune", ready=0, replicas=1),  # broken, not off
        ],
    )
    assert [(i.key, i.attributes) for i in snap.items if i.type == "app"] == [("factorio", {"running": False})]


def test_a_running_pod_wins_over_a_parked_deployment_in_the_same_namespace() -> None:
    snap = build(
        "clockmost",
        NAMESPACES,
        [
            Workload(kind="deployment", namespace="tanuki", name="tanuki", ready=1, replicas=1),
            Workload(kind="deployment", namespace="tanuki", name="worker", ready=0, replicas=0),
        ],
    )
    assert [(i.key, i.attributes) for i in snap.items if i.type == "app"] == [("tanuki", {"running": True})]


def test_a_host_binary_is_seen_once_the_host_installed_it() -> None:
    installed = {LABEL: "caddy", HOST_BINARY_LABEL: INSTALLED}
    namespaces = [
        Namespace(name="caddy-build", labels=installed),
        Namespace(name="gitea-build", labels={LABEL: "gitea"}),  # not installed yet: stays planned
        Namespace(name="vector-build", labels={LABEL: "vector", HOST_BINARY_LABEL: "pending"}),
    ]
    snap = build(
        "clockmost", namespaces, [Workload(kind="deployment", namespace="gitea-build", name="sindri", ready=1)]
    )
    assert [(i.key, i.attributes) for i in snap.items if i.type == "app"] == [("caddy", {"running": None})]
