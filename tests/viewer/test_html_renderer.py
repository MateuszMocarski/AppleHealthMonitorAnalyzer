from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

from connected_health.enums import WorkoutType
from connected_health.models import NutritionData
from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.report_models import (
    ActivityMetricsSummary,
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
    SleepScore,
    SleepSession,
)
from connected_health.viewer.html_renderer import HtmlRenderer
from connected_health.viewer.report_contract import (
    FullReport,
    SummaryReport,
    parse_persisted_report,
)


def _summary() -> MonthlySummary:
    return MonthlySummary(
        year=2026,
        month=8,
        reporting_days=1,
        days=[
            DailySummary(
                date=date(2026, 8, 1),
                activities=[],
                total_duration_minutes=0,
                total_active_energy_kcal=0,
                total_steps=None,
                total_distance_km=None,
                active_energy_kcal=None,
                basal_energy_kcal=None,
            )
        ],
        activities=[
            ActivitySummary(
                activity_type=WorkoutType.WALKING,
                sessions=1,
                duration_minutes=60,
                active_energy_kcal=None,
                distance_km=None,
            )
        ],
        activity_metrics=None,
        sleep_summary=None,
    )


def _detailed_full_summary() -> MonthlySummary:
    summary = _summary()
    summary.days = [
        DailySummary(
            date=date(2026, 8, 1),
            activities=[
                ActivitySummary(
                    activity_type=WorkoutType.WALKING,
                    sessions=1,
                    duration_minutes=60,
                    active_energy_kcal=300,
                    distance_km=5,
                )
            ],
            total_duration_minutes=60,
            total_active_energy_kcal=300,
            total_steps=1234,
            total_distance_km=1.5,
            active_energy_kcal=600,
            basal_energy_kcal=1900,
            weight=70,
            nutrition=NutritionData(
                protein_g=150,
                carbohydrates_g=200,
                fat_g=70,
                calories_kcal=2000,
            ),
            sleep_session=SleepSession(
                bedtime=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                wake_up=datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
                records=[],
                time_in_bed_minutes=480,
                time_asleep_minutes=450,
                core_minutes=300,
                deep_minutes=60,
                rem_minutes=90,
                unspecified_minutes=0,
                awake_minutes=30,
            ),
            sleep_score=SleepScore(
                bedtime_score=80,
                duration_score=90,
                wake_up_score=70,
                total_score=80,
            ),
        )
    ]
    return summary


def _rich_summary() -> MonthlySummary:
    summary = _detailed_full_summary()
    summary.reporting_days = 14
    summary.activities = [
        ActivitySummary(
            activity_type=WorkoutType.WALKING,
            sessions=10,
            duration_minutes=600,
            active_energy_kcal=3000,
            distance_km=42.5,
        ),
        ActivitySummary(
            activity_type=WorkoutType.INDOOR_CYCLING,
            sessions=2,
            duration_minutes=120,
            active_energy_kcal=800,
            distance_km=None,
        ),
    ]
    summary.activity_metrics = ActivityMetricsSummary(
        total_steps=8421,
        average_daily_steps=(842.1, 10),
        total_distance_km=12.5,
        average_daily_distance_km=(1.25, 10),
        average_step_length_cm=(74.2, 10),
        average_weight=70,
        start_weight=71,
        end_weight=69,
        max_weight=72,
        min_weight=68,
        measurements=4,
        average_basal_energy_kcal=(1900, 14),
        average_active_energy_kcal=(600, 12),
        average_tdee_kcal=(2500, 12),
        average_protein_g=(150, 11),
        average_carbohydrates_g=(200, 11),
        average_fat_g=(70, 11),
        average_calories_kcal=(2200, 11),
        average_calories_balance_kcal=(-300, 11),
    )
    summary.sleep_summary = SleepMonthlySummary(
        total_sessions=12,
        average_bedtime=datetime(2026, 8, 1, 22, 30, tzinfo=UTC).time(),
        average_wake_up=datetime(2026, 8, 1, 6, 30, tzinfo=UTC).time(),
        average_sleep_minutes=450,
        average_awake_minutes=30,
        average_sleep_efficiency=93.75,
        average_core_minutes=300,
        average_deep_minutes=60,
        average_rem_minutes=90,
        average_unspecified_minutes=0,
        average_bedtime_score=80,
        average_duration_score=90,
        average_wake_up_score=70,
        average_sleep_score=80,
        average_bonus=5,
        consistency_bonus=3,
    )
    return summary


