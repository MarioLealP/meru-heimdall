"""Reporting a scan to Thoth (D52, D54): phase 1 the items, phase 2 the links.

Both go under one scan id - the workflow run's - so a retried report counts no extra misses. Thoth refuses a snapshot
whole if anything in it is wrong.
"""

import httpx2

from heimdall.core.snapshot import Snapshot


async def report(
    http: httpx2.AsyncClient, thoth_url: str, token: str, scan_id: str, scope: str, snap: Snapshot
) -> dict:
    """Send both phases and return Thoth's answer to each; a 422 raises `RefusedError`."""
    base = f"{thoth_url}/v1/scans/{scan_id}/k8s-scan/{scope}"
    headers = {"Authorization": f"Bearer {token}"}
    answers = {}
    for phase, body in (
        ("items", {"items": [i.model_dump() for i in snap.items]}),
        ("relations", {"relations": [r.model_dump(by_alias=True) for r in snap.relations]}),
    ):
        response = await http.put(f"{base}/{phase}", json=body, headers=headers)
        if response.status_code == 422:  # refused: say why, the retry won't change it
            raise RefusedError(phase, response.text)
        response.raise_for_status()
        answers[phase] = response.json()
    return answers


class RefusedError(Exception):
    """Thoth turned a phase down; sending it again won't change that."""

    def __init__(self, phase: str, why: str):
        super().__init__(f"Thoth refused the {phase}: {why[:2000]}")
