from datetime import date, datetime, time, timezone

import pytest

from apple_health.models import NutritionData
from apple_health.report_models import (
    ActivityMetricsSummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
    SleepScore,
    SleepSession,
)

# =======
# Helpers
# =======


def _daily_summary(
    *,
    steps: int = 10000,
    distance_km: float = 8.0,
    active_energy_kcal: float | None = 700.0,
    basal_energy_kcal: float | None = 1900.0,
    nutrition: NutritionData | None = None,
) -> DailySummary:
    return DailySummary(
        date=date(2026, 8, 1),
        activities=[],
        total_duration_minutes=0.0,
        total_active_energy_kcal=0.0,
        total_steps=steps,
        total_distance_km=distance_km,
        active_energy_kcal=active_energy_kcal,
        basal_energy_kcal=basal_energy_kcal,
        nutrition=nutrition,
    )


def _activity_metrics(
    *,
    start_weight: float | None = 80.0,
    end_weight: float | None = 79.0,
    average_active_energy_kcal: tuple[float, int] | None = (700.0, 10),
    average_basal_energy_kcal: tuple[float, int] | None = (1900.0, 10),
    average_tdee_kcal: tuple[float, int] | None = (2600.0, 10),
    average_calories_kcal: tuple[float, int] | None = (2000.0, 10),
    average_calories_balance_kcal: tuple[float, int] | None = (-550.0, 10),
) -> ActivityMetricsSummary:
    return ActivityMetricsSummary(
        total_steps=10000,
        average_daily_steps=10000.0,
        total_distance_km=8.0,
        average_daily_distance_km=8.0,
        average_step_length_cm=80.0,
        average_basal_energy_kcal=average_basal_energy_kcal,
        average_active_energy_kcal=average_active_energy_kcal,
        average_tdee_kcal=average_tdee_kcal,
        average_weight=79.5,
        start_weight=start_weight,
        end_weight=end_weight,
        max_weight=80.0,
        min_weight=79.0,
        measurements=2,
        average_protein_g=(150.0, 10),
        average_carbohydrates_g=(200.0, 10),
        average_fat_g=(70.0, 10),
        average_calories_kcal=average_calories_kcal,
        average_calories_balance_kcal=average_calories_balance_kcal,
    )


def _sleep_summary() -> SleepMonthlySummary:
    return SleepMonthlySummary(
        total_sessions=1,
        average_bedtime=time(0, 0),
        average_wake_up=time(8, 0),
        average_sleep_minutes=480.0,
        average_awake_minutes=0.0,
        average_sleep_efficiency=100.0,
        average_core_minutes=300.0,
        average_deep_minutes=60.0,
        average_rem_minutes=120.0,
        average_bedtime_score=100.0,
        average_duration_score=100.0,
        average_wake_up_score=100.0,
        average_sleep_score=100.0,
    )


# =====================================================================
# Verifies that average step length is calculated from total distance
# and step count and converted from kilometres to centimetres.
# =====================================================================


def test_daily_summary_calculates_average_step_length() -> None:
    summary = _daily_summary(
        steps=10000,
        distance_km=8.0,
    )

    assert summary.average_step_length_cm == 80.0


# =====================================================================
# Verifies that average step length is zero when no steps are
# available, preventing division by zero.
# =====================================================================


def test_daily_summary_average_step_length_is_zero_without_steps() -> None:
    summary = _daily_summary(
        steps=0,
        distance_km=0.0,
    )

    assert summary.average_step_length_cm == 0.0


# =====================================================================
# Verifies that daily TDEE is calculated as the sum of active and basal
# energy expenditure.
# =====================================================================


def test_daily_summary_calculates_tdee() -> None:
    summary = _daily_summary(
        active_energy_kcal=700.0,
        basal_energy_kcal=1900.0,
    )

    assert summary.tdee_kcal == 2600.0


# =====================================================================
# Verifies that daily TDEE remains unavailable when either required
# energy component is missing.
# =====================================================================


