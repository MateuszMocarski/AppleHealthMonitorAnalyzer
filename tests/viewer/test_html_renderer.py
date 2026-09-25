from datetime import date

from connected_health.enums import WorkoutType
from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.report_models import ActivitySummary, DailySummary, MonthlySummary
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


def test_html_renderer_renders_validated_summary_without_daily_content() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_summary()))

    assert isinstance(report, SummaryReport)
    html = HtmlRenderer().render(report)

    assert 'data-report-kind="summary"' in html
    assert "Daily details" not in html
    assert 'class="unavailable">Unavailable' in html


def test_html_renderer_renders_validated_full_daily_content() -> None:
    report = parse_persisted_report(JsonRenderer().render_month(_summary()))

    assert isinstance(report, FullReport)
    html = HtmlRenderer().render(report)

    assert 'data-report-kind="full"' in html
    assert 'data-viewer-daily="true"' in html
    assert "2026-08-01" in html


def test_html_renderer_escapes_persisted_string_values_before_markup() -> None:
    report = parse_persisted_report(JsonRenderer().render_month_summary(_summary()))
    report.workouts[0].type = '<img src=x onerror="alert(1)">'

    html = HtmlRenderer().render(report)

    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
