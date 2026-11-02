"""The cluster scan (D54, D102): a Temporal Schedule starts one every 5 minutes. Workflow code is replayed from
history after a restart, so it stays deterministic - the I/O lives in the activities."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from heimdall.activities import Activities
    from heimdall.snapshot import Snapshot

TIMEOUT = timedelta(minutes=1)  # per attempt
# A few quick retries, then the run fails and the next scan starts fresh 5 minutes later.
RETRY = RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=4)


@workflow.defn
class ClusterScan:
    @workflow.run
    async def run(self) -> dict:
        snap: Snapshot = await workflow.execute_activity_method(
            Activities.look, start_to_close_timeout=TIMEOUT, retry_policy=RETRY
        )
        # One scan id per run: a retried report is the same scan to Thoth, not one more miss.
        return await workflow.execute_activity_method(
            Activities.report,
            args=[f"k8s-{workflow.info().run_id}", snap],
            start_to_close_timeout=TIMEOUT,
            retry_policy=RETRY,
        )
