from datetime import datetime, timedelta, timezone

from apple_health.analyzers.sleep_analyzer import SleepAnalyzer
from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import SleepStage
from apple_health.models import AppleHealthData, SleepRecord

#========
# Helpers
#========

def _sleep_record(
    start: datetime,
    end: datetime,
    stage: SleepStage,
) -> SleepRecord:
    return SleepRecord(
        stage=stage,
        source_name=APPLE_WATCH_SOURCE,
        source_version=None,
        start=start,
        end=end,
        duration_minutes=(end - start).total_seconds() / 60,
    )


def _health_data(
    sleep_records: list[SleepRecord],
) -> AppleHealthData:
    return AppleHealthData(
        workouts=[],
        daily_metrics=[],
        sleep_records=sleep_records,
    )
    
#======================================================================================
# Verifies that consecutive sleep stage records are combined into a single
# sleep session and that stage durations and total sleep time are calculated correctly.
#======================================================================================

def test_reconstructs_single_sleep_session() -> None:
    start = datetime(
        2026,
        8,
        10,
        23,
        30,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            start,
            start + timedelta(hours=2),
            SleepStage.CORE,
        ),
        _sleep_record(
            start + timedelta(hours=2),
            start + timedelta(hours=3),
            SleepStage.DEEP,
        ),
        _sleep_record(
            start + timedelta(hours=3),
            start + timedelta(hours=5),
            SleepStage.REM,
        ),
    ]

    analyzer = SleepAnalyzer(
        _health_data(records)
    )

    assert len(analyzer.sleep_sessions) == 1

    session = analyzer.sleep_sessions[0]

    assert session.bedtime == start
    assert session.wake_up == start + timedelta(hours=5)

    assert session.core_minutes == 120
    assert session.deep_minutes == 60
    assert session.rem_minutes == 120

    assert session.time_asleep_minutes == 300


#==================================================================
# Verifies that sleep records separated by more than the configured
# session gap threshold are treated as separate sleep sessions.
#==================================================================   

def test_splits_sleep_sessions_when_gap_exceeds_threshold() -> None:
    start = datetime(
        2026,
        8,
        10,
        23,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            start,
            start + timedelta(hours=2),
            SleepStage.CORE,
        ),
        _sleep_record(
            start + timedelta(hours=3),
            start + timedelta(hours=4),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(
        _health_data(records)
    )

    assert len(analyzer.sleep_sessions) == 2
    
#==============================================================================
# Verifies the session gap boundary condition: records separated by exactly
# the configured threshold are still considered part of the same sleep session.
#==============================================================================

def test_keeps_sleep_records_in_same_session_at_gap_threshold() -> None:
    start = datetime(
        2026,
        8,
        10,
        23,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            start,
            start + timedelta(hours=2),
            SleepStage.CORE,
        ),
        _sleep_record(
            start + timedelta(hours=2, minutes=30),
            start + timedelta(hours=3, minutes=30),
            SleepStage.REM,
        ),
    ]

    analyzer = SleepAnalyzer(
        _health_data(records)
    )

    assert len(analyzer.sleep_sessions) == 1

#=============================================================================
# Verifies that when multiple sleep sessions belong to the same reporting day,
# the longest session is selected as the primary sleep session.
#=============================================================================
   
def test_selects_longest_sleep_session_for_reporting_day() -> None:
    night_start = datetime(
        2026,
        8,
        14,
        0,
        30,
        tzinfo=timezone.utc,
    )

    nap_start = datetime(
        2026,
        8,
        14,
        15,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            night_start,
            night_start + timedelta(hours=7),
            SleepStage.CORE,
        ),
        _sleep_record(
            nap_start,
            nap_start + timedelta(hours=1),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(
        _health_data(records)
    )

    session = analyzer.session_for_day(
        night_start.date()
    )

    assert session is not None
    assert session.bedtime == night_start
    assert session.time_asleep_minutes == 420