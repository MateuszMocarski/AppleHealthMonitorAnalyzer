from datetime import date, datetime, time, timedelta, timezone
from statistics import pstdev

import apple_health.analyzers.sleep_analyzer as sleep_analyzer_module
from apple_health.analyzers.sleep_analyzer import SleepAnalyzer
from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import SleepStage
from apple_health.models import AppleHealthData, SleepRecord
from apple_health.sleep_score_config import (
    BEDTIME_PENALTY_INTERVAL_MINUTES,
    BEDTIME_PENALTY_POINTS,
    BEDTIME_SCORE_WEIGHT,
    BEDTIME_TARGET,
    SLEEP_AVERAGE_BONUS_THRESHOLDS,
    SLEEP_CONSISTENCY_BONUS_THRESHOLDS,
    SLEEP_DURATION_OVERSLEEP_WEIGHT,
    SLEEP_DURATION_PENALTY_INTERVAL_MINUTES,
    SLEEP_DURATION_PENALTY_POINTS,
    SLEEP_DURATION_SCORE_WEIGHT,
    SLEEP_DURATION_TARGET_MINUTES,
    SLEEP_DURATION_TOLERANCE_MINUTES,
    SLEEP_DURATION_UNDERSLEEP_WEIGHT,
    WAKE_UP_BEDTIME_WEIGHT,
    WAKE_UP_DURATION_WEIGHT,
    WAKE_UP_PENALTY_INTERVAL_MINUTES,
    WAKE_UP_PENALTY_POINTS,
    WAKE_UP_SCORE_WEIGHT,
    WAKE_UP_TARGET,
)

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

    analyzer = SleepAnalyzer(_health_data(records))

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

    analyzer = SleepAnalyzer(_health_data(records))

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

    analyzer = SleepAnalyzer(_health_data(records))

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

    analyzer = SleepAnalyzer(_health_data(records))

    session = analyzer.session_for_day(night_start.date())

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

    analyzer = SleepAnalyzer(_health_data(records))

    session = analyzer.sleep_sessions[0]

    assert session.reporting_date == date(
        2026,
        8,
        11,
    )

    assert analyzer.session_for_day(date(2026, 8, 11)) is session


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

    assert score.bedtime_score == (100.0 - BEDTIME_PENALTY_POINTS)


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
                    start + timedelta(minutes=SLEEP_DURATION_TARGET_MINUTES),
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
    duration_minutes = SLEEP_DURATION_TARGET_MINUTES - SLEEP_DURATION_TOLERANCE_MINUTES

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
    duration_minutes = SLEEP_DURATION_TARGET_MINUTES + SLEEP_DURATION_TOLERANCE_MINUTES

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

    expected_score = 100.0 - SLEEP_DURATION_PENALTY_POINTS * SLEEP_DURATION_UNDERSLEEP_WEIGHT

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

    expected_score = 100.0 - SLEEP_DURATION_PENALTY_POINTS * SLEEP_DURATION_OVERSLEEP_WEIGHT

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

    duration_minutes = WAKE_UP_TARGET.hour * 60 + WAKE_UP_TARGET.minute

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
    ) / (WAKE_UP_BEDTIME_WEIGHT + WAKE_UP_DURATION_WEIGHT)

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
        WAKE_UP_TARGET.hour * 60 + WAKE_UP_TARGET.minute + WAKE_UP_PENALTY_INTERVAL_MINUTES
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
    ) / (WAKE_UP_BEDTIME_WEIGHT + WAKE_UP_DURATION_WEIGHT)

    expected_score = expected_max_score - WAKE_UP_PENALTY_POINTS

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
    ) / (WAKE_UP_BEDTIME_WEIGHT + WAKE_UP_DURATION_WEIGHT)

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
    ) / (WAKE_UP_BEDTIME_WEIGHT + WAKE_UP_DURATION_WEIGHT)

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


# =====================================================================
# Verifies that the final daily sleep score is calculated as the
# configured weighted average of bedtime, duration and wake-up scores.
# =====================================================================


def test_total_sleep_score_uses_configured_component_weights() -> None:
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

    expected_score = (
        score.bedtime_score * BEDTIME_SCORE_WEIGHT
        + score.duration_score * SLEEP_DURATION_SCORE_WEIGHT
        + score.wake_up_score * WAKE_UP_SCORE_WEIGHT
    ) / (BEDTIME_SCORE_WEIGHT + SLEEP_DURATION_SCORE_WEIGHT + WAKE_UP_SCORE_WEIGHT)

    assert score.total_score == expected_score


# =====================================================================
# Verifies that the final daily sleep score remains within the valid
# 0-100 range when all component scores are combined.
# =====================================================================


