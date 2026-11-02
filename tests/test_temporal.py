from datetime import timedelta

from temporalio.client import ScheduleActionStartWorkflow, ScheduleOverlapPolicy

from heimdall.config import Settings
from heimdall.temporal import schedule


def test_one_scan_every_five_minutes_never_piling_up() -> None:
    s = schedule(Settings(authentik_password="x"))
    assert [i.every for i in s.spec.intervals] == [timedelta(minutes=5)]
    assert s.policy.overlap == ScheduleOverlapPolicy.SKIP
    assert isinstance(s.action, ScheduleActionStartWorkflow)
    assert (s.action.workflow, s.action.task_queue, s.action.execution_timeout) == (
        "ClusterScan",
        "heimdall",
        timedelta(minutes=5),
    )
