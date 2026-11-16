import json
from pathlib import Path

import httpx2
import pytest

from heimdall.clients.kube import Cluster, Namespace, Workload


def cluster(tmp_path: Path, handler) -> Cluster:
    token = tmp_path / "token"
    token.write_text("pod-token\n")
    return Cluster(
        http=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)), api_url="https://k8s", token_file=token
    )


def page(items: list[dict], cont: str | None = None) -> httpx2.Response:
    return httpx2.Response(200, content=json.dumps({"metadata": {"continue": cont} if cont else {}, "items": items}))


async def test_namespaces_come_in_pages_with_the_pod_token(tmp_path: Path) -> None:
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.url.path, dict(request.url.params), request.headers["authorization"]))
        if "continue" not in request.url.params:
            return page([{"metadata": {"name": "echo", "labels": {"meru.clockmost.com/app": "echo"}}}], "next")
        return page([{"metadata": {"name": "zot"}}])

    found = await cluster(tmp_path, handler).namespaces()
    assert found == [Namespace(name="echo", labels={"meru.clockmost.com/app": "echo"}), Namespace(name="zot")]
    assert seen == [
        ("/api/v1/namespaces", {"limit": "500"}, "Bearer pod-token"),
        ("/api/v1/namespaces", {"limit": "500", "continue": "next"}, "Bearer pod-token"),
    ]


async def test_workloads_with_how_many_pods_are_ready(tmp_path: Path) -> None:
    lists = {
        "/apis/apps/v1/deployments": [
            {
                "metadata": {"name": "echo", "namespace": "echo"},
                "spec": {"replicas": 1},
                "status": {"readyReplicas": 1},
            },
            {"metadata": {"name": "kitsune", "namespace": "kitsune"}, "spec": {"replicas": 0}, "status": {}},
        ],
        "/apis/apps/v1/statefulsets": [
            {"metadata": {"name": "db", "namespace": "thoth"}, "status": {"readyReplicas": 1}}
        ],
        "/apis/apps/v1/daemonsets": [
            {"metadata": {"name": "falco", "namespace": "falco"}, "status": {"numberReady": 1}}
        ],
        "/apis/batch/v1/cronjobs": [
            {"metadata": {"name": "charon", "namespace": "charon"}, "spec": {"suspend": False}, "status": {}},
            {"metadata": {"name": "anubis", "namespace": "anubis"}, "spec": {}, "status": {}},  # suspend unset = false
            {"metadata": {"name": "paused", "namespace": "paused"}, "spec": {"suspend": True}, "status": {}},
        ],
    }
    found = await cluster(tmp_path, lambda request: page(lists[request.url.path])).workloads()
    assert found == [
        Workload(kind="deployment", namespace="echo", name="echo", ready=1, replicas=1),
        Workload(kind="deployment", namespace="kitsune", name="kitsune", ready=0, replicas=0),  # scaled to 0
        Workload(kind="statefulset", namespace="thoth", name="db", ready=1),
        Workload(kind="daemonset", namespace="falco", name="falco", ready=1),
        Workload(kind="cronjob", namespace="charon", name="charon", ready=1),  # scheduled
        Workload(kind="cronjob", namespace="anubis", name="anubis", ready=1),
        Workload(kind="cronjob", namespace="paused", name="paused", ready=0),  # suspended
    ]


async def test_a_failed_page_fails_the_whole_look(tmp_path: Path) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "continue" in request.url.params:
            return httpx2.Response(403)
        return page([{"metadata": {"name": "echo"}}], "next")

    with pytest.raises(httpx2.HTTPStatusError):
        await cluster(tmp_path, handler).namespaces()