def test_total_sleep_score_stays_within_valid_range() -> None:
    start = datetime(
        2026,
        8,
        11,
        5,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = SleepAnalyzer(
        _health_data(
            [
                _sleep_record(
                    start,
                    start + timedelta(hours=3),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert 0.0 <= score.total_score <= 100.0


# =====================================================================
# Verifies that the monthly sleep summary calculates the average
# bedtime, duration and wake-up component scores from daily sleep scores.
# =====================================================================


def test_monthly_summary_calculates_average_component_scores() -> None:
    first_start = datetime(
        2026,
        8,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )

    second_start = datetime(
        2026,
        8,
        2,
        1,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            first_start,
            first_start + timedelta(hours=8),
            SleepStage.CORE,
        ),
        _sleep_record(
            second_start,
            second_start + timedelta(hours=7),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    first_session = analyzer.session_for_day(date(2026, 8, 1))
    second_session = analyzer.session_for_day(date(2026, 8, 2))

    assert first_session is not None
    assert second_session is not None

    first_score = analyzer.score_session(first_session)
    second_score = analyzer.score_session(second_session)

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert (
        summary.average_bedtime_score
        == (first_score.bedtime_score + second_score.bedtime_score) / 2
    )

    assert (
        summary.average_duration_score
        == (first_score.duration_score + second_score.duration_score) / 2
    )

    assert (
        summary.average_wake_up_score
        == (first_score.wake_up_score + second_score.wake_up_score) / 2
    )


# =====================================================================
# Verifies that the monthly average sleep score is calculated from the
# final daily sleep scores rather than from independently averaged parts.
# =====================================================================


def test_monthly_summary_calculates_average_total_sleep_score() -> None:
    first_start = datetime(
        2026,
        8,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )

    second_start = datetime(
        2026,
        8,
        2,
        1,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            first_start,
            first_start + timedelta(hours=8),
            SleepStage.CORE,
        ),
        _sleep_record(
            second_start,
            second_start + timedelta(hours=7),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    first_session = analyzer.session_for_day(date(2026, 8, 1))
    second_session = analyzer.session_for_day(date(2026, 8, 2))

    assert first_session is not None
    assert second_session is not None

    first_score = analyzer.score_session(first_session)
    second_score = analyzer.score_session(second_session)

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    expected_average = (first_score.total_score + second_score.total_score) / 2

    assert summary.average_sleep_score == expected_average


# =====================================================================
# Verifies that the monthly average bonus is selected from the highest
# configured threshold satisfied by the average daily sleep score.
# =====================================================================


def test_monthly_average_bonus_uses_matching_threshold() -> None:
    start = datetime(
        2026,
        8,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            start,
            start + timedelta(hours=8),
            SleepStage.CORE,
        )
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=1,
    )

    expected_bonus = next(
        (
            bonus
            for threshold, bonus in SLEEP_AVERAGE_BONUS_THRESHOLDS
            if summary.average_sleep_score >= threshold
        ),
        0,
    )

    assert summary.average_bonus == expected_bonus


# =====================================================================
# Verifies that the monthly consistency bonus is selected according to
# the population standard deviation of the daily total sleep scores.
# =====================================================================


def test_monthly_consistency_bonus_uses_sleep_score_standard_deviation() -> None:
    starts = [
        datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 2, 0, 30, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc),
    ]

    durations = [
        timedelta(hours=8),
        timedelta(hours=7, minutes=30),
        timedelta(hours=7),
    ]

    records = [
        _sleep_record(
            start,
            start + duration,
            SleepStage.CORE,
        )
        for start, duration in zip(
            starts,
            durations,
            strict=True,
        )
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    sleep_scores = [
        analyzer.score_session(analyzer.session_for_day(start.date())) for start in starts
    ]

    standard_deviation = pstdev(score.total_score for score in sleep_scores)

    expected_bonus = next(
        (
            bonus
            for threshold, bonus in SLEEP_CONSISTENCY_BONUS_THRESHOLDS
            if standard_deviation < threshold
        ),
        0,
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.consistency_bonus == expected_bonus


# =====================================================================
# Verifies that consistency cannot be evaluated from a single daily
# sleep score and therefore does not grant a consistency bonus.
# =====================================================================


def test_monthly_consistency_bonus_is_zero_for_single_session() -> None:
    start = datetime(
        2026,
        8,
        1,
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

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=1,
    )

    assert summary.consistency_bonus == 0.0


# =====================================================================
# Verifies that the final monthly sleep score is the sum of the average
# daily sleep score, average bonus and consistency bonus.
# =====================================================================


def test_monthly_sleep_score_combines_average_and_bonuses() -> None:
    starts = [
        datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 2, 0, 30, tzinfo=timezone.utc),
        datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc),
    ]

    records = [
        _sleep_record(
            starts[0],
            starts[0] + timedelta(hours=8),
            SleepStage.CORE,
        ),
        _sleep_record(
            starts[1],
            starts[1] + timedelta(hours=7, minutes=30),
            SleepStage.CORE,
        ),
        _sleep_record(
            starts[2],
            starts[2] + timedelta(hours=7),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    expected_score = summary.average_sleep_score + summary.average_bonus + summary.consistency_bonus

    assert summary.monthly_sleep_score == expected_score


# =====================================================================
# Verifies that awake intervals are tracked separately and are not
# included in the total amount of time counted as sleep.
# =====================================================================


def test_awake_time_is_excluded_from_total_sleep_time() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
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
            start + timedelta(hours=2),
            start + timedelta(hours=2, minutes=30),
            SleepStage.AWAKE,
        ),
        _sleep_record(
            start + timedelta(hours=2, minutes=30),
            start + timedelta(hours=4, minutes=30),
            SleepStage.REM,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    session = analyzer.sleep_sessions[0]

    assert session.time_asleep_minutes == 240
    assert session.awake_minutes == 30
    assert session.time_in_bed_minutes == 270


# =====================================================================
# Verifies that sleep efficiency represents the percentage of time in
# bed that was actually spent asleep.
# =====================================================================


def test_sleep_efficiency_is_calculated_from_sleep_and_time_in_bed() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            start,
            start + timedelta(hours=6),
            SleepStage.CORE,
        ),
        _sleep_record(
            start + timedelta(hours=6),
            start + timedelta(hours=7),
            SleepStage.AWAKE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    session = analyzer.sleep_sessions[0]

    expected_efficiency = session.time_asleep_minutes / session.time_in_bed_minutes * 100

    assert session.sleep_efficiency_percent == expected_efficiency


# =====================================================================
# Verifies that an IN_BED interval is not counted as actual sleep when
# calculating the total amount of time asleep.
# =====================================================================


def test_in_bed_stage_is_not_counted_as_sleep() -> None:
    start = datetime(
        2026,
        8,
        11,
        0,
        0,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            start,
            start + timedelta(hours=1),
            SleepStage.IN_BED,
        ),
        _sleep_record(
            start + timedelta(hours=1),
            start + timedelta(hours=7),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    session = analyzer.sleep_sessions[0]

    assert session.time_asleep_minutes == 360


# =====================================================================
# Verifies that requesting a sleep session for a day without a primary
# sleep session returns None instead of an unrelated session.
# =====================================================================


def test_session_for_day_returns_none_when_no_session_exists() -> None:
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

    assert analyzer.session_for_day(date(2026, 8, 12)) is None


# =====================================================================
# Verifies that monthly average bedtime is calculated correctly across
# midnight instead of treating late evening and early morning as distant times.
# =====================================================================


def test_monthly_average_bedtime_handles_midnight_correctly() -> None:
    first_start = datetime(
        2026,
        8,
        1,
        23,
        30,
        tzinfo=timezone.utc,
    )

    second_start = datetime(
        2026,
        8,
        3,
        0,
        30,
        tzinfo=timezone.utc,
    )

    records = [
        _sleep_record(
            first_start,
            first_start + timedelta(hours=8),
            SleepStage.CORE,
        ),
        _sleep_record(
            second_start,
            second_start + timedelta(hours=8),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_bedtime == time(
        0,
        0,
    )


# =====================================================================
# Verifies that sufficiently large bedtime penalties cannot reduce the
# bedtime score below zero.
# =====================================================================


def test_bedtime_score_never_drops_below_zero() -> None:
    start = datetime(
        2026,
        8,
        11,
        11,
        45,
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

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert score.bedtime_score == 0.0


# =====================================================================
# Verifies that sufficiently large undersleep penalties cannot reduce
# the duration score below zero.
# =====================================================================


def test_duration_score_never_drops_below_zero() -> None:
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
                    start + timedelta(minutes=1),
                    SleepStage.CORE,
                )
            ]
        )
    )

    session = analyzer.sleep_sessions[0]
    score = analyzer.score_session(session)

    assert score.duration_score == 0.0


# =====================================================================
# Verifies that linear penalty mode applies a proportional penalty for
# deviations smaller than one full configured penalty interval.
# =====================================================================


def test_linear_penalty_mode_applies_proportional_penalty(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sleep_analyzer_module,
        "SLEEP_SCORE_LINEAR_PENALTIES",
        True,
    )

    target = datetime(
        2026,
        8,
        11,
        BEDTIME_TARGET.hour,
        BEDTIME_TARGET.minute,
        tzinfo=timezone.utc,
    )

    deviation_minutes = BEDTIME_PENALTY_INTERVAL_MINUTES - 1

    start = target + timedelta(minutes=deviation_minutes)

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

    expected_penalty = deviation_minutes / BEDTIME_PENALTY_INTERVAL_MINUTES * BEDTIME_PENALTY_POINTS

    assert score.bedtime_score == (100.0 - expected_penalty)


# =====================================================================
# Verifies that disabling the monthly bonus system prevents both the
# average and consistency bonuses from being applied.
# =====================================================================


def test_monthly_bonuses_are_zero_when_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sleep_analyzer_module,
        "SLEEP_MONTHLY_BONUS_ENABLED",
        False,
    )

    starts = [
        datetime(
            2026,
            8,
            1,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        datetime(
            2026,
            8,
            2,
            1,
            0,
            tzinfo=timezone.utc,
        ),
    ]

    records = [
        _sleep_record(
            starts[0],
            starts[0] + timedelta(hours=8),
            SleepStage.CORE,
        ),
        _sleep_record(
            starts[1],
            starts[1] + timedelta(hours=7),
            SleepStage.CORE,
        ),
    ]

    analyzer = SleepAnalyzer(_health_data(records))

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.average_bonus == 0.0
    assert summary.consistency_bonus == 0.0
    assert summary.monthly_sleep_score == summary.average_sleep_score
