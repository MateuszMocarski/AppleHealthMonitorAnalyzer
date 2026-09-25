from datetime import UTC, date, datetime

from connected_health.enums import WorkoutType
from connected_health.models import NutritionData
from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.report_models import (
    ActivitySummary,
    DailySummary,
    MonthlySummary,
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


def test_html_renderer_renders_validated_summary_without_daily_content() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_summary()))

    assert isinstance(report, SummaryReport)
    html = HtmlRenderer().render(report)

    assert 'data-report-kind="summary"' in html
    assert "Daily details" not in html
    assert 'class="unavailable">Unavailable' in html


def test_html_renderer_renders_validated_full_daily_content() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_detailed_full_summary()))

    assert isinstance(report, FullReport)
    html = HtmlRenderer().render(report)

    assert 'data-report-kind="full"' in html
    assert 'data-viewer-daily="true"' in html
    assert "2026-08-01" in html
    assert "1234" in html
    assert "1.5" in html
    assert "450.0" in html
    assert "60.0" in html
    assert "70.0" in html
    assert "1900.0" in html
    assert "150.0" in html
    assert "2000.0" in html
    assert "walking" in html
    assert "<h4>Calories balance</h4><p>-500.0</p>" in html


def test_html_renderer_renders_missing_daily_values_as_unavailable_without_model_repr() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_summary()))

    html = HtmlRenderer().render(report)

    assert 'class="unavailable">Unavailable' in html
    assert "None" not in html
    assert "DailyGeneralActivity(" not in html
    assert "DailySleep(" not in html
    assert "DailyBodyWeight(" not in html
    assert "DailyEnergyExpenditure(" not in html
    assert "DailyNutrition(" not in html
    assert "No workouts recorded." in html


def test_html_renderer_renders_missing_nested_daily_values_as_unavailable() -> None:
    summary = _detailed_full_summary()
    summary.days[0].active_energy_kcal = None
    summary.days[0].nutrition = NutritionData(protein_g=150)

    report = parse_persisted_report(JsonRenderer().render_month(summary))

    html = HtmlRenderer().render(report)

    assert '<dt>active kcal</dt><dd><span class="unavailable">Unavailable</span>' in html
    assert '<dt>carbohydrates g</dt><dd><span class="unavailable">Unavailable</span>' in html
    assert "None" not in html


def test_html_renderer_escapes_string_values_defensively_before_markup() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_summary()))
    report.workouts[0].type = '<img src=x onerror="alert(1)">'

    html = HtmlRenderer().render(report)

    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