def _multi_day_full_summary() -> MonthlySummary:
    summary = _detailed_full_summary()
    summary.reporting_days = 2
    summary.days.append(replace(summary.days[0], date=date(2026, 8, 2)))
    return summary


def test_html_renderer_renders_validated_summary_without_daily_content() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_rich_summary()))

    assert isinstance(report, SummaryReport)
    html = HtmlRenderer().render(report)

    assert 'data-report-kind="summary"' in html
    assert "August 2026" in html
    assert "Summary report" in html
    assert "Reporting days" in html
    assert "Data through" in html
    assert "Daily details are not available in Summary reports." in html
    assert 'data-viewer-daily="true"' not in html
    assert "data-viewer-day=" not in html
    assert "Previous day" not in html
    assert "Next day" not in html
    assert "General activity" in html
    assert "Total steps" in html
    assert "8,421" in html
    assert "Average daily steps" in html
    assert "Coverage: 10 days" in html
    assert "Sleep score" in html
    assert "Monthly score" in html
    assert "Workouts" in html
    assert "Indoor cycling" in html
    assert "Per workout" in html
    assert "Body weight" in html
    assert "Starting weight" in html
    assert "Energy expenditure" in html
    assert "Coverage: 14 days" in html
    assert "Nutrition" in html
    assert "Average protein" in html
    assert "Calorie balance" in html
    assert "-300" in html
    assert "average_daily_steps" not in html
    assert "ActivityMetricsSummary(" not in html
    assert "Average sleep stages" in html
    assert "Average Sleep Score components" in html
    assert 'class="viewer-chart viewer-chart--pie"' in html
    assert 'class="viewer-chart viewer-chart--donut"' not in html
    assert "Total workout duration by type" in html
    assert "Total active energy by type" in html
    assert "viewer-sleep-config-dialog" in html
    assert "Session gap threshold" in html
    assert "Penalty style" in html
    assert "Average thresholds" in html
    assert '<dialog class="viewer-sleep-config-dialog" data-viewer-sleep-config>' in html
    assert "Bedtime by day" not in html
    assert "Daily steps and distance" not in html
    assert "Daily macros" not in html
    assert "NaN" not in html
    assert "Infinity" not in html


def test_html_renderer_uses_semantic_metric_lists_and_associates_activity_coverage() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_rich_summary()))

    html = HtmlRenderer().render(report)

    assert '<div class="viewer-metric-grid">' not in html
    assert html.count('<dl class="viewer-metric-grid') >= 10
    assert '<dl class="viewer-metric-grid"><div class="viewer-metric"><dt>Total steps</dt>' in html

    total_steps = html.split("<dt>Total steps</dt>", 1)[1].split("</div>", 1)[0]
    average_steps = html.split("<dt>Average daily steps</dt>", 1)[1].split("</div>", 1)[0]
    total_distance = html.split("<dt>Total distance</dt>", 1)[1].split("</div>", 1)[0]
    average_distance = html.split("<dt>Average daily distance</dt>", 1)[1].split("</div>", 1)[0]
    average_step_length = html.split("<dt>Average step length</dt>", 1)[1].split("</div>", 1)[0]

    assert "Coverage:" not in total_steps
    assert "Coverage:" not in total_distance
    assert (
        '<dd>842.1<span class="viewer-metric-coverage">Coverage: 10 days</span></dd>'
        in average_steps
    )
    assert '<span class="viewer-metric-coverage">Coverage: 10 days</span></dd>' in average_distance
    assert (
        '<span class="viewer-metric-coverage">Coverage: 10 days</span></dd>' in average_step_length
    )


