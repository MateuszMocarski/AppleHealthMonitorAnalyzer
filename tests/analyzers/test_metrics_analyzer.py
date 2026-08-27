from datetime import date, datetime, timezone

import pytest

from apple_health.analyzers.metrics_analyzer import MetricsAnalyzer
from apple_health.models import (
    AppleHealthData,
    DailyMetrics,
    NutritionData,
    WeightMeasurement,
)


def _metrics(
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


def _nutrition(
    *,
    calories_kcal: float = 0.0,
    protein_g: float = 0.0,
    carbohydrates_g: float = 0.0,
    fat_g: float = 0.0,
) -> NutritionData:
    return NutritionData(
        calories_kcal=calories_kcal,
        protein_g=protein_g,
        carbohydrates_g=carbohydrates_g,
        fat_g=fat_g,
    )


def _analyzer(
    *daily_metrics: DailyMetrics,
) -> MetricsAnalyzer:
    return MetricsAnalyzer(
        AppleHealthData(
            workouts=[],
            daily_metrics=list(daily_metrics),
            sleep_records=[],
        )
    )


# =====================================================================
# Verifies that metrics_for_day returns the DailyMetrics object
# assigned to the requested calendar day.
# =====================================================================


def test_metrics_for_day_returns_matching_metrics() -> None:
    metrics = _metrics(
        1,
        steps=10000,
    )

    analyzer = _analyzer(metrics)

    result = analyzer.metrics_for_day(date(2026, 8, 1))

    assert result is metrics


# =====================================================================
# Verifies that requesting metrics for a day without recorded data
# returns None instead of an unrelated DailyMetrics object.
# =====================================================================


def test_metrics_for_day_returns_none_when_no_metrics_exist() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=10000,
        )
    )

    assert analyzer.metrics_for_day(date(2026, 8, 2)) is None


# =====================================================================
# Verifies that monthly metrics include only records within the
# requested reporting-day range.
# =====================================================================


def test_summarize_month_respects_reporting_days() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=10000,
        ),
        _metrics(
            2,
            steps=12000,
        ),
        _metrics(
            3,
            steps=50000,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.total_steps == 22000


# =====================================================================
# Verifies that monthly step count and walking/running distance are
# calculated as the sum of all included daily metric records.
# =====================================================================


def test_summarize_month_calculates_step_and_distance_totals() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=10000,
            distance_km=8.0,
        ),
        _metrics(
            2,
            steps=5000,
            distance_km=4.0,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.total_steps == 15000
    assert summary.total_distance_km == 12.0


# =====================================================================
# Verifies that monthly daily averages for steps and distance are based
# on the number of completed reporting days.
# =====================================================================


def test_summarize_month_calculates_daily_activity_averages() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=10000,
            distance_km=8.0,
        ),
        _metrics(
            2,
            steps=5000,
            distance_km=4.0,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_daily_steps == 5000.0
    assert summary.average_daily_distance_km == 4.0


# =====================================================================
# Verifies that basal and active energy averages are calculated across
# the complete reporting period.
# =====================================================================


def test_summarize_month_calculates_energy_averages() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            basal_energy=1900,
            active_energy=600,
        ),
        _metrics(
            2,
            basal_energy=2000,
            active_energy=800,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.average_basal_energy_kcal == 1950.0
    assert summary.average_active_energy_kcal == 700.0


# =====================================================================
# Verifies that average step length is calculated from the total
# monthly walking/running distance and total number of steps.
# =====================================================================


def test_summarize_month_calculates_average_step_length() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=10000,
            distance_km=8.0,
        )
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=1,
    )

    assert summary.average_step_length_cm == 80.0


# =====================================================================
# Verifies that average step length is zero when no steps are
# available, avoiding division by zero.
# =====================================================================


def test_average_step_length_is_zero_when_no_steps_exist() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=0,
            distance_km=0.0,
        )
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=1,
    )

    assert summary.average_step_length_cm == 0.0


# =====================================================================
# Verifies that nutrition values are summed from available daily
# records and averaged across all completed reporting days.
# =====================================================================


def test_summarize_month_calculates_nutrition_averages() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            nutrition=_nutrition(
                calories_kcal=2000,
                protein_g=150,
                carbohydrates_g=200,
                fat_g=70,
            ),
        ),
        _metrics(
            2,
            nutrition=_nutrition(
                calories_kcal=2200,
                protein_g=170,
                carbohydrates_g=220,
                fat_g=80,
            ),
        ),
        _metrics(
            3,
            nutrition=None,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_calories_kcal == 1400.0
    assert summary.average_protein_g == pytest.approx(320 / 3)
    assert summary.average_carbohydrates_g == 140.0
    assert summary.average_fat_g == 50.0


# =====================================================================
# Verifies that monthly body-weight statistics include average, first,
# last, minimum, maximum and measurement count.
# =====================================================================


def test_summarize_month_calculates_weight_statistics() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            weight=80.0,
        ),
        _metrics(
            2,
            weight=79.5,
        ),
        _metrics(
            3,
            weight=81.0,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_weight == pytest.approx(80.1666666667)
    assert summary.start_weight == 80.0
    assert summary.end_weight == 81.0
    assert summary.min_weight == 79.5
    assert summary.max_weight == 81.0
    assert summary.measurements == 3


# =====================================================================
# Verifies that all optional body-weight statistics remain None when
# the reporting period contains no weight measurements.
# =====================================================================


def test_weight_statistics_are_empty_when_no_measurements_exist() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=10000,
        ),
        _metrics(
            2,
            steps=12000,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.average_weight is None
    assert summary.start_weight is None
    assert summary.end_weight is None
    assert summary.min_weight is None
    assert summary.max_weight is None
    assert summary.measurements == 0
