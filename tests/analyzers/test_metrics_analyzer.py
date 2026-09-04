from datetime import date, datetime, timezone

import pytest

from health_analyzer.analyzers.metrics_analyzer import MetricsAnalyzer
from health_analyzer.models import (
    HealthData,
    DailyMetrics,
    NutritionData,
    WeightMeasurement,
)


def _metrics(
    day: int,
    *,
    steps: int | None = None,
    distance_km: float | None = None,
    active_energy: float | None = None,
    basal_energy: float | None = None,
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
    calories_kcal: float | None = None,
    protein_g: float | None = None,
    carbohydrates_g: float | None = None,
    fat_g: float | None = None,
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
        HealthData(
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

    assert summary.average_daily_steps == (
        7500.0,
        2,
    )

    assert summary.average_daily_distance_km == (
        6.0,
        2,
    )


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

    assert summary.average_basal_energy_kcal == (1950.0, 2)
    assert summary.average_active_energy_kcal == (700.0, 2)
    assert summary.average_tdee_kcal == (2650.0, 2)


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

    assert summary.average_step_length_cm == (
        80.0,
        1,
    )


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

    assert summary.average_step_length_cm == (
        0.0,
        1,
    )


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


# =====================================================================
# Verifies that missing nutrition data remains unavailable instead of
# being represented as zero-valued monthly nutrition.
# =====================================================================


def test_summarize_month_preserves_missing_nutrition() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            active_energy=600,
            basal_energy=1800,
            nutrition=None,
        ),
        _metrics(
            2,
            active_energy=700,
            basal_energy=1900,
            nutrition=None,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=2,
    )

    assert summary.average_calories_kcal is None
    assert summary.average_protein_g is None
    assert summary.average_carbohydrates_g is None
    assert summary.average_fat_g is None
    assert summary.average_calories_balance_kcal is None


# =====================================================================
# Verifies that missing nutrition days are excluded from nutrition
# averages instead of being treated as days with zero intake.
# =====================================================================


def test_summarize_month_averages_nutrition_only_across_available_days() -> None:
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

    assert summary.average_calories_kcal == (2100.0, 2)
    assert summary.average_protein_g == (160.0, 2)
    assert summary.average_carbohydrates_g == (210.0, 2)
    assert summary.average_fat_g == (75.0, 2)


# =====================================================================
# Verifies that monthly calorie balance is averaged only across days
# with available calorie intake data.
# =====================================================================


def test_summarize_month_calculates_calorie_balance_only_for_available_days() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            active_energy=500,
            basal_energy=1500,
            nutrition=_nutrition(
                calories_kcal=2500,
            ),
        ),
        _metrics(
            2,
            active_energy=1000,
            basal_energy=2000,
            nutrition=None,
        ),
        _metrics(
            3,
            active_energy=600,
            basal_energy=1600,
            nutrition=_nutrition(
                calories_kcal=2000,
            ),
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_tdee_kcal == (2400.0, 3)
    assert summary.average_calories_kcal == (2250.0, 2)
    assert summary.average_calories_balance_kcal == (150.0, 2)


# =====================================================================
# Verifies that basal, active and TDEE averages use their own coverage,
# with TDEE requiring both energy components on the same day.
# =====================================================================


def test_summarize_month_uses_independent_energy_coverage() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            basal_energy=1500,
            active_energy=500,
        ),
        _metrics(
            2,
            basal_energy=1600,
            active_energy=None,
        ),
        _metrics(
            3,
            basal_energy=None,
            active_energy=700,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_basal_energy_kcal == (1550.0, 2)
    assert summary.average_active_energy_kcal == (600.0, 2)
    assert summary.average_tdee_kcal == (2000.0, 1)


# =====================================================================
# Verifies that each monthly nutrition average uses only days where that
# specific nutrient is available.
# =====================================================================


def test_summarize_month_uses_independent_nutrition_coverage() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            nutrition=_nutrition(
                calories_kcal=2000,
                protein_g=100,
                fat_g=70,
            ),
        ),
        _metrics(
            2,
            nutrition=_nutrition(
                protein_g=120,
                carbohydrates_g=250,
            ),
        ),
        _metrics(
            3,
            nutrition=_nutrition(
                calories_kcal=2400,
                carbohydrates_g=300,
                fat_g=80,
            ),
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=3,
    )

    assert summary.average_calories_kcal == (2200.0, 2)
    assert summary.average_protein_g == (110.0, 2)
    assert summary.average_carbohydrates_g == (275.0, 2)
    assert summary.average_fat_g == (75.0, 2)


# =====================================================================
# Verifies that monthly calorie balance uses only days where calories,
# basal energy and active energy are all available together.
# =====================================================================


def test_summarize_month_uses_complete_daily_coverage_for_calorie_balance() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            basal_energy=1500,
            active_energy=500,
            nutrition=_nutrition(calories_kcal=2500),
        ),
        _metrics(
            2,
            basal_energy=2000,
            active_energy=None,
            nutrition=_nutrition(calories_kcal=2900),
        ),
        _metrics(
            3,
            basal_energy=1600,
            active_energy=600,
            nutrition=_nutrition(calories_kcal=None),
        ),
        _metrics(
            4,
            basal_energy=1400,
            active_energy=400,
            nutrition=_nutrition(calories_kcal=1800),
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=4,
    )

    assert summary.average_calories_kcal == (2400.0, 3)
    assert summary.average_tdee_kcal == (2000.0, 3)
    assert summary.average_calories_balance_kcal == (250.0, 2)


# =====================================================================
# Verifies that steps, distance and step length preserve independent
# data coverage instead of treating missing activity records as zero.
# =====================================================================


def test_summarize_month_preserves_independent_activity_coverage() -> None:
    analyzer = _analyzer(
        _metrics(
            1,
            steps=5000,
            distance_km=4.0,
        ),
        _metrics(
            2,
            nutrition=_nutrition(
                calories_kcal=2000,
            ),
        ),
        _metrics(
            3,
            steps=7000,
        ),
        _metrics(
            4,
            distance_km=6.0,
        ),
    )

    summary = analyzer.summarize_month(
        year=2026,
        month=8,
        reporting_days=4,
    )

    assert summary.total_steps == 12000
    assert summary.average_daily_steps == (
        6000.0,
        2,
    )

    assert summary.total_distance_km == 10.0
    assert summary.average_daily_distance_km == (
        5.0,
        2,
    )

    assert summary.average_step_length_cm == (
        80.0,
        1,
    )
