from datetime import date, time

import apple_health.renderers.text_renderer as text_renderer_module
from apple_health.enums import WorkoutType
from apple_health.models import NutritionData
from apple_health.renderers.text_renderer import TextRenderer
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
    measurements: int = 2,
) -> ActivityMetricsSummary:
    return ActivityMetricsSummary(
        total_steps=122_192,
        average_daily_steps=8728.0,
        total_distance_km=100.55,
        average_daily_distance_km=7.18,
        average_step_length_cm=82.29,
        average_basal_energy_kcal=1945.0,
        average_active_energy_kcal=753.0,
        average_weight=79.45 if measurements else None,
        start_weight=80.10 if measurements else None,
        end_weight=78.75 if measurements else None,
        max_weight=80.20 if measurements else None,
        min_weight=78.75 if measurements else None,
        measurements=measurements,
        average_protein_g=155.0,
        average_carbohydrates_g=194.0,
        average_fat_g=73.0,
        average_calories_kcal=2052.0,
    )


def _sleep_summary() -> SleepMonthlySummary:
    return SleepMonthlySummary(
        total_sessions=14,
        average_bedtime=time(1, 45),
        average_wake_up=time(8, 56),
        average_sleep_minutes=413.0,
        average_awake_minutes=18.0,
        average_sleep_efficiency=96.0,
        average_core_minutes=289.0,
        average_deep_minutes=35.0,
        average_rem_minutes=89.0,
        average_bedtime_score=68.0,
        average_duration_score=82.0,
        average_wake_up_score=65.0,
        average_sleep_score=71.0,
        average_bonus=5.0,
        consistency_bonus=1.0,
    )


def _daily_summary(
    *,
    activities: list[ActivitySummary] | None = None,
    weight: float | None = 79.5,
    nutrition: NutritionData | None = None,
    sleep_session: SleepSession | None = None,
    sleep_score: SleepScore | None = None,
) -> DailySummary:
    return DailySummary(
        date=date(2026, 8, 1),
        activities=activities or [],
        total_duration_minutes=sum(activity.duration_minutes for activity in (activities or [])),
        total_active_energy_kcal=sum(
            activity.active_energy_kcal for activity in (activities or [])
        ),
        total_steps=10000,
        total_distance_km=8.0,
        active_energy_kcal=700.0,
        basal_energy_kcal=1900.0,
        weight=weight,
        nutrition=nutrition,
        sleep_session=sleep_session,
        sleep_score=sleep_score,
    )


def _monthly_summary(
    *,
    days: list[DailySummary] | None = None,
    activities: list[ActivitySummary] | None = None,
    measurements: int = 2,
    reporting_days: int = 14,
) -> MonthlySummary:
    return MonthlySummary(
        year=2026,
        month=8,
        reporting_days=reporting_days,
        days=days or [],
        activities=activities or [],
        activity_metrics=_activity_metrics(measurements=measurements),
        sleep_summary=_sleep_summary(),
    )


# =====================================================================
# Verifies that render_month_summary returns a complete monthly text
# report containing all major report sections.
# =====================================================================


def test_render_month_summary_contains_all_major_sections() -> None:
    walking = ActivitySummary(
        activity_type=WorkoutType.WALKING,
        sessions=30,
        duration_minutes=986.0,
        active_energy_kcal=4476.0,
        distance_km=79.58,
    )

    renderer = TextRenderer()

    output = renderer.render_month_summary(
        _monthly_summary(
            activities=[walking],
        )
    )

    assert "Apple Health Monthly Report" in output
    assert "August 2026" in output
    assert "Data available through: 2026-08-14" in output
    assert "General activity" in output
    assert "Sleep" in output
    assert "Sleep score" in output
    assert "Workouts" in output
    assert "Walking" in output
    assert "Body weight:" in output
    assert "Average energy expenditure" in output
    assert "Average nutrition" in output


# =====================================================================
# Verifies that rendering the full month includes both the monthly
# summary and the detailed daily reports.
# =====================================================================


def test_render_month_includes_daily_reports() -> None:
    renderer = TextRenderer()

    output = renderer.render_month(
        _monthly_summary(
            days=[
                _daily_summary(),
            ]
        )
    )

    assert "Apple Health Monthly Report" in output
    assert "2026-08-01" in output
    assert "Daily energy expenditure" in output


# =====================================================================
# Verifies that monthly body-weight output is omitted when the reporting
# period contains no weight measurements.
# =====================================================================


