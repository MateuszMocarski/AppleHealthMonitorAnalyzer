from datetime import datetime, timezone

from health_analyzer.analyzers.activity_analyzer import ActivityAnalyzer
from health_analyzer.enums import WorkoutType
from health_analyzer.models import HealthData, Workout


def _workout(
    day: int,
    activity_type: WorkoutType,
    duration_minutes: float,
    active_energy_kcal: float | None,
    distance_km: float | None,
) -> Workout:
    start = datetime(
        2026,
        8,
        day,
        10,
        0,
        tzinfo=timezone.utc,
    )

    return Workout(
        apple_activity_type="test",
        activity_type=activity_type,
        source_name="test",
        source_version=None,
        start=start,
        end=start,
        duration_minutes=duration_minutes,
        active_energy_kcal=active_energy_kcal,
        distance_km=distance_km,
    )


def _analyzer(
    *workouts: Workout,
) -> ActivityAnalyzer:
    return ActivityAnalyzer(
        HealthData(
            workouts=list(workouts),
            daily_metrics=[],
            sleep_records=[],
        )
    )


# =====================================================================
# Verifies that workouts are grouped by their start date and workouts
# recorded on the same calendar day belong to the same activity day.
# =====================================================================


def test_groups_workouts_by_day() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        ),
        _workout(
            1,
            WorkoutType.INDOOR_CYCLING,
            45,
            400,
            None,
        ),
        _workout(
            2,
            WorkoutType.WALKING,
            30,
            150,
            2.5,
        ),
    )

    workouts_by_day = analyzer.workouts_by_day()

    assert len(workouts_by_day) == 2
    assert len(workouts_by_day[datetime(2026, 8, 1).date()]) == 2
    assert len(workouts_by_day[datetime(2026, 8, 2).date()]) == 1


# =====================================================================
# Verifies that active_days returns the number of unique calendar days
# containing at least one recorded workout.
# =====================================================================


def test_active_days_counts_unique_workout_days() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        ),
        _workout(
            1,
            WorkoutType.WALKING,
            30,
            150,
            2.5,
        ),
        _workout(
            3,
            WorkoutType.INDOOR_CYCLING,
            45,
            400,
            None,
        ),
    )

    assert analyzer.active_days() == 2


# =====================================================================
# Verifies that requesting workouts for a day without recorded activity
# returns an empty list instead of raising an error.
# =====================================================================


def test_workouts_for_day_returns_empty_list_when_no_workouts_exist() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        )
    )

    workouts = analyzer.workouts_for_day(datetime(2026, 8, 2).date())

    assert workouts == []


# =====================================================================
# Verifies that daily workouts of the same activity type are aggregated
# into one summary with combined sessions, duration, energy and
# distance.
# =====================================================================


def test_summarize_day_aggregates_workouts_by_activity_type() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        ),
        _workout(
            1,
            WorkoutType.WALKING,
            30,
            150,
            2.5,
        ),
    )

    summaries = analyzer.summarize_day(datetime(2026, 8, 1).date())

    assert len(summaries) == 1

    summary = summaries[0]

    assert summary.activity_type == WorkoutType.WALKING
    assert summary.sessions == 2
    assert summary.duration_minutes == 90
    assert summary.active_energy_kcal == 450
    assert summary.distance_km == 7.5


# =====================================================================
# Verifies that different workout types recorded on the same day are
# represented by separate daily activity summaries.
# =====================================================================


def test_summarize_day_keeps_activity_types_separate() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        ),
        _workout(
            1,
            WorkoutType.INDOOR_CYCLING,
            45,
            400,
            None,
        ),
    )

    summaries = analyzer.summarize_day(datetime(2026, 8, 1).date())

    assert len(summaries) == 2

    activity_types = {summary.activity_type for summary in summaries}

    assert activity_types == {
        WorkoutType.WALKING,
        WorkoutType.INDOOR_CYCLING,
    }


# =====================================================================
# Verifies that an activity summary keeps distance as None when none of
# the aggregated workouts contain distance data.
# =====================================================================


def test_activity_summary_distance_is_none_when_no_distance_exists() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.INDOOR_CYCLING,
            45,
            400,
            None,
        ),
        _workout(
            1,
            WorkoutType.INDOOR_CYCLING,
            30,
            250,
            None,
        ),
    )

    summary = analyzer.summarize_day(datetime(2026, 8, 1).date())[0]

    assert summary.distance_km is None


# =====================================================================
# Verifies that aggregated workout distance remains missing when any
# workout in the activity group has no distance measurement.
# =====================================================================


def test_activity_summary_distance_is_none_when_any_workout_distance_is_missing() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.INDOOR_CYCLING,
            45,
            400,
            10.0,
        ),
        _workout(
            1,
            WorkoutType.INDOOR_CYCLING,
            30,
            250,
            None,
        ),
    )

    summary = analyzer.summarize_day(datetime(2026, 8, 1).date())[0]

    assert summary.distance_km is None


# =====================================================================
# Verifies that monthly activity summaries include only workouts within
# the requested month and completed reporting-day range.
# =====================================================================


def test_summarize_month_respects_reporting_days() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        ),
        _workout(
            2,
            WorkoutType.WALKING,
            30,
            150,
            2.5,
        ),
        _workout(
            3,
            WorkoutType.WALKING,
            120,
            600,
            10,
        ),
    )

    summaries = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert len(summaries) == 1

    summary = summaries[0]

    assert summary.sessions == 2
    assert summary.duration_minutes == 90
    assert summary.active_energy_kcal == 450
    assert summary.distance_km == 7.5


# =====================================================================
# Verifies that aggregated workout energy remains missing when any
# workout in the activity group has no active-energy measurement.
# =====================================================================


def test_activity_summary_energy_is_none_when_any_workout_energy_is_missing() -> None:
    analyzer = _analyzer(
        _workout(
            1,
            WorkoutType.WALKING,
            60,
            300,
            5,
        ),
        _workout(
            1,
            WorkoutType.WALKING,
            30,
            None,
            2.5,
        ),
    )

    summary = analyzer.summarize_day(datetime(2026, 8, 1).date())[0]

    assert summary.active_energy_kcal is None
