# Heimdall - cluster scanner

Meru's scan worker - tells Thoth what really runs in the cluster

Every 5 minutes a Temporal Schedule starts one `ClusterScan` in Temporal namespace `heimdall`:

1. **look** - lists every namespace, Deployment, StatefulSet and DaemonSet (read-only rights: Meru/meru
   `rbac/heimdall-reads-cluster.yaml`).
2. **report** - sends Thoth one snapshot as `k8s-scan@clockmost`: each workload as `clockmost/<namespace>/<kind>/<name>`,
   each Meru app whose own namespace has a ready Deployment (Thoth turns it `active`; it refuses an app nobody
   declared), and `part-of` links from a Meru app's workloads to the app.

Heimdall only ever says "seen". Something it stops seeing gets a miss in Thoth; three in a row put it on Anubis's list.
A snapshot is all or nothing: if any list fails, nothing is sent.

## Run locally

Needs Temporal, Thoth, the cluster and an Authentik login - in practice it runs in the cluster. The pieces run alone in
the tests.

## Development

```sh
scripts/check.sh   # lint, format, types, lockfile, tests - exactly what CI runs
```

## Deploy

`deploy/meru.yaml` makes this repo a Meru app: [Meru/meru](https://git.clockmost.com/Meru/meru) finds it and deploys it
into namespace `heimdall`. Shikigami adds it once the app's fence, signing key and build credentials exist,
from `deploy/meru.yaml.in` (the template's chart release and check image) with the owner from the request.
`deploy/values.yaml` is the app's whole deployment, rendered with the `nuwa-app` chart from
[Meru/nuwa](https://git.clockmost.com/Meru/nuwa). Merging to `main` runs the checks, builds the image, signs it and rolls
it out; builds run in namespace `heimdall-build` on the runner from [Meru/sindri](https://git.clockmost.com/Meru/sindri).
No secrets live in this repo: they come from OpenBao, through the External Secrets Operator or the build's own login.

## License

MIT - see `LICENSE`.
