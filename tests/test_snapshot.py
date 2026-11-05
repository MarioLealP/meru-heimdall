from heimdall.kube import Namespace, Workload
from heimdall.snapshot import End, Relation, build

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
        ("app", "tanuki"),  # kitsune has nothing ready; the build namespace doesn't count as the app running
        ("workload", "clockmost/kitsune/deployment/kitsune"),
        ("workload", "clockmost/tanuki-build/deployment/runner"),
        ("workload", "clockmost/tanuki/deployment/tanuki"),
        ("workload", "clockmost/temporal/statefulset/temporal-db"),
    ]
    assert all(i.attributes == {} for i in snap.items)  # the cluster scan owns no fields: it only says seen


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