@pytest.mark.parametrize(
    ("active_energy_kcal", "basal_energy_kcal"),
    [
        (None, 1900.0),
        (700.0, None),
        (None, None),
    ],
)
def test_daily_summary_tdee_is_none_when_energy_is_incomplete(
    active_energy_kcal: float | None,
    basal_energy_kcal: float | None,
) -> None:
    summary = _daily_summary(
        active_energy_kcal=active_energy_kcal,
        basal_energy_kcal=basal_energy_kcal,
    )

    assert summary.tdee_kcal is None


# =====================================================================
# Verifies that daily calorie balance is calculated as consumed
# calories minus total daily energy expenditure.
# =====================================================================


def test_daily_summary_calculates_calorie_balance() -> None:
    nutrition = NutritionData(
        calories_kcal=2000.0,
        protein_g=150.0,
        carbohydrates_g=200.0,
        fat_g=70.0,
    )

    summary = _daily_summary(
        active_energy_kcal=700.0,
        basal_energy_kcal=1900.0,
        nutrition=nutrition,
    )

    assert summary.calories_balance_kcal == -600.0


# =====================================================================
# Verifies that daily calorie balance is unavailable when no nutrition
# data exists for the day.
# =====================================================================


def test_daily_summary_calorie_balance_is_none_without_nutrition() -> None:
    summary = _daily_summary(
        nutrition=None,
    )

    assert summary.calories_balance_kcal is None


# =====================================================================
# Verifies that daily calorie balance remains unavailable when the
# nutrition section exists but the calorie value is missing.
# =====================================================================


def test_daily_summary_calorie_balance_is_none_without_calories() -> None:
    summary = _daily_summary(
        nutrition=NutritionData(
            protein_g=150.0,
        ),
    )

    assert summary.calories_balance_kcal is None


# =====================================================================
# Verifies that daily calorie balance remains unavailable when calorie
# intake exists but TDEE cannot be calculated from complete energy data.
# =====================================================================


@pytest.mark.parametrize(
    ("active_energy_kcal", "basal_energy_kcal"),
    [
        (None, 1900.0),
        (700.0, None),
    ],
)
def test_daily_summary_calorie_balance_is_none_when_energy_is_incomplete(
    active_energy_kcal: float | None,
    basal_energy_kcal: float | None,
) -> None:
    summary = _daily_summary(
        active_energy_kcal=active_energy_kcal,
        basal_energy_kcal=basal_energy_kcal,
        nutrition=NutritionData(
            calories_kcal=2000.0,
        ),
    )

    assert summary.calories_balance_kcal is None


# =====================================================================
# Verifies that MonthlySummary exposes the final completed reporting
# day as the date through which monthly data is available.
# =====================================================================


def test_monthly_summary_calculates_data_through() -> None:
    summary = MonthlySummary(
        year=2026,
        month=8,
        reporting_days=14,
        days=[],
        activities=[],
        activity_metrics=_activity_metrics(),
        sleep_summary=_sleep_summary(),
    )

    assert summary.data_through == date(
        2026,
        8,
        14,
    )


# =====================================================================
# Verifies that a monthly summary with no completed reporting days does
# not expose a data-through date.
# =====================================================================


def test_monthly_summary_data_through_is_none_without_reporting_days() -> None:
    summary = MonthlySummary(
        year=2026,
        month=8,
        reporting_days=0,
        days=[],
        activities=[],
        activity_metrics=_activity_metrics(),
        sleep_summary=_sleep_summary(),
    )

    assert summary.data_through is None


# =====================================================================
# Verifies that the activity metrics summary preserves monthly TDEE
# together with the number of contributing days.
# =====================================================================


def test_activity_metrics_summary_preserves_average_tdee() -> None:
    summary = _activity_metrics(
        average_tdee_kcal=(2600.0, 10),
    )

    assert summary.average_tdee_kcal == (2600.0, 10)


# =====================================================================
# Verifies that body-weight change is calculated as end weight minus
# start weight when both measurements are available.
# =====================================================================


def test_activity_metrics_summary_calculates_weight_change() -> None:
    summary = _activity_metrics(
        start_weight=80.0,
        end_weight=78.5,
    )

    assert summary.weight_change == -1.5