def test_html_renderer_renders_validated_full_daily_content() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_rich_summary()))

    assert isinstance(report, FullReport)
    html = HtmlRenderer().render(report)

    assert 'data-report-kind="full"' in html
    assert 'data-viewer-daily="true"' in html
    assert 'class="viewer-daily-navigation"' in html
    assert 'data-viewer-day="2026-08-01"' in html
    assert '<time data-viewer-day-label datetime="2026-08-01">August 1, 2026</time>' in html
    assert '<button type="button" data-viewer-day-previous disabled>Previous day</button>' in html
    assert "Next day" in html
    assert "Full report" in html
    assert "General activity" in html
    assert "Average daily steps" in html
    assert "Sleep score" in html
    assert "Bedtime score" in html
    assert "Duration score" in html
    assert "Wake-up score" in html
    assert "Total score" in html
    assert "Workouts" in html
    assert "2026-08-01" in html
    assert "1,234" in html
    assert "1.5" in html
    assert "450" in html
    assert "60" in html
    assert "70" in html
    assert 'class="viewer-chart viewer-chart--pie"' in html
    assert 'class="viewer-chart viewer-chart--donut"' not in html
    assert 'class="viewer-chart-line" fill="none"' in html
    assert 'class="viewer-chart-area"' not in html
    assert 'class="viewer-chart viewer-chart--line"' in html
    assert 'class="viewer-chart-grid viewer-chart-grid--daily viewer-daily-sleep-charts"' in html
    assert "1,900" in html
    assert "150" in html
    assert "2,000" in html
    assert "Walking" in html
    assert "<h4>Calorie balance</h4>" in html
    assert "Sleep session" in html
    assert "Sleep stages" in html
    assert "Sleep score" in html
    assert "Body weight" in html
    assert "Energy expenditure" in html
    assert "Nutrition" in html
    assert "Average sleep stages" in html
    assert "Average Sleep Score components" in html
    assert "Bedtime by day" in html
    assert "Wake-up time by day" in html
    assert "Daily steps" in html
    assert "Daily distance" in html
    assert "Daily steps and distance" not in html
    assert "Body weight by day" in html
    assert "Daily calorie balance" in html
    assert "Protein by day" in html
    assert "Carbohydrates by day" in html
    assert "Fat by day" in html
    assert "Calories by day" in html
    assert "Daily macros" not in html
    assert "viewer-chart--dual-line" not in html
    assert html.count('class="viewer-chart viewer-chart--line"') >= 8
    assert html.count('class="viewer-chart-line" fill="none"') >= 7
    assert "<polygon" not in html
    assert "Sleep Score components" in html
    monthly_score_chart = html.split("<figcaption>Average Sleep Score components</figcaption>", 1)[
        1
    ].split("</figure>", 1)[0]
    daily_score_chart = html.split("<figcaption>Sleep Score components</figcaption>", 1)[1].split(
        "</figure>", 1
    )[0]
    assert "Monthly score" not in monthly_score_chart
    assert "Average bonus" not in monthly_score_chart
    assert "Total score" not in daily_score_chart


def test_html_renderer_groups_monthly_and_daily_score_kpis_with_their_charts() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_rich_summary()))

    html = HtmlRenderer().render(report)

    assert '<div class="viewer-sleep-chart-layout">' in html
    monthly_score_group = html.split('<section class="viewer-sleep-score-chart">', 1)[1].split(
        "</section>", 1
    )[0]
    daily_score_group = html.split('<section class="viewer-daily-sleep-score-chart">', 1)[1].split(
        "</section>", 1
    )[0]
    monthly_metrics = html.split("<h3>Sleep score</h3>", 1)[1].split("</section>", 1)[0]

    assert "Average Sleep Score components" in monthly_score_group
    assert "Monthly score" in monthly_score_group
    assert "Maximum monthly score" in monthly_score_group
    assert "Average bonus" in monthly_score_group
    assert "Consistency bonus" in monthly_score_group
    assert "Monthly score" not in monthly_metrics
    assert "Sleep Score components" in daily_score_group
    assert "Total score" in daily_score_group


