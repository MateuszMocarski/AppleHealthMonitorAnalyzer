import json
from datetime import date

import pytest

from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.report_models import DailySummary, MonthlySummary
from connected_health.viewer.report_contract import (
    FullReport,
    PersistedReportValidationError,
    ReportKind,
    SummaryReport,
    parse_persisted_report,
)


def _summary() -> MonthlySummary:
    return MonthlySummary(
        year=2026,
        month=8,
        reporting_days=0,
        days=[],
        activities=[],
        activity_metrics=None,
        sleep_summary=None,
    )


def _summary_json() -> str:
    return JsonRenderer().render_month_summary(_summary())


def test_current_json_renderer_summary_validates_as_summary() -> None:
    report = parse_persisted_report(_summary_json(), expected_kind=ReportKind.SUMMARY)

    assert isinstance(report, SummaryReport)
    assert not isinstance(report, FullReport)


def test_current_json_renderer_full_validates_as_full() -> None:
    report = parse_persisted_report(
        JsonRenderer().render_month(_summary()), expected_kind=ReportKind.FULL
    )

    assert isinstance(report, FullReport)
    assert report.days == []


def test_current_json_renderer_full_with_daily_payload_validates() -> None:
    summary = _summary()
    summary.reporting_days = 1
    summary.days = [
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
    ]

    report = parse_persisted_report(
        JsonRenderer().render_month(summary), expected_kind=ReportKind.FULL
    )

    assert isinstance(report, FullReport)
    assert report.days[0].date == date(2026, 8, 1)


@pytest.mark.parametrize(
    "source",
    [
        '{"schema_version": "1.0",',
        '{"schema_version":"1.0","schema_version":"1.0"}',
        "NaN",
        "Infinity",
        "-Infinity",
        "[]",
    ],
)
def test_strict_json_parser_rejects_invalid_input(source: str) -> None:
    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(source)


def test_rejects_artifact_kind_shape_mismatch() -> None:
    with pytest.raises(PersistedReportValidationError, match="expected a full report"):
        parse_persisted_report(_summary_json(), expected_kind=ReportKind.FULL)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", "2.0"),
        ("unexpected", True),
    ],
)
def test_rejects_wrong_schema_version_and_unknown_keys(key: str, value: object) -> None:
    payload = json.loads(_summary_json())
    payload[key] = value

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_summary_with_full_only_days_key() -> None:
    payload = json.loads(_summary_json())
    payload["days"] = []

    with pytest.raises(PersistedReportValidationError, match="expected a summary report"):
        parse_persisted_report(json.dumps(payload), expected_kind=ReportKind.SUMMARY)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("report", "year"), "2026"),
        (("report", "data_through"), "2026/08/01"),
        (("workouts",), [{"type": "unknown"}]),
        (("calories_balance", "average_calories_balance_kcal"), float("nan")),
    ],
)
def test_contract_rejects_wrong_types_identifiers_and_nonfinite_values(
    path: tuple[str, ...], value: object
) -> None:
    payload = json.loads(_summary_json())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_coverage_count_above_reporting_day_domain() -> None:
    payload = json.loads(_summary_json())
    payload["report"]["reporting_days"] = 1
    payload["report"]["data_through"] = "2026-08-01"
    payload["energy_expenditure"] = {
        "average_basal_kcal": 1.0,
        "basal_count_days": 2,
        "average_active_kcal": None,
        "active_count_days": None,
        "average_tdee_kcal": None,
        "tdee_count_days": None,
    }

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_duplicate_or_out_of_range_daily_dates() -> None:
    payload = json.loads(JsonRenderer().render_month(_summary()))
    payload["report"]["reporting_days"] = 1
    payload["report"]["data_through"] = "2026-08-01"
    payload["days"] = [
        {
            "date": "2026-08-02",
            "general_activity": None,
            "sleep": None,
            "workouts": [],
            "body_weight": None,
            "energy_expenditure": None,
            "nutrition": None,
            "calories_balance_kcal": None,
        }
    ]

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload), expected_kind=ReportKind.FULL)


def test_rejects_non_renderer_datetime_representation() -> None:
    summary = _summary()
    summary.reporting_days = 1
    summary.days = [
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
    ]
    payload = json.loads(JsonRenderer().render_month(summary))
    payload["days"][0]["sleep"] = {
        "session": {
            "bedtime": "2026-08-01T00:00",
            "wake_up": "2026-08-01T08:00:00+00:00",
            "time_in_bed_minutes": 480,
            "time_asleep_minutes": 480,
            "awake_minutes": 0,
            "efficiency_percent": 100,
            "stages": {
                "core_minutes": 300,
                "deep_minutes": 60,
                "rem_minutes": 120,
                "unspecified_minutes": 0,
            },
        },
        "score": None,
    }

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload), expected_kind=ReportKind.FULL)