# =====================================================================
# Verifies that monthly weight change is unavailable when either
# endpoint measurement is missing.
# =====================================================================


@pytest.mark.parametrize(
    ("start_weight", "end_weight"),
    [
        (None, 79.0),
        (80.0, None),
    ],
)
def test_activity_metrics_summary_weight_change_is_none_when_incomplete(
    start_weight: float | None,
    end_weight: float | None,
) -> None:
    summary = _activity_metrics(
        start_weight=start_weight,
        end_weight=end_weight,
    )

    assert summary.weight_change is None


# =====================================================================
# Verifies that the activity metrics summary preserves the monthly
# calorie balance together with the number of contributing days.
# =====================================================================


def test_activity_metrics_summary_preserves_average_calorie_balance() -> None:
    summary = _activity_metrics(
        average_calories_balance_kcal=(-550.0, 10),
    )

    assert summary.average_calories_balance_kcal == (-550.0, 10)


# =====================================================================
# Verifies that sleep efficiency is calculated as the percentage of
# time in bed that was actually spent asleep.
# =====================================================================


def test_sleep_session_calculates_sleep_efficiency() -> None:
    session = SleepSession(
        bedtime=datetime(
            2026,
            8,
            1,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        wake_up=datetime(
            2026,
            8,
            1,
            8,
            0,
            tzinfo=timezone.utc,
        ),
        records=[],
        time_in_bed_minutes=480.0,
        time_asleep_minutes=450.0,
        core_minutes=300.0,
        deep_minutes=60.0,
        rem_minutes=90.0,
        awake_minutes=30.0,
    )

    assert session.sleep_efficiency_percent == pytest.approx(93.75)


# =====================================================================
# Verifies that sleep sessions beginning before noon belong to the same
# calendar day for reporting purposes.
# =====================================================================


def test_sleep_session_before_noon_uses_same_reporting_date() -> None:
    bedtime = datetime(
        2026,
        8,
        1,
        1,
        0,
        tzinfo=timezone.utc,
    )

    session = SleepSession(
        bedtime=bedtime,
        wake_up=bedtime,
        records=[],
        time_in_bed_minutes=0.0,
        time_asleep_minutes=0.0,
        core_minutes=0.0,
        deep_minutes=0.0,
        rem_minutes=0.0,
        awake_minutes=0.0,
    )

    assert session.reporting_date == date(
        2026,
        8,
        1,
    )


# =====================================================================
# Verifies that sleep sessions beginning at noon or later belong to the
# following calendar day for reporting purposes.
# =====================================================================


def test_sleep_session_at_noon_uses_next_reporting_date() -> None:
    bedtime = datetime(
        2026,
        8,
        1,
        12,
        0,
        tzinfo=timezone.utc,
    )

    session = SleepSession(
        bedtime=bedtime,
        wake_up=bedtime,
        records=[],
        time_in_bed_minutes=0.0,
        time_asleep_minutes=0.0,
        core_minutes=0.0,
        deep_minutes=0.0,
        rem_minutes=0.0,
        awake_minutes=0.0,
    )

    assert session.reporting_date == date(
        2026,
        8,
        2,
    )


# =====================================================================
# Verifies that the monthly Sleep Score combines the average daily
# score with both configured monthly bonuses.
# =====================================================================


def test_sleep_monthly_summary_combines_score_and_bonuses() -> None:
    summary = _sleep_summary()

    summary.average_sleep_score = 75.0
    summary.average_bonus = 10.0
    summary.consistency_bonus = 5.0

    assert summary.monthly_sleep_score == 90.0


# =====================================================================
# Verifies that the final daily Sleep Score is calculated as the
# weighted average of its three configured component scores.
# =====================================================================


def test_sleep_score_preserves_total_score() -> None:
    score = SleepScore(
        bedtime_score=80.0,
        duration_score=90.0,
        wake_up_score=70.0,
        total_score=81.5,
    )

    assert score.total_score == 81.5