def test_html_renderer_uses_wide_weight_chart_and_compact_daily_secondary_grid() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_rich_summary()))

    html = HtmlRenderer().render(report)

    weight_section = html.split('viewer-monthly-section--body-weight">', 1)[1].split(
        "</section>", 1
    )[0]
    secondary_summary = html.split('<div class="viewer-daily-secondary-summary">', 1)[1].split(
        "</div></div></article>", 1
    )[0]

    assert 'class="viewer-chart-grid viewer-chart-grid--wide"' in weight_section
    assert "Body weight by day" in weight_section
    assert 'class="viewer-metric-grid viewer-metric-grid--three"' in html
    assert secondary_summary.count("viewer-daily-section--secondary") == 4
    for heading in ("Body weight", "Energy expenditure", "Nutrition", "Calorie balance"):
        assert f"<h4>{heading}</h4>" in secondary_summary
    assert "Daily macros" not in secondary_summary


def test_full_activity_renders_separate_steps_and_distance_series() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_multi_day_full_summary()))

    html = HtmlRenderer().render(report)
    steps_chart = html.split("<figcaption>Daily steps</figcaption>", 1)[1].split("</figure>", 1)[0]
    distance_chart = html.split("<figcaption>Daily distance</figcaption>", 1)[1].split(
        "</figure>", 1
    )[0]

    assert 'class="viewer-chart viewer-chart--dual-line"' not in html
    assert 'class="viewer-chart-line" fill="none"' in steps_chart
    assert 'class="viewer-chart-line" fill="none"' in distance_chart
    assert steps_chart.count('class="viewer-chart-point"') == 2
    assert distance_chart.count('class="viewer-chart-point"') == 2
    assert "1,234 steps" in steps_chart
    assert "1.5 km" in distance_chart


def test_html_renderer_orders_daily_articles_and_selects_the_latest_day() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_multi_day_full_summary()))

    html = HtmlRenderer().render(report)

    first_day = html.index('data-viewer-day="2026-08-01"')
    latest_day = html.index('data-viewer-day="2026-08-02"')

    assert first_day < latest_day
    assert 'data-viewer-day="2026-08-01" data-viewer-day-label="August 1, 2026" hidden' in html
    assert 'data-viewer-day="2026-08-02" data-viewer-day-label="August 2, 2026">' in html
    assert '<time data-viewer-current-day datetime="2026-08-02">August 2, 2026</time>' in html
    assert '<button type="button" data-viewer-day-previous>Previous day</button>' in html
    assert '<button type="button" data-viewer-day-next disabled>Next day</button>' in html


def test_html_renderer_normalizes_bedtime_chart_geometry_but_keeps_clock_labels() -> None:
    summary = _multi_day_full_summary()
    summary.days[0].sleep_session = replace(
        summary.days[0].sleep_session,
        bedtime=datetime(2026, 8, 1, 23, 0, tzinfo=UTC),
    )
    summary.days[1].sleep_session = replace(
        summary.days[1].sleep_session,
        bedtime=datetime(2026, 8, 2, 1, 0, tzinfo=UTC),
    )
    report = parse_persisted_report(JsonRenderer().render_month(summary))

    html = HtmlRenderer().render(report)
    bedtime_chart = html.split("Bedtime by day", 1)[1].split("</figure>", 1)[0]
    wake_up_chart = html.split("Wake-up time by day", 1)[1].split("</figure>", 1)[0]

    assert "01:00" in bedtime_chart
    assert "25:00" not in bedtime_chart
    assert "<title>Aug 2: 01:00</title>" in bedtime_chart
    assert "1500" not in bedtime_chart
    assert "<title>Aug 2: 08:00</title>" in wake_up_chart


