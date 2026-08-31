import json
from datetime import date, datetime, time, timezone

from apple_health.config.app_config import AppConfig
from apple_health.enums import WorkoutType
from apple_health.models import NutritionData
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.report_models import (
    ActivityMetricsSummary,
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
    SleepScore,
    SleepSession,
)

# =======
# Helpers
# =======


def _activity_metrics(
    *,
    total_steps: int | None = 64_321,
    average_daily_steps: tuple[float, int]
    | None = (
        4594.3571428571,
        14,
    ),
    total_distance_km: float | None = 47.891234,
    average_daily_distance_km: tuple[float, int]
    | None = (
        3.4208024286,
        14,
    ),
    average_step_length_cm: tuple[float, int]
    | None = (
        74.453287,
        14,
    ),
    average_basal_energy_kcal: tuple[float, int] | None = (2210.456, 12),
    average_active_energy_kcal: tuple[float, int] | None = (910.788, 14),
    average_tdee_kcal: tuple[float, int] | None = (3121.244, 11),
    average_weight: float | None = 112.3456,
    start_weight: float | None = 113.2,
    end_weight: float | None = 111.7,
    max_weight: float | None = 114.0,
    min_weight: float | None = 111.4,
    measurements: int = 11,
    average_protein_g: tuple[float, int] | None = (171.234, 10),
    average_carbohydrates_g: tuple[float, int] | None = (211.37, 9),
    average_fat_g: tuple[float, int] | None = (119.876, 8),
    average_calories_kcal: tuple[float, int] | None = (2850.432, 7),
    average_calories_balance_kcal: tuple[float, int] | None = (-270.812, 6),
) -> ActivityMetricsSummary:
    return ActivityMetricsSummary(
        total_steps=total_steps,
        average_daily_steps=average_daily_steps,
        total_distance_km=total_distance_km,
        average_daily_distance_km=average_daily_distance_km,
        average_step_length_cm=average_step_length_cm,
        average_basal_energy_kcal=average_basal_energy_kcal,
        average_active_energy_kcal=average_active_energy_kcal,
        average_tdee_kcal=average_tdee_kcal,
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
        average_calories_balance_kcal=average_calories_balance_kcal,
    )


def _sleep_summary() -> SleepMonthlySummary:
    return SleepMonthlySummary(
        total_sessions=12,
        average_bedtime=time(23, 18),
        average_wake_up=time(7, 42),
        average_sleep_minutes=438.7654321,
        average_awake_minutes=21.2345678,
        average_sleep_efficiency=95.6123456,
        average_core_minutes=301.456789,
        average_deep_minutes=52.345678,
        average_rem_minutes=84.962965,
        average_unspecified_minutes=0.0,
        average_bedtime_score=88.4567,
        average_duration_score=92.3456,
        average_wake_up_score=84.5678,
        average_sleep_score=88.4567,
        average_bonus=10.0,
        consistency_bonus=4.0,
    )


def _walking() -> ActivitySummary:
    return ActivitySummary(
        activity_type=WorkoutType.WALKING,
        sessions=18,
        duration_minutes=742.3456,
        active_energy_kcal=3210.789,
        distance_km=58.4321,
    )


def _indoor_cycling() -> ActivitySummary:
    return ActivitySummary(
        activity_type=WorkoutType.INDOOR_CYCLING,
        sessions=5,
        duration_minutes=214.5678,
        active_energy_kcal=2488.123,
        distance_km=None,
    )


def _daily_summary(
    *,
    day: int = 1,
    activities: list[ActivitySummary] | None = None,
    total_steps: int = 10_000,
    total_distance_km: float = 8.0,
    active_energy_kcal: float | None = 700.0,
    basal_energy_kcal: float | None = 1900.0,
    weight: float | None = 79.5,
    nutrition: NutritionData | None = None,
    sleep_session: SleepSession | None = None,
    sleep_score: SleepScore | None = None,
) -> DailySummary:
    activities = activities or []

    return DailySummary(
        date=date(
            2026,
            8,
            day,
        ),
        activities=activities,
        total_duration_minutes=sum(activity.duration_minutes for activity in activities),
        total_active_energy_kcal=sum(activity.active_energy_kcal for activity in activities),
        total_steps=total_steps,
        total_distance_km=total_distance_km,
        active_energy_kcal=active_energy_kcal,
        basal_energy_kcal=basal_energy_kcal,
        weight=weight,
        nutrition=nutrition,
        sleep_session=sleep_session,
        sleep_score=sleep_score,
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
            activity_metrics if activity_metrics is not None else _activity_metrics()
        ),
        sleep_summary=(sleep_summary if sleep_summary is not None else _sleep_summary()),
    )


