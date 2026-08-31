from datetime import date, datetime, time, timedelta, timezone
from statistics import pstdev

import pytest

from apple_health.analyzers.sleep_analyzer import SleepAnalyzer
from apple_health.config.app_config import AppConfig
from apple_health.enums import SleepStage
from apple_health.models import AppleHealthData, SleepRecord
from apple_health.report_models import SleepScore, SleepSession

# =======
# Helpers
# =======


def _datetime(
    day: int,
    hour: int = 0,
    minute: int = 0,
) -> datetime:
    return datetime(
        2026,
        8,
        day,
        hour,
        minute,
        tzinfo=timezone.utc,
    )


def _sleep_record(
    start: datetime,
    end: datetime,
    stage: SleepStage = SleepStage.CORE,
    source_name: str | None = None,
) -> SleepRecord:
    source_name = source_name if source_name is not None else AppConfig().source.apple_watch_source

    return SleepRecord(
        stage=stage,
        source_name=source_name,
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


def _analyzer(
    *sleep_records: SleepRecord,
    config: AppConfig | None = None,
) -> SleepAnalyzer:
    return SleepAnalyzer(
        _health_data(list(sleep_records)),
        config=config,
    )


def _analyzer_for_single_sleep(
    start: datetime,
    duration: timedelta,
    stage: SleepStage = SleepStage.CORE,
    config: AppConfig | None = None,
) -> SleepAnalyzer:
    return _analyzer(
        _sleep_record(
            start,
            start + duration,
            stage,
        ),
        config=config,
    )


def _single_session(
    start: datetime,
    duration: timedelta,
    stage: SleepStage = SleepStage.CORE,
    config: AppConfig | None = None,
) -> tuple[SleepAnalyzer, SleepSession]:
    analyzer = _analyzer_for_single_sleep(
        start,
        duration,
        stage,
        config=config,
    )

    return analyzer, analyzer.sleep_sessions[0]


def _score_sleep(
    start: datetime,
    duration: timedelta,
    config: AppConfig | None = None,
) -> SleepScore:
    analyzer, session = _single_session(
        start,
        duration,
        config=config,
    )

    return analyzer.score_session(session)


def _wake_up_max_score(
    score: SleepScore,
    config: AppConfig,
) -> float:
    wakeup_config = config.sleep.score.wake_up

    return (
        score.bedtime_score * wakeup_config.bedtime_weight
        + score.duration_score * wakeup_config.duration_weight
    ) / (wakeup_config.bedtime_weight + wakeup_config.duration_weight)


# =====================================================================
# Verifies that consecutive sleep stage records are combined into a
# single sleep session and that stage durations and total sleep time
# are calculated correctly.
# =====================================================================


def test_reconstructs_single_sleep_session() -> None:
    start = _datetime(10, 23, 30)

    analyzer = _analyzer(
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
    )

    assert len(analyzer.sleep_sessions) == 1

    session = analyzer.sleep_sessions[0]

    assert session.bedtime == start
    assert session.wake_up == start + timedelta(hours=5)
    assert session.core_minutes == 120
    assert session.deep_minutes == 60
    assert session.rem_minutes == 120
    assert session.time_asleep_minutes == 300


# =====================================================================
# Verifies that sleep-session reconstruction is independent of the
# input record order by sorting eligible Apple Watch records
# chronologically.
# =====================================================================


def test_reconstructs_sleep_session_from_unsorted_records() -> None:
    start = _datetime(10, 23, 30)

    analyzer = _analyzer(
        _sleep_record(
            start + timedelta(hours=3),
            start + timedelta(hours=5),
            SleepStage.REM,
        ),
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
    )

    assert len(analyzer.sleep_sessions) == 1

    session = analyzer.sleep_sessions[0]

    assert session.bedtime == start
    assert session.wake_up == start + timedelta(hours=5)
    assert session.core_minutes == 120
    assert session.deep_minutes == 60
    assert session.rem_minutes == 120
    assert session.time_asleep_minutes == 300


# =====================================================================
# Verifies that sleep records separated by more than the configured
# session gap threshold are treated as separate sleep sessions.
# =====================================================================


def test_splits_sleep_sessions_when_gap_exceeds_threshold() -> None:
    start = _datetime(10, 23)

    analyzer = _analyzer(
        _sleep_record(
            start,
            start + timedelta(hours=2),
        ),
        _sleep_record(
            start + timedelta(hours=3),
            start + timedelta(hours=4),
        ),
    )

    assert len(analyzer.sleep_sessions) == 2


# =====================================================================
# Verifies that records separated by exactly the configured gap
# threshold remain in one sleep session.
# =====================================================================


def test_keeps_sleep_records_in_same_session_at_gap_threshold() -> None:
    start = _datetime(10, 23)

    analyzer = _analyzer(
        _sleep_record(
            start,
            start + timedelta(hours=2),
        ),
        _sleep_record(
            start + timedelta(hours=2, minutes=30),
            start + timedelta(hours=3, minutes=30),
            SleepStage.REM,
        ),
    )

    assert len(analyzer.sleep_sessions) == 1


# =====================================================================
# Verifies that when multiple sleep sessions belong to the same
# reporting day, the longest session is selected as the primary sleep
# session.
# =====================================================================


def test_selects_longest_sleep_session_for_reporting_day() -> None:
    night_start = _datetime(14, 0, 30)
    nap_start = _datetime(14, 15)

    analyzer = _analyzer(
        _sleep_record(
            night_start,
            night_start + timedelta(hours=7),
        ),
        _sleep_record(
            nap_start,
            nap_start + timedelta(hours=1),
        ),
    )

    session = analyzer.session_for_day(night_start.date())

    assert session is not None
    assert session.bedtime == night_start
    assert session.time_asleep_minutes == 420


# =====================================================================
# Verifies that only sleep records originating from Apple Watch are
# used when reconstructing sleep sessions.
# =====================================================================


def test_ignores_sleep_records_from_non_watch_sources() -> None:
    start = _datetime(10, 23)

    analyzer = _analyzer(
        _sleep_record(
            start,
            start + timedelta(hours=7),
        ),
        _sleep_record(
            start + timedelta(hours=8),
            start + timedelta(hours=9),
            source_name="Some Other Source",
        ),
    )

    assert len(analyzer.sleep_sessions) == 1
    assert analyzer.sleep_sessions[0].time_asleep_minutes == 420


# =====================================================================
# Verifies that a sleep session starting in the evening is assigned to
# the following calendar day for reporting purposes.
# =====================================================================


def test_assigns_evening_sleep_to_next_reporting_day() -> None:
    start = _datetime(10, 23, 30)

    analyzer, session = _single_session(
        start,
        timedelta(hours=7),
    )

    assert session.reporting_date == date(
        2026,
        8,
        11,
    )
    assert analyzer.session_for_day(date(2026, 8, 11)) is session


# =====================================================================
# Verifies that a sleep session starting at noon is assigned to the
# following reporting day.
# =====================================================================


def test_assigns_sleep_starting_at_noon_to_next_reporting_day() -> None:
    _, session = _single_session(
        _datetime(10, 12),
        timedelta(hours=1),
    )

    assert session.reporting_date == date(
        2026,
        8,
        11,
    )


# =====================================================================
# Verifies that going to bed before the configured bedtime target
# receives the maximum bedtime score.
# =====================================================================


def test_bedtime_before_target_receives_maximum_score() -> None:
    score = _score_sleep(
        _datetime(10, 23, 30),
        timedelta(hours=8),
    )

    assert score.bedtime_score == 100.0


# =====================================================================
# Verifies that a bedtime exactly at the configured target receives the
# maximum bedtime score.
# =====================================================================


def test_bedtime_at_target_receives_maximum_score() -> None:
    config = AppConfig()
    bedtime_config = config.sleep.score.bedtime
    start = _datetime(
        11,
        bedtime_config.target.hour,
        bedtime_config.target.minute,
    )

    score = _score_sleep(
        start,
        timedelta(hours=8),
        config=config,
    )

    assert score.bedtime_score == 100.0


# =====================================================================
# Verifies that going to bed one full penalty interval after the target
# reduces the bedtime score by exactly one configured penalty.
# =====================================================================


def test_bedtime_one_penalty_interval_late_applies_single_penalty() -> None:
    config = AppConfig()
    bedtime_config = config.sleep.score.bedtime
    target = _datetime(
        11,
        bedtime_config.target.hour,
        bedtime_config.target.minute,
    )
    start = target + timedelta(minutes=bedtime_config.penalty_interval_minutes)

    score = _score_sleep(
        start,
        timedelta(hours=8),
        config=config,
    )

    assert score.bedtime_score == (100.0 - bedtime_config.penalty_points)


# =====================================================================
# Verifies that a bedtime deviation smaller than one full penalty
# interval does not reduce the score when step penalties are enabled.
# =====================================================================


def test_bedtime_partial_penalty_interval_does_not_reduce_score() -> None:
    config = AppConfig()
    bedtime_config = config.sleep.score.bedtime
    target = _datetime(
        11,
        bedtime_config.target.hour,
        bedtime_config.target.minute,
    )
    start = target + timedelta(minutes=bedtime_config.penalty_interval_minutes - 1)

    score = _score_sleep(
        start,
        timedelta(hours=8),
        config=config,
    )

    assert score.bedtime_score == 100.0


# =====================================================================
# Verifies that sleeping for exactly the configured target duration
# receives the maximum duration score.
# =====================================================================


def test_duration_at_target_receives_maximum_score() -> None:
    config = AppConfig()
    duration_config = config.sleep.score.duration
    score = _score_sleep(
        _datetime(11),
        timedelta(minutes=duration_config.target_minutes),
        config=config,
    )

    assert score.duration_score == 100.0


# =====================================================================
# Verifies that sleep duration at the lower tolerance boundary receives
# the maximum duration score.
# =====================================================================


def test_duration_at_lower_tolerance_boundary_receives_maximum_score() -> None:
    config = AppConfig()
    duration_config = config.sleep.score.duration
    duration_minutes = duration_config.target_minutes - duration_config.tolerance_minutes

    score = _score_sleep(
        _datetime(11),
        timedelta(minutes=duration_minutes),
        config=config,
    )

    assert score.duration_score == 100.0


# =====================================================================
# Verifies that sleep duration at the upper tolerance boundary receives
# the maximum duration score.
# =====================================================================


def test_duration_at_upper_tolerance_boundary_receives_maximum_score() -> None:
    config = AppConfig()
    duration_config = config.sleep.score.duration
    duration_minutes = duration_config.target_minutes + duration_config.tolerance_minutes

    score = _score_sleep(
        _datetime(11),
        timedelta(minutes=duration_minutes),
        config=config,
    )

    assert score.duration_score == 100.0


# =====================================================================
# Verifies that sleeping one full penalty interval below the lower
# tolerance boundary applies one undersleep penalty with its weight.
# =====================================================================


def test_duration_one_penalty_interval_underslept_applies_penalty() -> None:
    config = AppConfig()
    duration_config = config.sleep.score.duration
    duration_minutes = (
        duration_config.target_minutes
        - duration_config.tolerance_minutes
        - duration_config.penalty_interval_minutes
    )

    score = _score_sleep(
        _datetime(11),
        timedelta(minutes=duration_minutes),
        config=config,
    )

    expected_score = 100.0 - duration_config.penalty_points * duration_config.undersleep_weight

    assert score.duration_score == expected_score


# =====================================================================
# Verifies that sleeping one full penalty interval above the upper
# tolerance boundary applies one oversleep penalty with its weight.
# =====================================================================


def test_duration_one_penalty_interval_overslept_applies_penalty() -> None:
    config = AppConfig()
    duration_config = config.sleep.score.duration
    duration_minutes = (
        duration_config.target_minutes
        + duration_config.tolerance_minutes
        + duration_config.penalty_interval_minutes
    )

    score = _score_sleep(
        _datetime(11),
        timedelta(minutes=duration_minutes),
        config=config,
    )

    expected_score = 100.0 - duration_config.penalty_points * duration_config.oversleep_weight

    assert score.duration_score == expected_score


# =====================================================================
# Verifies that waking up at the configured target does not apply any
# additional penalty and returns the maximum available wake-up score.
# =====================================================================


def test_wake_up_at_target_receives_maximum_available_score() -> None:
    config = AppConfig()
    wakeup_config = config.sleep.score.wake_up

    start = _datetime(11)

    duration_minutes = wakeup_config.target.hour * 60 + wakeup_config.target.minute

    score = _score_sleep(
        start,
        timedelta(minutes=duration_minutes),
        config=config,
    )

    assert score.wake_up_score == _wake_up_max_score(
        score,
        config=config,
    )


# =====================================================================
# Verifies that waking up one full penalty interval after the target
# reduces the wake-up score by exactly one configured penalty.
# =====================================================================


def test_wake_up_one_penalty_interval_late_applies_single_penalty() -> None:
    config = AppConfig()
    start = _datetime(11)
    wakeup_config = config.sleep.score.wake_up
    wake_up_minutes = (
        wakeup_config.target.hour * 60
        + wakeup_config.target.minute
        + wakeup_config.penalty_interval_minutes
    )

    score = _score_sleep(
        start,
        timedelta(minutes=wake_up_minutes),
        config=config,
    )

    expected_score = _wake_up_max_score(score, config=config) - wakeup_config.penalty_points

    assert score.wake_up_score == expected_score


# =====================================================================
# Verifies that the maximum wake-up score is calculated as the weighted
# average of the bedtime and duration scores using configured weights.
# =====================================================================


def test_wake_up_maximum_score_uses_bedtime_and_duration_weights() -> None:
    config = AppConfig()

    score = _score_sleep(
        _datetime(11, 1),
        timedelta(hours=7),
        config=config,
    )

    assert score.wake_up_score <= _wake_up_max_score(
        score,
        config,
    )


# =====================================================================
# Verifies that waking up before the target cannot exceed the weighted
# maximum derived from the bedtime and duration component scores.
# =====================================================================


def test_wake_up_before_target_is_capped_by_component_scores() -> None:
    config = AppConfig()

    score = _score_sleep(
        _datetime(11, 1),
        timedelta(hours=6),
        config=config,
    )

    assert score.wake_up_score == _wake_up_max_score(
        score,
        config,
    )


# =====================================================================
# Verifies that sufficiently large late wake-up penalties cannot reduce
# the wake-up score below zero.
# =====================================================================


def test_wake_up_score_never_drops_below_zero() -> None:
    analyzer = _analyzer(
        _sleep_record(
            _datetime(11, 6, 15),
            _datetime(11, 11, 59),
        )
    )

    score = analyzer.score_session(analyzer.sleep_sessions[0])

    assert score.wake_up_score == 0.0


# =====================================================================
# Verifies that the final daily sleep score is calculated as the
# configured weighted average of bedtime, duration and wake-up scores.
# =====================================================================


def test_total_sleep_score_uses_configured_component_weights() -> None:
    config = AppConfig()

    weights = config.sleep.score.weights
    weights.bedtime = 1.0
    weights.duration = 2.0
    weights.wake_up = 3.0

    score = _score_sleep(
        _datetime(11, 1),
        timedelta(hours=7),
        config=config,
    )

    expected_score = (
        score.bedtime_score * weights.bedtime
        + score.duration_score * weights.duration
        + score.wake_up_score * weights.wake_up
    ) / (weights.bedtime + weights.duration + weights.wake_up)

    assert score.total_score == expected_score


# =====================================================================
# Verifies that the final daily sleep score remains within the valid
# 0-100 range when all component scores are combined.
# =====================================================================


def test_total_sleep_score_stays_within_valid_range() -> None:
    score = _score_sleep(
        _datetime(11, 5),
        timedelta(hours=3),
    )

    assert 0.0 <= score.total_score <= 100.0


# =====================================================================
# Verifies that the monthly sleep summary calculates the average
# bedtime, duration and wake-up component scores from daily sleep
# scores.
# =====================================================================


def test_monthly_summary_calculates_average_component_scores() -> None:
    first_start = _datetime(1)
    second_start = _datetime(2, 1)

    analyzer = _analyzer(
        _sleep_record(
            first_start,
            first_start + timedelta(hours=8),
        ),
        _sleep_record(
            second_start,
            second_start + timedelta(hours=7),
        ),
    )

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
# final daily sleep scores rather than from independently averaged
# parts.
# =====================================================================


def test_monthly_summary_calculates_average_total_sleep_score() -> None:
    first_start = _datetime(1)
    second_start = _datetime(2, 1)

    analyzer = _analyzer(
        _sleep_record(
            first_start,
            first_start + timedelta(hours=8),
        ),
        _sleep_record(
            second_start,
            second_start + timedelta(hours=7),
        ),
    )

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
    config = AppConfig()
    analyzer = _analyzer_for_single_sleep(
        _datetime(1),
        timedelta(hours=8),
        config=config,
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=1,
    )

    expected_bonus = next(
        (
            bonus
            for threshold, bonus in config.sleep.score.monthly_bonus.average_thresholds
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
    config = AppConfig()
    starts = [
        _datetime(1),
        _datetime(2, 0, 30),
        _datetime(3, 1),
    ]
    durations = [
        timedelta(hours=8),
        timedelta(hours=7, minutes=30),
        timedelta(hours=7),
    ]

    analyzer = _analyzer(
        *[
            _sleep_record(
                start,
                start + duration,
            )
            for start, duration in zip(
                starts,
                durations,
                strict=True,
            )
        ],
        config=config,
    )

    sleep_scores = []

    for start in starts:
        session = analyzer.session_for_day(start.date())

        assert session is not None

        sleep_scores.append(analyzer.score_session(session))

    standard_deviation = pstdev(score.total_score for score in sleep_scores)

    expected_bonus = next(
        (
            bonus
            for threshold, bonus in config.sleep.score.monthly_bonus.consistency_thresholds
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
    analyzer = _analyzer_for_single_sleep(
        _datetime(1),
        timedelta(hours=8),
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
        _datetime(1),
        _datetime(2, 0, 30),
        _datetime(3, 1),
    ]
    durations = [
        timedelta(hours=8),
        timedelta(hours=7, minutes=30),
        timedelta(hours=7),
    ]

    analyzer = _analyzer(
        *[
            _sleep_record(
                start,
                start + duration,
            )
            for start, duration in zip(
                starts,
                durations,
                strict=True,
            )
        ]
    )

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
    start = _datetime(11)

    analyzer = _analyzer(
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
    )

    session = analyzer.sleep_sessions[0]

    assert session.time_asleep_minutes == 240
    assert session.awake_minutes == 30
    assert session.time_in_bed_minutes == 270


# =====================================================================
# Verifies that sleep efficiency represents the percentage of time in
# bed that was actually spent asleep.
# =====================================================================


def test_sleep_efficiency_is_calculated_from_sleep_and_time_in_bed() -> None:
    start = _datetime(11)

    analyzer = _analyzer(
        _sleep_record(
            start,
            start + timedelta(hours=6),
        ),
        _sleep_record(
            start + timedelta(hours=6),
            start + timedelta(hours=7),
            SleepStage.AWAKE,
        ),
    )

    session = analyzer.sleep_sessions[0]

    expected_efficiency = session.time_asleep_minutes / session.time_in_bed_minutes * 100

    assert session.sleep_efficiency_percent == expected_efficiency


# =====================================================================
# Verifies that an IN_BED interval is not counted as actual sleep when
# calculating the total amount of time asleep.
# =====================================================================


def test_in_bed_stage_is_not_counted_as_sleep() -> None:
    start = _datetime(11)

    analyzer = _analyzer(
        _sleep_record(
            start,
            start + timedelta(hours=1),
            SleepStage.IN_BED,
        ),
        _sleep_record(
            start + timedelta(hours=1),
            start + timedelta(hours=7),
        ),
    )

    assert analyzer.sleep_sessions[0].time_asleep_minutes == 360


# =====================================================================
# Verifies that requesting a sleep session for a day without a primary
# sleep session returns None instead of an unrelated session.
# =====================================================================


def test_session_for_day_returns_none_when_no_session_exists() -> None:
    analyzer = _analyzer_for_single_sleep(
        _datetime(11),
        timedelta(hours=8),
    )

    assert analyzer.session_for_day(date(2026, 8, 12)) is None


# =====================================================================
# Verifies that monthly average bedtime is calculated correctly across
# midnight instead of treating late evening and early morning as
# distant times.
# =====================================================================


def test_monthly_average_bedtime_handles_midnight_correctly() -> None:
    first_start = _datetime(1, 23, 30)
    second_start = _datetime(3, 0, 30)

    analyzer = _analyzer(
        _sleep_record(
            first_start,
            first_start + timedelta(hours=8),
        ),
        _sleep_record(
            second_start,
            second_start + timedelta(hours=8),
        ),
    )

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
    score = _score_sleep(
        _datetime(11, 11, 45),
        timedelta(hours=1),
    )

    assert score.bedtime_score == 0.0


# =====================================================================
# Verifies that sufficiently large undersleep penalties cannot reduce
# the duration score below zero.
# =====================================================================


def test_duration_score_never_drops_below_zero() -> None:
    score = _score_sleep(
        _datetime(11),
        timedelta(minutes=1),
    )

    assert score.duration_score == 0.0


# =====================================================================
# Verifies that linear penalty mode applies a proportional penalty for
# deviations smaller than one full configured penalty interval.
# =====================================================================


def test_linear_penalty_mode_applies_proportional_penalty() -> None:
    config = AppConfig()
    config.sleep.score.linear_penalties = True

    bedtime_config = config.sleep.score.bedtime

    target = _datetime(
        11,
        bedtime_config.target.hour,
        bedtime_config.target.minute,
    )

    deviation_minutes = bedtime_config.penalty_interval_minutes - 1

    start = target + timedelta(minutes=deviation_minutes)

    score = _score_sleep(
        start,
        timedelta(hours=8),
        config=config,
    )

    expected_penalty = (
        deviation_minutes / bedtime_config.penalty_interval_minutes * bedtime_config.penalty_points
    )

    assert score.bedtime_score == pytest.approx(100.0 - expected_penalty)


# =====================================================================
# Verifies that disabling the monthly bonus system prevents both the
# average and consistency bonuses from being applied.
# =====================================================================


def test_monthly_bonuses_are_zero_when_disabled() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.enabled = False

    analyzer = _analyzer(
        _sleep_record(
            _datetime(1),
            _datetime(1) + timedelta(hours=8),
        ),
        _sleep_record(
            _datetime(2, 1),
            _datetime(2, 1) + timedelta(hours=7),
        ),
        config=config,
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.average_bonus == 0.0
    assert summary.consistency_bonus == 0.0
    assert summary.monthly_sleep_score == summary.average_sleep_score


# =====================================================================
# Verifies that the configured sleep-session gap threshold is injected
# into SleepAnalyzer and controls sleep-session reconstruction.
# =====================================================================


def test_uses_configured_sleep_session_gap_threshold() -> None:
    config = AppConfig()
    config.sleep.session_gap_threshold_minutes = 60

    start = _datetime(10, 23)

    analyzer = _analyzer(
        _sleep_record(
            start,
            start + timedelta(hours=2),
        ),
        _sleep_record(
            start + timedelta(hours=3),
            start + timedelta(hours=4),
        ),
        config=config,
    )

    assert len(analyzer.sleep_sessions) == 1


# =====================================================================
# Verifies that sleep source filtering requires an exact configured
# sourceName instead of accepting a longer source containing that value.
# =====================================================================


def test_sleep_source_requires_exact_match() -> None:
    config = AppConfig()
    config.source.apple_watch_source = "Custom Watch"

    analyzer = _analyzer(
        _sleep_record(
            _datetime(10, 23),
            _datetime(11, 6),
            source_name="Custom Watch Device",
        ),
        config=config,
    )

    assert analyzer.sleep_sessions == []