def test_monthly_weight_section_is_omitted_without_measurements() -> None:
    renderer = TextRenderer()

    output = renderer.render_month_summary(
        _monthly_summary(
            measurements=0,
        )
    )

    assert "Body weight:" not in output


# =====================================================================
# Verifies that missing daily nutrition data is rendered explicitly
# instead of failing or displaying fabricated nutrition values.
# =====================================================================


def test_daily_report_shows_missing_nutrition_message() -> None:
    renderer = TextRenderer()

    output = renderer.render_month(
        _monthly_summary(
            days=[
                _daily_summary(
                    nutrition=None,
                )
            ]
        )
    )

    assert "No nutrition data for that day" in output


# =====================================================================
# Verifies that a day with steps but no recorded workout is clearly
# rendered as having no workouts rather than no activity at all.
# =====================================================================


def test_daily_report_distinguishes_steps_without_workouts() -> None:
    renderer = TextRenderer()

    output = renderer.render_month(
        _monthly_summary(
            days=[
                _daily_summary(
                    activities=[],
                )
            ]
        )
    )

    assert "No workouts." in output
    assert "No activities." not in output


# =====================================================================
# Verifies that disabling the monthly bonus feature changes the rendered
# Sleep Score section to an explicit disabled-state message.
# =====================================================================


def test_monthly_sleep_bonus_disabled_message_is_rendered(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        text_renderer_module,
        "SLEEP_MONTHLY_BONUS_ENABLED",
        False,
    )

    renderer = TextRenderer()

    output = renderer.render_month_summary(_monthly_summary())

    assert "Monthly bonus system: disabled" in output
    assert "Monthly score:" not in output


# =====================================================================
# Verifies that a monthly report without sleep data is still rendered
# successfully and omits sleep-related sections.
# =====================================================================


def test_monthly_report_without_sleep_data() -> None:
    summary = _monthly_summary()
    summary.sleep_summary = None

    output = TextRenderer().render_month_summary(summary)

    assert "Apple Health Monthly Report" in output
    assert "General activity" in output

    assert "Sleep\n-----" not in output
    assert "Sleep score" not in output


# =====================================================================
# Verifies that the monthly workouts section is omitted when no
# workouts are available for the reporting period.
# =====================================================================


def test_monthly_report_without_workouts_omits_workouts_section() -> None:
    summary = _monthly_summary(
        activities=[],
    )

    output = TextRenderer().render_month_summary(summary)

    assert "Apple Health Monthly Report" in output
    assert "Workouts\n--------" not in output


# =====================================================================
# Verifies that the monthly nutrition section is omitted when no
# nutrition data is available for the reporting period.
# =====================================================================


def test_monthly_report_without_nutrition_omits_nutrition_section() -> None:
    summary = _monthly_summary()

    summary.activity_metrics.average_protein_g = None
    summary.activity_metrics.average_carbohydrates_g = None
    summary.activity_metrics.average_fat_g = None
    summary.activity_metrics.average_calories_kcal = None

    output = TextRenderer().render_month_summary(summary)

    assert "Apple Health Monthly Report" in output
    assert "General activity" in output
    assert "Average energy expenditure" in output
    assert "Average nutrition" not in output


# =====================================================================
# Verifies that the monthly energy expenditure section is omitted when
# no basal or active energy data is available for the reporting period.
# =====================================================================


def test_monthly_report_without_energy_omits_energy_section() -> None:
    summary = _monthly_summary()

    summary.activity_metrics.average_basal_energy_kcal = None
    summary.activity_metrics.average_active_energy_kcal = None

    output = TextRenderer().render_month_summary(summary)

    assert "Apple Health Monthly Report" in output
    assert "General activity" in output
    assert "Average nutrition" in output
    assert "Average energy expenditure" not in output


# =====================================================================
# Verifies that the monthly general activity section is omitted when
# neither step nor walking/running distance data is available.
# =====================================================================


def test_monthly_report_without_general_activity_omits_section() -> None:
    summary = _monthly_summary()

    summary.activity_metrics.total_steps = None
    summary.activity_metrics.average_daily_steps = None
    summary.activity_metrics.total_distance_km = None
    summary.activity_metrics.average_daily_distance_km = None
    summary.activity_metrics.average_step_length_cm = None

    output = TextRenderer().render_month_summary(summary)

    assert "Apple Health Monthly Report" in output
    assert "General activity" not in output
