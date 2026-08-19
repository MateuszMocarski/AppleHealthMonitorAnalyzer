from datetime import date, datetime, timedelta, timezone

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import SleepStage, WorkoutType
from apple_health.models import (
    AppleHealthData,
    DailyMetrics,
    NutritionData,
    SleepRecord,
    WeightMeasurement,
    Workout,
)


def _daily_metrics(
    day: int,
    *,
    steps: int = 0,
    distance_km: float = 0.0,
    active_energy: float = 0.0,
    basal_energy: float = 0.0,
    weight: float | None = None,
    nutrition: NutritionData | None = None,
) -> DailyMetrics:
    measurement = None

    if weight is not None:
        measurement = WeightMeasurement(
            value=weight,
            timestamp=datetime(
                2026,
                8,
                day,
                8,
                0,
                tzinfo=timezone.utc,
            ),
            is_user_entered=True,
        )

    return DailyMetrics(
        date=date(2026, 8, day),
        steps=steps,
        distance_km=distance_km,
        active_energy=active_energy,
        basal_energy=basal_energy,
        weight=measurement,
        nutrition=nutrition,
    )


def _workout(
    day: int,
    *,
    duration_minutes: float,
    active_energy_kcal: float,
) -> Workout:
    start = datetime(
        2026,
        8,
        day,
        18,
        0,
        tzinfo=timezone.utc,
    )

    return Workout(
        apple_activity_type="test",
        activity_type=WorkoutType.WALKING,
        source_name="test",
        source_version=None,
        start=start,
        end=start,
        duration_minutes=duration_minutes,
        active_energy_kcal=active_energy_kcal,
        distance_km=5.0,
    )


def _sleep_record(
    start: datetime,
    end: datetime,
) -> SleepRecord:
    return SleepRecord(
        stage=SleepStage.CORE,
        source_name=APPLE_WATCH_SOURCE,
        source_version=None,
        start=start,
        end=end,
        duration_minutes=(end - start).total_seconds() / 60,
    )


def _health_data(
    *,
    daily_metrics: list[DailyMetrics],
    workouts: list[Workout] | None = None,
    sleep_records: list[SleepRecord] | None = None,
) -> AppleHealthData:
    return AppleHealthData(
        workouts=workouts or [],
        daily_metrics=daily_metrics,
        sleep_records=sleep_records or [],
    )


# =====================================================================
# Verifies that summarize_day combines daily metrics into a complete
# DailySummary with activity, energy, body weight and nutrition data.
# =====================================================================


def test_summarize_day_combines_daily_metrics() -> None:
    nutrition = NutritionData(
        calories_kcal=2000,
        protein_g=150,
        carbohydrates_g=200,
        fat_g=70,
    )

    analyzer = HealthAnalyzer(
        _health_data(
            daily_metrics=[
                _daily_metrics(
                    1,
                    steps=10000,
                    distance_km=8.0,
                    active_energy=700,
                    basal_energy=1900,
                    weight=80.0,
                    nutrition=nutrition,
                )
            ],
            workouts=[
                _workout(
                    1,
                    duration_minutes=60,
                    active_energy_kcal=400,
                )
            ],
        )
    )

    summary = analyzer.summarize_day(date(2026, 8, 1))

    assert summary.total_steps == 10000
    assert summary.total_distance_km == 8.0
    assert summary.active_energy_kcal == 700
    assert summary.basal_energy_kcal == 1900
    assert summary.weight == 80.0
    assert summary.nutrition is nutrition
    assert summary.total_duration_minutes == 60
    assert summary.total_active_energy_kcal == 400


# =====================================================================
# Verifies that summarize_day returns safe default values when no
# DailyMetrics object exists for the requested day.
# =====================================================================


def test_summarize_day_uses_defaults_when_metrics_are_missing() -> None:
    analyzer = HealthAnalyzer(_health_data(daily_metrics=[_daily_metrics(2)]))

    summary = analyzer.summarize_day(date(2026, 8, 1))

    assert summary.total_steps == 0
    assert summary.total_distance_km == 0.0
    assert summary.active_energy_kcal == 0.0
    assert summary.basal_energy_kcal == 0.0
    assert summary.weight is None
    assert summary.nutrition is None


# =====================================================================
# Verifies that a primary sleep session and its calculated SleepScore
# are attached to the corresponding DailySummary.
# =====================================================================


def test_summarize_day_includes_sleep_session_and_score() -> None:
    sleep_start = datetime(
        2026,
        8,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = HealthAnalyzer(
        _health_data(
            daily_metrics=[
                _daily_metrics(1),
                _daily_metrics(2),
            ],
            sleep_records=[
                _sleep_record(
                    sleep_start,
                    sleep_start.replace(hour=8),
                )
            ],
        )
    )

    summary = analyzer.summarize_day(date(2026, 8, 1))

    assert summary.sleep_session is not None
    assert summary.sleep_score is not None


# =====================================================================
# Verifies that the reporting period for the latest data month ends on
# the day before the final day containing any imported metrics.
# =====================================================================


def test_reporting_days_excludes_last_data_day() -> None:
    analyzer = HealthAnalyzer(
        _health_data(
            daily_metrics=[
                _daily_metrics(14),
                _daily_metrics(15),
            ]
        )
    )

    assert (
        analyzer._reporting_days(
            2026,
            8,
        )
        == 14
    )


# =====================================================================
# Verifies that a month preceding the latest complete-data month uses
# the full number of calendar days as its reporting period.
# =====================================================================


def test_reporting_days_returns_full_historical_month() -> None:
    analyzer = HealthAnalyzer(_health_data(daily_metrics=[_daily_metrics(15)]))

    assert (
        analyzer._reporting_days(
            2026,
            7,
        )
        == 31
    )


# =====================================================================
# Verifies that a month occurring after the latest available complete
# data period contains zero reporting days.
# =====================================================================


def test_reporting_days_returns_zero_for_future_data_month() -> None:
    analyzer = HealthAnalyzer(_health_data(daily_metrics=[_daily_metrics(15)]))

    assert (
        analyzer._reporting_days(
            2026,
            9,
        )
        == 0
    )


# =====================================================================
# Verifies that summarize_month builds a MonthlySummary using only
# completed reporting days and includes delegated analyzer results.
# =====================================================================


def test_summarize_month_builds_complete_monthly_summary() -> None:
    first_sleep_start = datetime(
        2026,
        8,
        1,
        0,
        0,
        tzinfo=timezone.utc,
    )

    second_sleep_start = datetime(
        2026,
        8,
        2,
        0,
        0,
        tzinfo=timezone.utc,
    )

    analyzer = HealthAnalyzer(
        _health_data(
            daily_metrics=[
                _daily_metrics(
                    1,
                    steps=10000,
                ),
                _daily_metrics(
                    2,
                    steps=12000,
                ),
                _daily_metrics(
                    3,
                    steps=50000,
                ),
            ],
            sleep_records=[
                _sleep_record(
                    first_sleep_start,
                    first_sleep_start + timedelta(hours=8),
                ),
                _sleep_record(
                    second_sleep_start,
                    second_sleep_start + timedelta(hours=8),
                ),
            ],
        )
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
    )

    assert summary.year == 2026
    assert summary.month == 8
    assert summary.reporting_days == 2
    assert len(summary.days) == 2

    assert summary.activity_metrics.total_steps == 22000
    assert summary.activities == []
    assert summary.sleep_summary is not None
