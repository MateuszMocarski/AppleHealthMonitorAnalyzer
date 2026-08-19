from datetime import date, datetime, timedelta, timezone

from apple_health.analyzers.sleep_analyzer import SleepAnalyzer
from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import SleepStage
from apple_health.models import AppleHealthData, SleepRecord
from apple_health.sleep_score_config import BEDTIME_PENALTY_INTERVAL_MINUTES, BEDTIME_PENALTY_POINTS, SLEEP_DURATION_OVERSLEEP_WEIGHT, SLEEP_DURATION_PENALTY_INTERVAL_MINUTES, SLEEP_DURATION_PENALTY_POINTS, SLEEP_DURATION_TARGET_MINUTES, SLEEP_DURATION_TOLERANCE_MINUTES, SLEEP_DURATION_UNDERSLEEP_WEIGHT, WAKE_UP_BEDTIME_WEIGHT, WAKE_UP_DURATION_WEIGHT, WAKE_UP_PENALTY_INTERVAL_MINUTES, WAKE_UP_PENALTY_POINTS, WAKE_UP_TARGET

# =======
# Helpers
# =======

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
    
# =====================================================================================
# Verifies that consecutive sleep stage records are combined into a single
# sleep session and that stage durations and total sleep time are calculated correctly.
# =====================================================================================

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


# =================================================================
# Verifies that sleep records separated by more than the configured
# session gap threshold are treated as separate sleep sessions.
# =================================================================   

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
    
# =============================================================================
# Verifies the session gap boundary condition: records separated by exactly
# the configured threshold are still considered part of the same sleep session.
# =============================================================================

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

# ============================================================================
# Verifies that when multiple sleep sessions belong to the same reporting day,
# the longest session is selected as the primary sleep session.
# ============================================================================
   
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

# ============================================================= 
# Verifies that only sleep records originating from Apple Watch
# are used when reconstructing sleep sessions.
# =============================================================    

def test_ignores_sleep_records_from_non_watch_sources() -> None:
    start = datetime(
        2026,
        8,
        10,
        23,
        0,
        tzinfo=timezone.utc,
    )

    watch_record = _sleep_record(
        start,
        start + timedelta(hours=7),
        SleepStage.CORE,
    )

    other_record = SleepRecord(
        stage=SleepStage.CORE,
        source_name="Some Other Source",
        source_version=None,
        start=start + timedelta(hours=8),
        end=start + timedelta(hours=9),
        duration_minutes=60,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                watch_record,
                other_record,
            ]
        )
    )

    assert len(analyzer.sleep_sessions) == 1
    assert analyzer.sleep_sessions[0].time_asleep_minutes == 420
    
# =================================================================    
# Verifies that a sleep session starting in the evening is assigned
# to the following calendar day for reporting purposes.
# =================================================================   

def test_assigns_evening_sleep_to_next_reporting_day() -> None:
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
            start + timedelta(hours=7),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(
        _health_data(records)
    )

    session = analyzer.sleep_sessions[0]

    assert session.reporting_date == date(
        2026,
        8,
        11,
    )

    assert analyzer.session_for_day(
        date(2026, 8, 11)
    ) is session

# =====================================================================
# Verifies the reporting-date boundary condition: a sleep session
# starting at 12:00 or later is assigned to the following calendar day.
# =====================================================================
   
def test_assigns_sleep_starting_at_noon_to_next_reporting_day() -> None:
    start = datetime(
        2026,
        8,
        10,
        12,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=1),
                    SleepStage.CORE,
                )
            ]
        )
    )

    assert analyzer.sleep_sessions[0].reporting_date == date(
        2026,
        8,
        11,
    )
    
# =====================================================================
# Verifies that going to bed before the configured bedtime target
# receives the maximum bedtime score.
# =====================================================================

def test_bedtime_before_target_receives_maximum_score() -> None:
    start = datetime(
        2026,
        8,
        10,
        23,
        30,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=8),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]

    score = analyzer.score_session(session)

    assert score.bedtime_score == 100.0
    
# =====================================================================
# Verifies the bedtime target boundary condition: going to bed exactly
# at the configured target receives the maximum bedtime score.
# =====================================================================

def test_bedtime_at_target_receives_maximum_score() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=8),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]

    score = analyzer.score_session(session)

    assert score.bedtime_score == 100.0
    
# =====================================================================
# Verifies that going to bed one full penalty interval after the target
# reduces the bedtime score by exactly one configured penalty.
# =====================================================================

def test_bedtime_one_penalty_interval_late_applies_single_penalty() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        BEDTIME_PENALTY_INTERVAL_MINUTES,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=8),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]

    score = analyzer.score_session(session)

    assert score.bedtime_score == (
        100.0 - BEDTIME_PENALTY_POINTS
    )
    
# =====================================================================
# Verifies that a bedtime deviation smaller than one full penalty
# interval does not reduce the score when step penalties are enabled.
# =====================================================================

def test_bedtime_partial_penalty_interval_does_not_reduce_score() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        BEDTIME_PENALTY_INTERVAL_MINUTES - 1,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=8),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]

    score = analyzer.score_session(session)

    assert score.bedtime_score == 100.0
    
# =====================================================================
# Verifies that sleeping for exactly the configured target duration
# receives the maximum duration score.
# =====================================================================

def test_duration_at_target_receives_maximum_score() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(
                        minutes=SLEEP_DURATION_TARGET_MINUTES
                    ),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert score.duration_score == 100.0
    
# =====================================================================
# Verifies the lower duration tolerance boundary: sleeping exactly at
# the lower acceptable limit still receives the maximum duration score.
# =====================================================================