def test_html_renderer_daily_sleep_session_uses_local_clock_without_timezone_suffix() -> None:
    summary = _rich_summary()
    offset = timezone(timedelta(hours=2))
    summary.days[0].sleep_session = replace(
        summary.days[0].sleep_session,
        bedtime=datetime(2026, 8, 1, 1, 16, tzinfo=offset),
        wake_up=datetime(2026, 8, 1, 8, 37, tzinfo=offset),
    )
    report = parse_persisted_report(JsonRenderer().render_month(summary))

    html = HtmlRenderer().render(report)

    assert "August 1, 2026 at 1:16" in html
    assert "August 1, 2026 at 8:37" in html
    assert "+0200" not in html


def test_html_renderer_notes_partial_workout_energy_without_zero_filling() -> None:
    summary = _rich_summary()
    summary.activities[1].active_energy_kcal = None
    report = parse_persisted_report(JsonRenderer().render_month_summary(summary))

    html = HtmlRenderer().render(report)
    energy_chart = html.split("Total active energy by type", 1)[1].split("</figure>", 1)[0]

    assert "Some workout types have unavailable active-energy data" in html
    assert "Indoor cycling" not in energy_chart
    assert "<title>Indoor cycling:" not in energy_chart


def test_html_renderer_renders_a_controlled_empty_daily_state_for_full_reports() -> None:
    summary = _summary()
    summary.days = []
    report = parse_persisted_report(JsonRenderer().render_month(summary))

    html = HtmlRenderer().render(report)

    assert 'data-viewer-daily="true"' in html
    assert "No daily details are available for this Full report." in html
    assert "data-viewer-day=" not in html
    assert "Previous day" not in html
    assert "Next day" not in html


def test_html_renderer_renders_missing_daily_values_as_unavailable_without_model_repr() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_summary()))

    html = HtmlRenderer().render(report)

    assert 'class="viewer-unavailable unavailable">Unavailable' in html
    assert "None" not in html
    assert "DailyGeneralActivity(" not in html
    assert "DailySleep(" not in html
    assert "DailyBodyWeight(" not in html
    assert "DailyEnergyExpenditure(" not in html
    assert "DailyNutrition(" not in html
    assert "No workouts recorded." in html
    assert 'class="viewer-monthly-section viewer-monthly-section--activity ' in html


def test_html_renderer_renders_missing_nested_daily_values_as_unavailable() -> None:
    summary = _detailed_full_summary()
    summary.days[0].active_energy_kcal = None
    summary.days[0].nutrition = NutritionData(protein_g=150)

    report = parse_persisted_report(JsonRenderer().render_month(summary))

    html = HtmlRenderer().render(report)

    assert (
        '<dt>Active energy</dt><dd><span class="viewer-unavailable unavailable">Unavailable</span>'
        in html
    )
    assert (
        "<dt>Carbohydrates</dt><dd>"
        '<span class="viewer-unavailable unavailable">Unavailable</span>' in html
    )
    assert "None" not in html


def test_html_renderer_escapes_string_values_defensively_before_markup() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_summary()))
    report.workouts[0].type = '<img src=x onerror="alert(1)">'

    html = HtmlRenderer().render(report)

    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html


def test_html_renderer_preserves_zero_values_and_provider_neutrality() -> None:
    summary = _rich_summary()
    summary.activity_metrics.total_steps = 0
    report = parse_persisted_report(JsonRenderer().render_month_summary(summary))

    html = HtmlRenderer().render(report)

    assert "<dt>Total steps</dt><dd>0</dd>" in html
    assert "Apple" not in html
    assert "apple" not in HtmlRenderer.__doc__.lower()


def test_html_renderer_preserves_daily_zero_values_and_escapes_daily_strings() -> None:
    summary = _detailed_full_summary()
    summary.days[0].total_steps = 0
    report = parse_persisted_report(JsonRenderer().render_month(summary))
    report.days[0].workouts[0].type = '<img src=x onerror="alert(1)">'

    html = HtmlRenderer().render(report)

    assert "<dt>Steps</dt><dd>0</dd>" in html
    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
