import json
from datetime import date, time

import pytest

from apple_health.enums import WorkoutType
from apple_health.report_models import (
    ActivityMetricsSummary,
    ActivitySummary,
    MonthlySummary,
    SleepMonthlySummary,
)
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.sleep_score_config import (
    SLEEP_MONTHLY_BONUS_MAX_POINTS,
)


# =======
# Helpers
# =======


def _activity_metrics(
    *,
    total_steps: int | None = 122_192,
    average_daily_steps: float | None = 8728.0,
    total_distance_km: float | None = 100.5498755962,
    average_daily_distance_km: float | None = 7.1821339711,
    average_step_length_cm: float | None = 82.2884277172,
    average_basal_energy_kcal: float | None = 1944.7069285715,
    average_active_energy_kcal: float | None = 752.9383571428,
    average_weight: float | None = 79.4535714285,
    start_weight: float | None = 80.1,
    end_weight: float | None = 78.75,
    max_weight: float | None = 80.2,
    min_weight: float | None = 78.75,
    measurements: int = 14,
    average_protein_g: float | None = 154.7142857142,
    average_carbohydrates_g: float | None = 193.7857142857,
    average_fat_g: float | None = 72.7857142857,
    average_calories_kcal: float | None = 2052.1428571428,
) -> ActivityMetricsSummary:
    return ActivityMetricsSummary(
        total_steps=total_steps,
        average_daily_steps=average_daily_steps,
        total_distance_km=total_distance_km,
        average_daily_distance_km=average_daily_distance_km,
        average_step_length_cm=average_step_length_cm,
        average_basal_energy_kcal=average_basal_energy_kcal,
        average_active_energy_kcal=average_active_energy_kcal,
        average_weight=average_weight,
        start_weight=start_weight,
        end_weight=end_weight,
        max_weight=max_weight,
        min_weight=min_weight,
        measurements=measurements,
        average_protein_g=average_protein_g,
        average_carbohydrates_g=average_carbohydrates_g,
        average_fat_g=average_fat_g,
        average_calories_kcal=average_calories_kcal,
    )


def _sleep_summary() -> SleepMonthlySummary:
    return SleepMonthlySummary(
        total_sessions=14,
        average_bedtime=time(1, 45),
        average_wake_up=time(8, 56),
        average_sleep_minutes=412.6166666667,
        average_awake_minutes=18.4547619048,
        average_sleep_efficiency=95.9837689863,
        average_core_minutes=289.2523809524,
        average_deep_minutes=34.6488095238,
        average_rem_minutes=88.7154761905,
        average_bedtime_score=67.5,
        average_duration_score=81.7857142857,
        average_wake_up_score=64.5952380952,
        average_sleep_score=71.2936507937,
        average_bonus=5.0,
        consistency_bonus=1.0,
    )


def _walking() -> ActivitySummary:
    return ActivitySummary(
        activity_type=WorkoutType.WALKING,
        sessions=30,
        duration_minutes=985.9904863278,
        active_energy_kcal=4476.2503,
        distance_km=79.575995,
    )


def _indoor_cycling() -> ActivitySummary:
    return ActivitySummary(
        activity_type=WorkoutType.INDOOR_CYCLING,
        sessions=7,
        duration_minutes=286.3349394162,
        active_energy_kcal=3200.77,
        distance_km=None,
    )


def _monthly_summary(
    *,
    activity_metrics: ActivityMetricsSummary | None = None,
    sleep_summary: SleepMonthlySummary | None = None,
    activities: list[ActivitySummary] | None = None,
    reporting_days: int = 14,
) -> MonthlySummary:
    return MonthlySummary(
        year=2026,
        month=8,
        reporting_days=reporting_days,
        days=[],
        activities=(
            activities
            if activities is not None
            else [
                _walking(),
                _indoor_cycling(),
            ]
        ),
        activity_metrics=(
            activity_metrics
            if activity_metrics is not None
            else _activity_metrics()
        ),
        sleep_summary=(
            sleep_summary
            if sleep_summary is not None
            else _sleep_summary()
        ),
    )


def _render_payload(
    summary: MonthlySummary,
) -> dict:
    output = JsonRenderer().render_month_summary(
        summary
    )

    return json.loads(output)


# =====================================================================
# Verifies that the monthly JSON report exposes the stable top-level API
# contract together with schema version and report metadata.
# =====================================================================

def test_render_month_summary_exposes_expected_contract() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    assert set(payload) == {
        "schema_version",
        "report",
        "general_activity",
        "sleep",
        "workouts",
        "body_weight",
        "energy_expenditure",
        "nutrition",
    }

    assert payload["schema_version"] == "1.0"

    assert payload["report"] == {
        "type": "monthly",
        "year": 2026,
        "month": 8,
        "reporting_days": 14,
        "data_through": "2026-08-14",
    }


# =====================================================================
# Verifies that general activity values are exposed as numeric API data
# and floating-point measurements are normalized to two decimal places.
# =====================================================================

def test_render_month_summary_builds_general_activity() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    general_activity = payload[
        "general_activity"
    ]

    assert general_activity == {
        "total_steps": 122_192,
        "average_daily_steps": 8728.0,
        "total_distance_km": 100.55,
        "average_daily_distance_km": 7.18,
        "average_step_length_cm": 82.29,
    }

    assert isinstance(
        general_activity["total_steps"],
        int,
    )

    assert isinstance(
        general_activity["total_distance_km"],
        float,
    )


