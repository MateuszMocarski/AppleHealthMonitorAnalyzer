from datetime import date, time

from apple_health.config.app_config import AppConfig
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
    measurements: int = 11,
) -> ActivityMetricsSummary:
    return ActivityMetricsSummary(
        total_steps=64_321,
        average_daily_steps=(4594.36, 14),
        total_distance_km=47.89,
        average_daily_distance_km=(3.42, 14),
        average_step_length_cm=(74.45, 14),
        average_basal_energy_kcal=(2210.46, 12),
        average_active_energy_kcal=(910.79, 14),
        average_tdee_kcal=(3121.24, 11),
        average_weight=112.35 if measurements else None,
        start_weight=113.2 if measurements else None,
        end_weight=111.7 if measurements else None,
        max_weight=114.0 if measurements else None,
        min_weight=111.4 if measurements else None,
        measurements=measurements,
        average_protein_g=(171.23, 10),
        average_carbohydrates_g=(211.37, 9),
        average_fat_g=(119.88, 8),
        average_calories_kcal=(2850.43, 7),
        average_calories_balance_kcal=(-270.81, 6),
    )


def _sleep_summary() -> SleepMonthlySummary:
    return SleepMonthlySummary(
        total_sessions=12,
        average_bedtime=time(23, 18),
        average_wake_up=time(7, 42),
        average_sleep_minutes=438.77,
        average_awake_minutes=21.23,
        average_sleep_efficiency=95.61,
        average_core_minutes=301.46,
        average_deep_minutes=52.35,
        average_rem_minutes=84.96,
        average_unspecified_minutes=0.0,
        average_bedtime_score=88.46,
        average_duration_score=92.35,
        average_wake_up_score=84.57,
        average_sleep_score=88.46,
        average_bonus=10.0,
        consistency_bonus=4.0,
    )