def test_duration_at_lower_tolerance_boundary_receives_maximum_score() -> None:
    duration_minutes = (
        SLEEP_DURATION_TARGET_MINUTES
        - SLEEP_DURATION_TOLERANCE_MINUTES
    )

    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(minutes=duration_minutes),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert score.duration_score == 100.0
    
# =====================================================================
# Verifies the upper duration tolerance boundary: sleeping exactly at
# the upper acceptable limit still receives the maximum duration score.
# =====================================================================

def test_duration_at_upper_tolerance_boundary_receives_maximum_score() -> None:
    duration_minutes = (
        SLEEP_DURATION_TARGET_MINUTES
        + SLEEP_DURATION_TOLERANCE_MINUTES
    )

    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(minutes=duration_minutes),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert score.duration_score == 100.0
    
# =====================================================================
# Verifies that sleeping one full penalty interval below the lower
# tolerance boundary applies one undersleep penalty with its weight.
# =====================================================================

def test_duration_one_penalty_interval_underslept_applies_penalty() -> None:
    duration_minutes = (
        SLEEP_DURATION_TARGET_MINUTES
        - SLEEP_DURATION_TOLERANCE_MINUTES
        - SLEEP_DURATION_PENALTY_INTERVAL_MINUTES
    )

    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(minutes=duration_minutes),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    expected_score = (
        100.0
        - SLEEP_DURATION_PENALTY_POINTS
        * SLEEP_DURATION_UNDERSLEEP_WEIGHT
    )

    assert score.duration_score == expected_score
    
# =====================================================================
# Verifies that sleeping one full penalty interval above the upper
# tolerance boundary applies one oversleep penalty with its weight.
# =====================================================================

def test_duration_one_penalty_interval_overslept_applies_penalty() -> None:
    duration_minutes = (
        SLEEP_DURATION_TARGET_MINUTES
        + SLEEP_DURATION_TOLERANCE_MINUTES
        + SLEEP_DURATION_PENALTY_INTERVAL_MINUTES
    )

    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(minutes=duration_minutes),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    expected_score = (
        100.0
        - SLEEP_DURATION_PENALTY_POINTS
        * SLEEP_DURATION_OVERSLEEP_WEIGHT
    )

    assert score.duration_score == expected_score
    
# =====================================================================
# Verifies that waking up at the configured target does not apply any
# additional penalty and returns the maximum available wake-up score.
# =====================================================================

def test_wake_up_at_target_receives_maximum_available_score() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    duration_minutes = (
        WAKE_UP_TARGET.hour * 60
        + WAKE_UP_TARGET.minute
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(minutes=duration_minutes),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    expected_max_score = (
        score.bedtime_score * WAKE_UP_BEDTIME_WEIGHT
        + score.duration_score * WAKE_UP_DURATION_WEIGHT
    ) / (
        WAKE_UP_BEDTIME_WEIGHT
        + WAKE_UP_DURATION_WEIGHT
    )

    assert score.wake_up_score == expected_max_score
    
# =====================================================================
# Verifies that waking up one full penalty interval after the target
# reduces the wake-up score by exactly one configured penalty.
# =====================================================================

def test_wake_up_one_penalty_interval_late_applies_single_penalty() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    wake_up_minutes = (
        WAKE_UP_TARGET.hour * 60
        + WAKE_UP_TARGET.minute
        + WAKE_UP_PENALTY_INTERVAL_MINUTES
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(minutes=wake_up_minutes),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    expected_max_score = (
        score.bedtime_score * WAKE_UP_BEDTIME_WEIGHT
        + score.duration_score * WAKE_UP_DURATION_WEIGHT
    ) / (
        WAKE_UP_BEDTIME_WEIGHT
        + WAKE_UP_DURATION_WEIGHT
    )

    expected_score = (
        expected_max_score
        - WAKE_UP_PENALTY_POINTS
    )

    assert score.wake_up_score == expected_score
    
# =====================================================================
# Verifies that the maximum wake-up score is calculated as the weighted
# average of the bedtime and duration scores using configured weights.
# =====================================================================

def test_wake_up_maximum_score_uses_bedtime_and_duration_weights() -> None:
    start = datetime(
        2026,
        8,
        11,
        1,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=7),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    expected_max_score = (
        score.bedtime_score * WAKE_UP_BEDTIME_WEIGHT
        + score.duration_score * WAKE_UP_DURATION_WEIGHT
    ) / (
        WAKE_UP_BEDTIME_WEIGHT
        + WAKE_UP_DURATION_WEIGHT
    )

    assert score.wake_up_score <= expected_max_score
    
# =====================================================================
# Verifies that waking up before the target cannot exceed the weighted
# maximum derived from the bedtime and duration component scores.
# =====================================================================

def test_wake_up_before_target_is_capped_by_component_scores() -> None:
    start = datetime(
        2026,
        8,
        11,
        1,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=6),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    expected_max_score = (
        score.bedtime_score * WAKE_UP_BEDTIME_WEIGHT
        + score.duration_score * WAKE_UP_DURATION_WEIGHT
    ) / (
        WAKE_UP_BEDTIME_WEIGHT
        + WAKE_UP_DURATION_WEIGHT
    )

    assert score.wake_up_score == expected_max_score
    
# =====================================================================
# Verifies that sufficiently large late wake-up penalties cannot reduce
# the wake-up score below zero.
# =====================================================================

def test_wake_up_score_never_drops_below_zero() -> None:
    start = datetime(
        2026,
        8,
        11,
        6,
        15,
        tzinfo=timezone.utc,
    )

    end = datetime(
        2026,
        8,
        11,
        11,
        59,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    end,
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert score.wake_up_score == 0.0