# =====================================================================
# Verifies that monthly sleep data uses API-friendly time values,
# normalized numeric values and the configured maximum Sleep Score.
# =====================================================================

def test_render_month_summary_builds_sleep_section() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    sleep = payload["sleep"]

    assert sleep["sessions"] == 14
    assert sleep["average_bedtime"] == "01:45"
    assert sleep["average_wake_up"] == "08:56"

    assert sleep["average_sleep_minutes"] == 412.62
    assert sleep["average_awake_minutes"] == 18.45
    assert sleep["average_efficiency_percent"] == 95.98

    assert sleep["stages"] == {
        "core_minutes": 289.25,
        "deep_minutes": 34.65,
        "rem_minutes": 88.72,
    }

    assert sleep["score"] == {
        "average_bedtime": 67.5,
        "average_duration": 81.79,
        "average_wake_up": 64.6,
        "average_total": 71.29,
        "average_bonus": 5.0,
        "consistency_bonus": 1.0,
        "monthly_score": 77.29,
        "monthly_score_max": (
            100
            + SLEEP_MONTHLY_BONUS_MAX_POINTS
        ),
    }


# =====================================================================
# Verifies that workout types use stable enum identifiers and that
# averages explicitly describe whether they are daily or per workout.
# =====================================================================

def test_render_month_summary_builds_workouts() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    workouts = payload["workouts"]

    assert len(workouts) == 2

    walking = workouts[0]

    assert walking == {
        "type": "walking",
        "sessions": 30,
        "duration_minutes": 985.99,
        "active_energy_kcal": 4476.25,
        "distance_km": 79.58,
        "average_basis": "daily",
        "average_duration_minutes": 70.43,
        "average_active_energy_kcal": 319.73,
        "average_distance_km": 5.68,
    }

    cycling = workouts[1]

    assert cycling == {
        "type": "indoor_cycling",
        "sessions": 7,
        "duration_minutes": 286.33,
        "active_energy_kcal": 3200.77,
        "distance_km": None,
        "average_basis": "workout",
        "average_duration_minutes": 40.9,
        "average_active_energy_kcal": 457.25,
        "average_distance_km": None,
    }


# =====================================================================
# Verifies that body-weight measurements are represented as normalized
# numeric values while preserving the measurement count as an integer.
# =====================================================================

def test_render_month_summary_builds_body_weight() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    body_weight = payload["body_weight"]

    assert body_weight == {
        "average_kg": 79.45,
        "start_kg": 80.1,
        "end_kg": 78.75,
        "change_kg": -1.35,
        "max_kg": 80.2,
        "min_kg": 78.75,
        "measurements": 14,
    }


# =====================================================================
# Verifies that monthly energy expenditure is exposed using normalized
# numeric values and explicit energy units in the field names.
# =====================================================================

def test_render_month_summary_builds_energy_expenditure() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    assert payload["energy_expenditure"] == {
        "average_basal_kcal": 1944.71,
        "average_active_kcal": 752.94,
        "average_tdee_kcal": 2697.65,
    }


# =====================================================================
# Verifies that monthly nutrition values and calculated calorie balance
# are represented as normalized numeric API fields.
# =====================================================================

def test_render_month_summary_builds_nutrition() -> None:
    payload = _render_payload(
        _monthly_summary()
    )

    assert payload["nutrition"] == {
        "average_protein_g": 154.71,
        "average_carbohydrates_g": 193.79,
        "average_fat_g": 72.79,
        "average_calories_kcal": 2052.14,
        "average_calories_balance_kcal": -645.5,
    }


# =====================================================================
# Verifies that unavailable monthly report sections remain present in
# the API contract as null values while an empty workout list stays [].
# =====================================================================

def test_render_month_summary_preserves_partial_report_contract() -> None:
    summary = _monthly_summary()

    summary.activity_metrics = None
    summary.sleep_summary = None
    summary.activities = []

    payload = _render_payload(summary)

    assert payload["general_activity"] is None
    assert payload["sleep"] is None
    assert payload["workouts"] == []
    assert payload["body_weight"] is None
    assert payload["energy_expenditure"] is None
    assert payload["nutrition"] is None


# =====================================================================
# Verifies that individual optional metric categories become null
# without removing unrelated sections from the JSON report.
# =====================================================================

def test_render_month_summary_supports_partially_available_metrics() -> None:
    metrics = _activity_metrics(
        measurements=0,
        average_weight=None,
        start_weight=None,
        end_weight=None,
        max_weight=None,
        min_weight=None,
        average_protein_g=None,
        average_carbohydrates_g=None,
        average_fat_g=None,
        average_calories_kcal=None,
    )

    payload = _render_payload(
        _monthly_summary(
            activity_metrics=metrics,
        )
    )

    assert payload["general_activity"] is not None
    assert payload["energy_expenditure"] is not None

    assert payload["body_weight"] is None
    assert payload["nutrition"] is None


# =====================================================================
# Verifies that a report with no completed reporting days exposes a null
# data-through value while retaining the stable report metadata schema.
# =====================================================================

def test_render_month_summary_uses_null_data_through_without_reporting_days() -> None:
    payload = _render_payload(
        _monthly_summary(
            reporting_days=0,
            activities=[],
        )
    )

    assert payload["report"]["reporting_days"] == 0
    assert payload["report"]["data_through"] is None