def _daily_summary(
    *,
    activities: list[ActivitySummary] | None = None,
    weight: float | None = 79.5,
    active_energy_kcal: float | None = 700.0,
    basal_energy_kcal: float | None = 1900.0,
    nutrition: NutritionData | None = None,
    sleep_session: SleepSession | None = None,
    sleep_score: SleepScore | None = None,
    total_steps: int | None = 10000,
    total_distance_km: float | None = 8.0,
) -> DailySummary:
    return DailySummary(
        date=date(2026, 8, 1),
        activities=activities or [],
        total_duration_minutes=sum(activity.duration_minutes for activity in (activities or [])),
        total_active_energy_kcal=(
            sum(
                activity.active_energy_kcal
                for activity in (activities or [])
                if activity.active_energy_kcal is not None
            )
            if all(activity.active_energy_kcal is not None for activity in (activities or []))
            else None
        ),
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
        sessions=18,
        duration_minutes=742.35,
        active_energy_kcal=3210.79,
        distance_km=58.43,
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
    assert "Sleep configuration" in output
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
# Verifies that monthly body-weight output is omitted when the
# reporting period contains no weight measurements.
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
# Verifies that the monthly text report uses the configured maximum
# monthly bonus when displaying the maximum possible Sleep Score.
# =====================================================================


def test_monthly_sleep_score_uses_configured_maximum_points() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.max_points = 25

    renderer = TextRenderer(config=config)

    output = renderer.render_month_summary(_monthly_summary())

    assert "Monthly score:     102/125" in output


# =====================================================================
# Verifies that disabling the monthly bonus feature changes the
# rendered Sleep Score section to an explicit disabled-state message.
# =====================================================================


def test_monthly_sleep_bonus_disabled_message_is_rendered() -> None:
    config = AppConfig()
    config.sleep.score.monthly_bonus.enabled = False

    renderer = TextRenderer(config=config)

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
    assert "Sleep configuration" not in output


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
    summary.activity_metrics.average_calories_balance_kcal = None

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
    summary.activity_metrics.average_tdee_kcal = None

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


# =====================================================================
# Verifies that the monthly summary renders the injected effective
# sleep configuration rather than implicit default configuration
# values.
# =====================================================================


def test_monthly_summary_renders_injected_sleep_configuration() -> None:
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

    renderer = TextRenderer(
        config=config,
    )

    output = renderer.render_month_summary(
        _monthly_summary(),
    )

    assert "Sleep configuration" in output
    assert "Session gap threshold: 45 min" in output
    assert "Linear penalties: yes" in output
    assert "Target:           23:30" in output
    assert "Target:           450 min" in output
    assert "Undersleep weight: 1.5" in output
    assert "Bedtime:  2" in output
    assert "Duration: 3" in output
    assert "Wake-up:  4" in output


# =====================================================================
# Verifies that monthly energy averages are rendered independently and
# coverage is shown only for metrics with incomplete contributing days.
# =====================================================================


def test_monthly_report_renders_independent_energy_coverage() -> None:
    summary = _monthly_summary()
    metrics = summary.activity_metrics
    assert metrics is not None

    metrics.average_basal_energy_kcal = (2200.0, 14)
    metrics.average_active_energy_kcal = None
    metrics.average_tdee_kcal = (3000.0, 9)

    output = TextRenderer().render_month_summary(summary)

    assert "  Basal energy:   2200 kcal\n" in output
    assert "  Basal energy:   2200 kcal based on" not in output
    assert "  Active energy:" not in output
    assert "  TDEE:           3000 kcal based on 9 days" in output


# =====================================================================
# Verifies that monthly nutrition averages are rendered independently
# when only some nutrient values are available.
# =====================================================================


def test_monthly_report_renders_partial_nutrition_independently() -> None:
    summary = _monthly_summary()
    metrics = summary.activity_metrics
    assert metrics is not None

    metrics.average_protein_g = (150.0, 10)
    metrics.average_carbohydrates_g = None
    metrics.average_fat_g = (70.0, 8)
    metrics.average_calories_kcal = None
    metrics.average_calories_balance_kcal = None

    output = TextRenderer().render_month_summary(summary)

    assert "Average nutrition" in output
    assert "  Protein:  150 g based on 10 days" in output
    assert "  Carbs:" not in output
    assert "  Fat:      70 g based on 8 days" in output
    assert "  Calories:" not in output
    assert "Average calories balance:" not in output


# =====================================================================
# Verifies that monthly calorie balance is rendered from its stored
# value and contributing-day coverage rather than other averages.
# =====================================================================


def test_monthly_report_renders_calorie_balance_coverage() -> None:
    summary = _monthly_summary()
    metrics = summary.activity_metrics
    assert metrics is not None

    metrics.average_calories_balance_kcal = (150.0, 6)

    output = TextRenderer().render_month_summary(summary)

    assert "Average calories balance: 150 kcal based on 6 days" in output


# =====================================================================
# Verifies that partial daily energy renders only available components
# and does not fabricate TDEE from incomplete data.
# =====================================================================


def test_daily_report_renders_partial_energy_independently() -> None:
    summary = _monthly_summary(
        days=[
            _daily_summary(
                basal_energy_kcal=1900.0,
                active_energy_kcal=None,
            )
        ]
    )
    summary.activity_metrics = None

    output = TextRenderer().render_month(summary)

    assert "  Basal energy:   1900 kcal" in output
    assert "  Active energy:" not in output
    assert "  TDEE:" not in output


# =====================================================================
# Verifies that partial daily nutrition renders each available nutrient
# independently without treating missing values as zero.
# =====================================================================


def test_daily_report_renders_partial_nutrition_independently() -> None:
    summary = _monthly_summary(
        days=[
            _daily_summary(
                nutrition=NutritionData(
                    protein_g=150.0,
                    fat_g=70.0,
                ),
            )
        ]
    )
    summary.activity_metrics = None

    output = TextRenderer().render_month(summary)

    assert "Daily nutrition" in output
    assert "  Protein:   150 g" in output
    assert "  Carbs:" not in output
    assert "  Fat:       70 g" in output
    assert "  Calories:" not in output
    assert "Calories balance:" not in output


# =====================================================================
# Verifies that monthly metric coverage is shown only when fewer days
# contribute to the metric than the report contains.
# =====================================================================


def test_monthly_report_shows_coverage_only_for_incomplete_metrics() -> None:
    summary = _monthly_summary()
    metrics = summary.activity_metrics
    assert metrics is not None

    metrics.average_basal_energy_kcal = (
        2200.0,
        summary.reporting_days,
    )
    metrics.average_active_energy_kcal = (
        800.0,
        summary.reporting_days - 2,
    )

    output = TextRenderer().render_month_summary(summary)

    assert "  Basal energy:   2200 kcal\n" in output
    assert f"  Basal energy:   2200 kcal based on " f"{summary.reporting_days} days" not in output
    assert f"  Active energy:  800 kcal based on " f"{summary.reporting_days - 2} days" in output


# =====================================================================
# Verifies that incomplete metric coverage uses the singular day label
# when exactly one day contributes to the monthly average.
# =====================================================================


def test_monthly_report_uses_singular_day_for_single_day_coverage() -> None:
    summary = _monthly_summary()
    metrics = summary.activity_metrics
    assert metrics is not None

    metrics.average_protein_g = (150.0, 1)

    output = TextRenderer().render_month_summary(summary)

    assert "  Protein:  150 g based on 1 day" in output


# =====================================================================
# Verifies that a day without energy data is reported explicitly
# instead of rendering an empty energy expenditure section.
# =====================================================================


def test_daily_report_reports_missing_energy_data() -> None:
    summary = _monthly_summary(
        days=[
            _daily_summary(
                basal_energy_kcal=None,
                active_energy_kcal=None,
            )
        ]
    )
    summary.activity_metrics = None

    output = TextRenderer().render_month(summary)

    assert "No energy expenditure data for that day" in output
    assert "Daily energy expenditure" not in output


# =====================================================================
# Verifies that monthly activity metrics expose their independent
# contributing-day coverage without mixing step and distance data.
# =====================================================================


def test_monthly_report_renders_activity_coverage() -> None:
    summary = _monthly_summary()
    metrics = summary.activity_metrics
    assert metrics is not None

    metrics.total_steps = 12000
    metrics.average_daily_steps = (6000.0, 2)

    metrics.total_distance_km = 10.0
    metrics.average_daily_distance_km = (
        5.0,
        2,
    )

    metrics.average_step_length_cm = (
        80.0,
        1,
    )

    summary.reporting_days = 4

    output = TextRenderer().render_month_summary(summary)

    assert "  Average daily: 6000 based on 2 days" in output

    assert "  Average daily:       " "5.00 km based on 2 days" in output

    assert "  Average step length: " "80.00 cm based on 1 day" in output


# =====================================================================
# Verifies that missing workout energy is omitted instead of being
# rendered as a measured zero-energy value.
# =====================================================================


def test_monthly_workout_omits_missing_energy() -> None:
    walking = ActivitySummary(
        activity_type=WorkoutType.WALKING,
        sessions=1,
        duration_minutes=60,
        active_energy_kcal=None,
        distance_km=5.0,
    )

    output = TextRenderer().render_month_summary(
        _monthly_summary(
            activities=[walking],
        )
    )

    assert "  Energy:   " not in output
    assert "Average Daily Energy:" not in output
    assert "  Distance: 5.00 km" in output
