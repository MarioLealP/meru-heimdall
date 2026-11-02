"""Heimdall's settings, from HEIMDALL_* environment variables (Nüwa's env + secretEnv)."""

from datetime import timedelta
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEIMDALL_")

    # Temporal's front door (D70): mutual TLS with the pod's pki_meru certificate + an Authentik token. Its own
    # namespace (D103): its token can't touch Shikigami's workflows in `meru`.
    temporal_address: str = "temporal-frontend.temporal.svc:7233"
    temporal_server_name: str = "temporal-frontend.temporal.svc"
    temporal_namespace: str = "heimdall"
    task_queue: str = "heimdall"
    tls_dir: Path = Path("/var/run/meru/tls")  # tls.crt, tls.key, ca.crt (nuwa-app's certificate)

    # Authentik client_credentials (blueprints/heimdall.yaml): one service account, a token per provider.
    token_url: str = "https://auth.clockmost.com/application/o/token/"
    authentik_username: str = "heimdall"
    authentik_password: SecretStr
    temporal_client_id: str = "temporal"
    thoth_client_id: str = "thoth"
    thoth_url: str = "http://thoth.thoth.svc"

    # Listing the cluster (Meru/meru rbac/heimdall-reads-cluster.yaml): the pod's API token + cluster CA (nuwa-app
    # kubernetesApi). `cluster` is Thoth's scope and the first part of every workload key.
    kubernetes_url: str = "https://kubernetes.default.svc"
    kubernetes_dir: Path = Path("/var/run/meru/kubernetes")  # token, ca.crt
    cluster: str = "clockmost"

    # D102: one scan every 5 minutes; Thoth puts what 3 scans in a row miss on Anubis's list.
    scan_every: timedelta = timedelta(minutes=5)
    # Not `port`: Kubernetes puts HEIMDALL_PORT=tcp://... (a service link for the Service named heimdall) in the env.
    http_port: int = 8080
