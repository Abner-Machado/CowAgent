"""Regression tests for timezone-aware scheduler recurrence (#3145)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from agent.tools.scheduler.scheduler_service import SchedulerService
from agent.tools.scheduler.scheduler_tool import SchedulerTool
from agent.tools.scheduler import time_utils


def _cron_task(expression, timezone_name=None):
    schedule = {"type": "cron", "expression": expression}
    if timezone_name:
        schedule["timezone"] = timezone_name
    return {"id": "task-1", "schedule": schedule}


def _utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_cron_keeps_local_wall_clock_across_melbourne_dst():
    """A UTC cron would drift one hour after Melbourne changes offset."""
    task = _cron_task("0 11 * * 5", "Australia/Melbourne")
    before = _utc("2026-10-02T00:30:00")  # 10:30 AEST, before the transition
    first = SchedulerService.__new__(SchedulerService)._calculate_next_run(task, before)

    assert first == _utc("2026-10-02T01:00:00")  # 11:00 +10:00

    after_first = first + timedelta(minutes=1)
    second = SchedulerService.__new__(SchedulerService)._calculate_next_run(task, after_first)
    assert second == _utc("2026-10-09T00:00:00")  # 11:00 +11:00


def test_spring_forward_nonexistent_local_time_shifts_to_real_instant():
    task = _cron_task("30 2 * * *", "America/New_York")
    before = _utc("2026-03-08T06:00:00")

    next_run = SchedulerService.__new__(SchedulerService)._calculate_next_run(task, before)

    # 02:30 does not exist; croniter advances to the next real wall time
    # (03:00 EDT). The following day returns to 02:30 EST.
    assert next_run == _utc("2026-03-08T07:00:00")
    following = SchedulerService.__new__(SchedulerService)._calculate_next_run(task, next_run)
    assert following == _utc("2026-03-09T06:30:00")


def test_fall_back_repeated_local_hour_does_not_run_task_twice():
    task = _cron_task("30 1 * * *", "America/New_York")
    # Start just after the first Saturday occurrence so the next calculation
    # reaches the repeated 01:30 wall-clock hour on the transition day.
    before = _utc("2026-10-31T05:31:00")

    service = SchedulerService.__new__(SchedulerService)
    first = service._calculate_next_run(task, before)
    after_first = first + timedelta(minutes=1)
    second = service._calculate_next_run(task, after_first)

    assert first == _utc("2026-11-01T05:30:00")
    assert second == _utc("2026-11-02T06:30:00")  # next daily occurrence


def test_aware_timestamps_are_normalized_to_utc_for_zone_tasks():
    task = _cron_task("0 11 * * *", "Asia/Shanghai")
    task["next_run_at"] = "2026-10-02T11:00:00+08:00"
    task["last_run_at"] = "2026-10-02T10:00:00Z"

    normalized = time_utils.normalize_task_timestamps(task)

    assert normalized["next_run_at"] == "2026-10-02T03:00:00+00:00"
    assert normalized["last_run_at"] == "2026-10-02T10:00:00+00:00"


def test_legacy_task_timestamps_are_not_reinterpreted():
    """Tasks without a declared zone retain the pre-2.1.9 storage contract."""
    task = {
        "next_run_at": "2026-10-02T01:30:00",
        "last_run_at": "2026-10-01T01:30:00",
    }

    normalized = time_utils.normalize_task_timestamps(task)

    assert normalized["next_run_at"] == task["next_run_at"]
    assert normalized["last_run_at"] == task["last_run_at"]


def test_legacy_cron_keeps_naive_local_wall_clock_across_dst():
    """The default no-timezone path must not gain a fixed UTC offset."""
    task = _cron_task("0 11 * * 5")
    service = SchedulerService.__new__(SchedulerService)

    before = datetime.fromisoformat("2026-10-02T10:30:00")
    first = service._calculate_next_run(task, before)
    assert first == datetime.fromisoformat("2026-10-02T11:00:00")
    assert first.tzinfo is None

    after_first = first + timedelta(minutes=1)
    second = service._calculate_next_run(task, after_first)
    # 2026-10-04 starts DST in Melbourne, but the wall clock remains unchanged.
    assert second == datetime.fromisoformat("2026-10-09T11:00:00")
    assert second.tzinfo is None


def test_legacy_once_task_accepts_naive_web_reference_time():
    """The web create/edit APIs pass a naive datetime.now() as from_time."""
    task = {
        "id": "task-1",
        "schedule": {"type": "once", "run_at": "2026-10-02T11:00:00"},
    }

    next_run = SchedulerService.__new__(SchedulerService)._calculate_next_run(
        task, datetime.fromisoformat("2026-10-02T10:00:00")
    )

    assert next_run == datetime.fromisoformat("2026-10-02T11:00:00")


def test_legacy_once_task_accepts_aware_web_input_shapes():
    """Naive, offset, and Z input must all remain comparable for old tasks."""
    service = SchedulerService.__new__(SchedulerService)
    for value in (
        "2026-10-02T11:00:00",
        "2026-10-02T11:00:00+08:00",
        "2026-10-02T03:00:00Z",
    ):
        task = {"id": "task-1", "schedule": {"type": "once", "run_at": value}}
        expected = datetime.fromisoformat(value).astimezone().replace(tzinfo=None)
        assert service._calculate_next_run(task, expected - timedelta(minutes=1)) == expected


def test_service_compares_explicit_zone_timestamps_without_type_error():
    task = _cron_task("0 9 * * *", "Asia/Shanghai")
    task["next_run_at"] = "2026-10-02T09:00:00+08:00"
    normalized = time_utils.normalize_task_timestamps(task)

    service = SchedulerService.__new__(SchedulerService)
    assert service._is_task_due(normalized, _utc("2026-10-02T01:05:00")) is True
    assert service._is_task_due(normalized, _utc("2026-10-02T00:59:59")) is False


def test_service_accepts_naive_now_for_explicit_zone_task():
    task = _cron_task("0 11 * * *", "Australia/Melbourne")
    service = SchedulerService.__new__(SchedulerService)

    next_run = service._calculate_next_run(task, datetime.fromisoformat("2026-10-02T10:30:00"))
    assert next_run == _utc("2026-10-03T01:00:00")



def test_tool_uses_the_same_timezone_contract_for_initial_next_run():
    tool = SchedulerTool()
    schedule = tool._parse_schedule(
        "cron", "0 11 * * *", "Australia/Melbourne"
    )
    assert schedule == {
        "type": "cron",
        "expression": "0 11 * * *",
        "timezone": "Australia/Melbourne",
    }

    task = {"schedule": schedule}
    next_run = tool._calculate_next_run(task)
    assert next_run.tzinfo is not None
    assert next_run.utcoffset() == timezone.utc.utcoffset(None)
    assert next_run.astimezone(ZoneInfo("Australia/Melbourne")).hour == 11


def test_tool_rejects_unknown_iana_timezone():
    tool = SchedulerTool()

    assert tool._parse_schedule("cron", "0 11 * * *", "Not/A_Zone") is None


def test_tool_keeps_legacy_once_task_wall_clock():
    tool = SchedulerTool()
    schedule = tool._parse_schedule("once", "2026-10-02T11:00:00")

    assert schedule == {"type": "once", "run_at": "2026-10-02T11:00:00"}


def test_once_absolute_timestamp_is_canonicalized_with_task_zone():
    tool = SchedulerTool()
    schedule = tool._parse_schedule(
        "once", "2026-10-02T11:00:00", "Australia/Melbourne"
    )

    assert schedule["run_at"] == "2026-10-02T01:00:00+00:00"
    assert schedule["timezone"] == "Australia/Melbourne"


def test_run_task_now_checks_for_missing_task_before_migration():
    store = SimpleNamespace(get_task=lambda task_id: None)
    service = SchedulerService(store, lambda task: True)

    with pytest.raises(ValueError, match="Task 'missing' not found"):
        service.run_task_now("missing")


def test_is_task_due_uses_reference_now_for_zoned_tasks():
    """Future zoned task must not raise TypeError comparing naive now to aware next_run."""
    task = _cron_task("0 11 * * 5", "Australia/Melbourne")
    task["next_run_at"] = "2026-10-09T00:00:00+00:00"  # 11:00 AEDT Friday
    store = SimpleNamespace(update_task=lambda *a, **kw: None, delete_task=lambda *a, **kw: None)
    service = SchedulerService(store, lambda task: False)

    naive_now = datetime(2026, 10, 3, 12, 0, 0)  # naive server time, well before
    assert service._is_task_due(task, naive_now) is False

    # Timezone-independent: build naive local wall clock that maps to 00:05Z on ANY host
    ref_utc = datetime(2026, 10, 9, 0, 5, 0, tzinfo=timezone.utc)
    overdue_now = ref_utc.astimezone().replace(tzinfo=None)
    assert service._is_task_due(task, overdue_now) is True


def test_next_cron_occurrence_always_returns_future_instant():
    """During fall-back, the result must be strictly after the reference instant."""
    zone = ZoneInfo("Australia/Melbourne")
    # 2026-04-05 02:00 AEDT -> 01:00 AEST (fall-back); the 01:xx hour repeats.
    # If `after` is inside the second fold, croniter for a daily "1 1 * * *"
    # might return the first fold's 01:00 which is already past.
    after = datetime(2026, 4, 5, 1, 30, 0).replace(tzinfo=zone).astimezone(timezone.utc)
    result = time_utils.next_cron_occurrence("0 1 * * *", after, zone)
    assert result > after