def _render_payload(
    summary: MonthlySummary,
    config: AppConfig | None = None,
) -> dict:
    output = JsonRenderer(
        config=config,
    ).render_month_summary(summary)

    return json.loads(output)


# =====================================================================
# Verifies that the monthly JSON report exposes the stable top-level
# API contract together with schema version and report metadata.
# =====================================================================


def test_render_month_summary_exposes_expected_contract() -> None:
    payload = _render_payload(_monthly_summary())

    assert set(payload) == {
        "schema_version",
        "report",
        "general_activity",
        "sleep",
        "workouts",
        "body_weight",
        "energy_expenditure",
        "nutrition",
        "calories_balance",
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
    payload = _render_payload(_monthly_summary())

    general_activity = payload["general_activity"]

    assert isinstance(
        general_activity["total_steps"],
        int,
    )

    assert isinstance(
        general_activity["total_distance_km"],
        float,
    )

    assert payload["general_activity"] == {
        "total_steps": 64_321,
        "average_daily_steps": 4594.36,
        "steps_count_days": 14,
        "total_distance_km": 47.89,
        "average_daily_distance_km": 3.42,
        "distance_count_days": 14,
        "average_step_length_cm": 74.45,
        "step_length_count_days": 14,
    }


# =====================================================================
# Verifies that monthly sleep data uses API-friendly time values,
# normalized numeric values and the configured maximum Sleep Score.
# =====================================================================


def test_render_month_summary_builds_sleep_section() -> None:
    config = AppConfig()

    payload = _render_payload(
        _monthly_summary(),
        config=config,
    )

    sleep = payload["sleep"]

    assert sleep["sessions"] == 12
    assert sleep["average_bedtime"] == "23:18"
    assert sleep["average_wake_up"] == "07:42"

    assert sleep["average_sleep_minutes"] == 438.77
    assert sleep["average_awake_minutes"] == 21.23
    assert sleep["average_efficiency_percent"] == 95.61

    assert sleep["stages"] == {
        "core_minutes": 301.46,
        "deep_minutes": 52.35,
        "rem_minutes": 84.96,
        "unspecified_minutes": 0.0,
    }

    assert sleep["score"] == {
        "average_bedtime": 88.46,
        "average_duration": 92.35,
        "average_wake_up": 84.57,
        "average_total": 88.46,
        "average_bonus": 10.0,
        "consistency_bonus": 4.0,
        "monthly_score": 102.46,
        "monthly_score_max": (100 + config.sleep.score.monthly_bonus.max_points),
    }


# =====================================================================
# Verifies that workout types use stable enum identifiers and that
# averages explicitly describe whether they are daily or per workout.
# =====================================================================


def test_render_month_summary_builds_workouts() -> None:
    payload = _render_payload(_monthly_summary())

    workouts = payload["workouts"]

    assert len(workouts) == 2

    walking = workouts[0]

    assert walking == {
        "type": "walking",
        "sessions": 18,
        "duration_minutes": 742.35,
        "active_energy_kcal": 3210.79,
        "distance_km": 58.43,
        "average_basis": "daily",
        "average_duration_minutes": 53.02,
        "average_active_energy_kcal": 229.34,
        "average_distance_km": 4.17,
    }

    cycling = workouts[1]

    assert cycling == {
        "type": "indoor_cycling",
        "sessions": 5,
        "duration_minutes": 214.57,
        "active_energy_kcal": 2488.12,
        "distance_km": None,
        "average_basis": "workout",
        "average_duration_minutes": 42.91,
        "average_active_energy_kcal": 497.62,
        "average_distance_km": None,
    }


# =====================================================================
# Verifies that body-weight measurements are represented as normalized
# numeric values while preserving the measurement count as an integer.
# =====================================================================


def test_render_month_summary_builds_body_weight() -> None:
    payload = _render_payload(_monthly_summary())

    body_weight = payload["body_weight"]

    assert body_weight == {
        "average_kg": 112.35,
        "start_kg": 113.2,
        "end_kg": 111.7,
        "change_kg": -1.5,
        "max_kg": 114.0,
        "min_kg": 111.4,
        "measurements": 11,
    }


# =====================================================================
# Verifies that monthly energy expenditure is exposed using normalized
# numeric values and explicit energy units in the field names.
# =====================================================================


def test_render_month_summary_builds_energy_expenditure() -> None:
    payload = _render_payload(_monthly_summary())

    assert payload["energy_expenditure"] == {
        "average_basal_kcal": 2210.46,
        "basal_count_days": 12,
        "average_active_kcal": 910.79,
        "active_count_days": 14,
        "average_tdee_kcal": 3121.24,
        "tdee_count_days": 11,
    }


# =====================================================================
# Verifies that monthly nutrition values and calculated calorie balance
# are represented as normalized numeric API fields.
# =====================================================================


def test_render_month_summary_builds_nutrition() -> None:
    payload = _render_payload(_monthly_summary())

    assert payload["nutrition"] == {
        "average_protein_g": 171.23,
        "protein_count_days": 10,
        "average_carbohydrates_g": 211.37,
        "carbohydrates_count_days": 9,
        "average_fat_g": 119.88,
        "fat_count_days": 8,
        "average_calories_kcal": 2850.43,
        "calories_count_days": 7,
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
    assert payload["calories_balance"] == {
        "average_calories_balance_kcal": None,
        "total_calories_balance_kcal": None,
        "calories_balance_count_days": None,
    }


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
        average_calories_balance_kcal=None,
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
# Verifies that a report with no completed reporting days exposes a
# null data-through value while retaining the stable report metadata
# schema.
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


# =====================================================================
# Verifies that render_month includes daily report entries in addition
# to the monthly summary contract.
# =====================================================================


def test_render_month_includes_daily_reports() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert "days" in payload
    assert len(payload["days"]) == 1
    assert payload["days"][0]["date"] == "2026-08-01"


# =====================================================================
# Verifies that daily general activity exposes steps, distance and step
# length using normalized numeric values.
# =====================================================================


def test_render_day_builds_general_activity() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            total_steps=10000,
            total_distance_km=8.123456,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    general_activity = payload["days"][0]["general_activity"]

    assert general_activity == {
        "steps": 10000,
        "distance_km": 8.12,
        "step_length_cm": 81.23,
    }


# =====================================================================
# Verifies that daily workouts use stable workout type identifiers and
# preserve workout metrics without monthly averaging fields.
# =====================================================================


def test_render_day_builds_workouts() -> None:
    walking = ActivitySummary(
        activity_type=WorkoutType.WALKING,
        sessions=1,
        duration_minutes=60.456,
        active_energy_kcal=400.789,
        distance_km=5.4321,
    )

    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            activities=[walking],
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["workouts"] == [
        {
            "type": "walking",
            "sessions": 1,
            "duration_minutes": 60.46,
            "active_energy_kcal": 400.79,
            "distance_km": 5.43,
        }
    ]


# =====================================================================
# Verifies that daily body weight is represented as a dedicated section
# and normalized to the API precision.
# =====================================================================


def test_render_day_builds_body_weight() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            weight=79.456,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["body_weight"] == {
        "weight_kg": 79.46,
    }


# =====================================================================
# Verifies that daily energy expenditure exposes basal, active and TDEE
# values using normalized numeric fields.
# =====================================================================


def test_render_day_builds_energy_expenditure() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            basal_energy_kcal=1900.456,
            active_energy_kcal=700.788,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["energy_expenditure"] == {
        "basal_kcal": 1900.46,
        "active_kcal": 700.79,
        "tdee_kcal": 2601.24,
    }


# =====================================================================
# Verifies that daily nutrition and calorie balance are represented as
# separate API concepts.
# =====================================================================


def test_render_day_builds_nutrition_and_calorie_balance() -> None:
    nutrition = NutritionData(
        calories_kcal=2000.456,
        protein_g=150.123,
        carbohydrates_g=200.789,
        fat_g=70.456,
    )

    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            nutrition=nutrition,
            basal_energy_kcal=1900.0,
            active_energy_kcal=700.0,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    day = payload["days"][0]

    assert day["nutrition"] == {
        "protein_g": 150.12,
        "carbohydrates_g": 200.79,
        "fat_g": 70.46,
        "calories_kcal": 2000.46,
    }

    assert day["calories_balance_kcal"] == -599.54


# =====================================================================
# Verifies that daily sleep data preserves full timestamps, sleep-stage
# durations and sleep-efficiency metrics.
# =====================================================================


def test_render_day_builds_sleep_session() -> None:
    sleep_session = SleepSession(
        bedtime=datetime(
            2026,
            8,
            1,
            0,
            30,
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
        time_in_bed_minutes=450.456,
        time_asleep_minutes=420.123,
        core_minutes=280.123,
        deep_minutes=50.456,
        rem_minutes=89.544,
        unspecified_minutes=0.0,
        awake_minutes=30.333,
    )

    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            sleep_session=sleep_session,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    sleep = payload["days"][0]["sleep"]

    assert sleep["session"]["bedtime"] == ("2026-08-01T00:30:00+00:00")
    assert sleep["session"]["wake_up"] == ("2026-08-01T08:00:00+00:00")

    assert sleep["session"]["time_in_bed_minutes"] == 450.46
    assert sleep["session"]["time_asleep_minutes"] == 420.12
    assert sleep["session"]["awake_minutes"] == 30.33


# =====================================================================
# Verifies that daily Sleep Score components and total score are
# exposed as normalized API values.
# =====================================================================


def test_render_day_builds_sleep_score() -> None:
    sleep_session = SleepSession(
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
        time_in_bed_minutes=480,
        time_asleep_minutes=480,
        core_minutes=300,
        deep_minutes=60,
        rem_minutes=120,
        unspecified_minutes=0.0,
        awake_minutes=0,
    )

    sleep_score = SleepScore(
        bedtime_score=80.456,
        duration_score=90.789,
        wake_up_score=70.123,
        total_score=81.234,
    )

    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            sleep_session=sleep_session,
            sleep_score=sleep_score,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["sleep"]["score"] == {
        "bedtime": 80.46,
        "duration": 90.79,
        "wake_up": 70.12,
        "total": 81.23,
    }


# =====================================================================
# Verifies that missing optional daily data remains represented through
# null values and empty collections without breaking the day contract.
# =====================================================================


def test_render_day_preserves_partial_report_contract() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            activities=[],
            weight=None,
            active_energy_kcal=None,
            basal_energy_kcal=None,
            nutrition=None,
            sleep_session=None,
            sleep_score=None,
        )
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    day = payload["days"][0]

    assert day["sleep"] is None
    assert day["workouts"] == []
    assert day["body_weight"] is None
    assert day["nutrition"] is None
    assert day["calories_balance_kcal"] is None
    assert day["energy_expenditure"] is None
    assert day["nutrition"] is None
    assert day["calories_balance_kcal"] is None


# =====================================================================
# Verifies that JsonRenderer uses the injected monthly sleep bonus
# configuration when calculating the maximum monthly sleep score.
# =====================================================================


def test_uses_configured_monthly_sleep_bonus_max_points() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.max_points = 25

    payload = _render_payload(
        _monthly_summary(),
        config=config,
    )

    assert payload["sleep"]["score"]["monthly_score_max"] == 125


# =====================================================================
# Verifies that disabling the monthly bonus system limits the maximum
# monthly Sleep Score exposed by JSON to the base 100-point scale.
# =====================================================================


def test_disabled_monthly_sleep_bonus_uses_base_score_maximum() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.enabled = False

    payload = _render_payload(
        _monthly_summary(),
        config=config,
    )

    assert payload["sleep"]["score"]["monthly_score_max"] == 100


# =====================================================================
# Verifies that the monthly sleep JSON section exposes the effective
# injected sleep configuration using API-friendly values.
# =====================================================================


def test_render_month_summary_builds_sleep_configuration() -> None:
    config = AppConfig()

    config.sleep.session_gap_threshold_minutes = 45
    config.sleep.score.linear_penalties = True

    config.sleep.score.bedtime.target = time(23, 30)
    config.sleep.score.duration.target_minutes = 450
    config.sleep.score.duration.undersleep_weight = 1.5

    config.sleep.score.wake_up.target = time(7, 30)

    config.sleep.score.weights.bedtime = 2.0
    config.sleep.score.weights.duration = 3.0
    config.sleep.score.weights.wake_up = 4.0

    payload = _render_payload(
        _monthly_summary(),
        config=config,
    )

    configuration = payload["sleep"]["configuration"]

    assert configuration["session_gap_threshold_minutes"] == 45
    assert configuration["linear_penalties"] is True

    assert configuration["bedtime"]["target"] == "23:30"

    assert configuration["duration"]["target_minutes"] == 450
    assert configuration["duration"]["undersleep_weight"] == 1.5

    assert configuration["wake_up"]["target"] == "07:30"

    assert configuration["weights"] == {
        "bedtime": 2.0,
        "duration": 3.0,
        "wake_up": 4.0,
    }

    assert configuration["monthly_bonus"]["average_thresholds"][0] == {
        "threshold": 90,
        "bonus": 15,
    }

    assert configuration["monthly_bonus"]["consistency_thresholds"][0] == {
        "threshold": 3,
        "bonus": 5,
    }


# =====================================================================
# Verifies that monthly calorie balance exposes average and total values
# together with their shared contributing-day coverage.
# =====================================================================


def test_render_month_summary_builds_calorie_balance() -> None:
    payload = _render_payload(_monthly_summary())

    assert payload["calories_balance"] == {
        "average_calories_balance_kcal": -270.81,
        "total_calories_balance_kcal": -1624.87,
        "calories_balance_count_days": 6,
    }


# =====================================================================
# Verifies that monthly energy metrics preserve a stable section shape
# while each value keeps its own independent coverage.
# =====================================================================


def test_render_month_summary_supports_partial_energy_coverage() -> None:
    metrics = _activity_metrics(
        average_basal_energy_kcal=(2200.0, 14),
        average_active_energy_kcal=None,
        average_tdee_kcal=(3000.0, 9),
    )

    payload = _render_payload(
        _monthly_summary(
            activity_metrics=metrics,
        )
    )

    assert payload["energy_expenditure"] == {
        "average_basal_kcal": 2200.0,
        "basal_count_days": 14,
        "average_active_kcal": None,
        "active_count_days": None,
        "average_tdee_kcal": 3000.0,
        "tdee_count_days": 9,
    }


# =====================================================================
# Verifies that monthly nutrition preserves a stable section shape when
# only selected nutrient averages are available.
# =====================================================================


def test_render_month_summary_supports_partial_nutrition_coverage() -> None:
    metrics = _activity_metrics(
        average_protein_g=(150.0, 10),
        average_carbohydrates_g=None,
        average_fat_g=(70.0, 8),
        average_calories_kcal=None,
        average_calories_balance_kcal=None,
    )

    payload = _render_payload(
        _monthly_summary(
            activity_metrics=metrics,
        )
    )

    assert payload["nutrition"] == {
        "average_protein_g": 150.0,
        "protein_count_days": 10,
        "average_carbohydrates_g": None,
        "carbohydrates_count_days": None,
        "average_fat_g": 70.0,
        "fat_count_days": 8,
        "average_calories_kcal": None,
        "calories_count_days": None,
    }


# =====================================================================
# Verifies that partial daily energy keeps missing values as null and
# does not fabricate TDEE from an incomplete energy pair.
# =====================================================================


def test_render_day_supports_partial_energy() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            basal_energy_kcal=1900.0,
            active_energy_kcal=None,
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["energy_expenditure"] == {
        "basal_kcal": 1900.0,
        "active_kcal": None,
        "tdee_kcal": None,
    }


# =====================================================================
# Verifies that partial daily nutrition keeps unavailable nutrient
# values as null without treating them as zero.
# =====================================================================


def test_render_day_supports_partial_nutrition() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            nutrition=NutritionData(
                protein_g=150.0,
                fat_g=70.0,
            ),
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    day = payload["days"][0]

    assert day["nutrition"] == {
        "protein_g": 150.0,
        "carbohydrates_g": None,
        "fat_g": 70.0,
        "calories_kcal": None,
    }

    assert day["calories_balance_kcal"] is None


# =====================================================================
# Verifies that an empty daily nutrition object is represented as null
# when no nutrient value is actually available.
# =====================================================================


def test_render_day_uses_null_for_empty_nutrition() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            nutrition=NutritionData(),
        ),
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["nutrition"] is None


# =====================================================================
# Verifies that monthly general activity exposes independent coverage
# for steps, distance and their shared step-length intersection.
# =====================================================================


def test_render_month_summary_preserves_activity_coverage() -> None:
    metrics = _activity_metrics(
        total_steps=12000,
        average_daily_steps=(6000.0, 2),
        total_distance_km=10.0,
        average_daily_distance_km=(5.0, 2),
        average_step_length_cm=(80.0, 1),
    )

    payload = _render_payload(
        _monthly_summary(
            activity_metrics=metrics,
            reporting_days=4,
        )
    )

    assert payload["general_activity"] == {
        "total_steps": 12000,
        "average_daily_steps": 6000.0,
        "steps_count_days": 2,
        "total_distance_km": 10.0,
        "average_daily_distance_km": 5.0,
        "distance_count_days": 2,
        "average_step_length_cm": 80.0,
        "step_length_count_days": 1,
    }


# =====================================================================
# Verifies that a day without step or walking-distance measurements
# exposes no general-activity section instead of fabricated zeros.
# =====================================================================


def test_render_day_uses_null_for_missing_general_activity() -> None:
    summary = _monthly_summary()
    summary.days = [
        _daily_summary(
            total_steps=None,
            total_distance_km=None,
        )
    ]

    payload = json.loads(JsonRenderer().render_month(summary))

    assert payload["days"][0]["general_activity"] is None
