import json
from datetime import UTC, date, datetime

import pytest

from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.report_models import DailySummary, MonthlySummary, SleepSession
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


def _valid_monthly_workout() -> dict[str, object]:
    return {
        "type": "walking",
        "sessions": 1,
        "duration_minutes": 60.0,
        "active_energy_kcal": 400.0,
        "distance_km": 5.0,
        "average_basis": "daily",
        "average_duration_minutes": 60.0,
        "average_active_energy_kcal": 400.0,
        "average_distance_km": 5.0,
    }


def _valid_sleep() -> dict[str, object]:
    return {
        "sessions": 1,
        "average_bedtime": "23:00",
        "average_wake_up": "07:00",
        "average_sleep_minutes": 480.0,
        "average_awake_minutes": 0.0,
        "average_efficiency_percent": 100.0,
        "stages": {
            "core_minutes": 300.0,
            "deep_minutes": 60.0,
            "rem_minutes": 120.0,
            "unspecified_minutes": 0.0,
        },
        "score": {
            "average_bedtime": 80.0,
            "average_duration": 90.0,
            "average_wake_up": 90.0,
            "average_total": 90.0,
            "average_bonus": 0.0,
            "consistency_bonus": 0.0,
            "monthly_score": 90.0,
            "monthly_score_max": 120.0,
        },
        "configuration": {
            "session_gap_threshold_minutes": 30,
            "linear_penalties": False,
            "bedtime": {"target": "00:00", "penalty_interval_minutes": 15, "penalty_points": 5.0},
            "duration": {
                "target_minutes": 480,
                "tolerance_minutes": 30,
                "penalty_interval_minutes": 15,
                "penalty_points": 5.0,
                "oversleep_weight": 1.0,
                "undersleep_weight": 1.0,
            },
            "wake_up": {
                "target": "08:00",
                "bedtime_weight": 1.0,
                "duration_weight": 2.0,
                "penalty_interval_minutes": 15,
                "penalty_points": 3.0,
            },
            "weights": {"bedtime": 1.0, "duration": 1.0, "wake_up": 1.0},
            "monthly_bonus": {
                "enabled": True,
                "max_points": 20,
                "average_thresholds": [],
                "consistency_thresholds": [],
            },
        },
    }


def _set_path(payload: dict[str, object], path: tuple[str, ...], value: object) -> None:
    target: object = payload
    for key in path[:-1]:
        target = target[int(key)] if isinstance(target, list) else target[key]
    if isinstance(target, list):
        target[int(path[-1])] = value
    else:
        target[path[-1]] = value


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


def test_current_json_renderer_offset_sleep_datetime_validates() -> None:
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
            sleep_session=SleepSession(
                bedtime=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                wake_up=datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
                records=[],
                time_in_bed_minutes=480,
                time_asleep_minutes=480,
                core_minutes=300,
                deep_minutes=60,
                rem_minutes=120,
                unspecified_minutes=0,
                awake_minutes=0,
            ),
        )
    ]

    report = parse_persisted_report(
        JsonRenderer().render_month(summary), expected_kind=ReportKind.FULL
    )

    assert isinstance(report, FullReport)
    assert report.days[0].sleep is not None


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("sleep", "stages", "core_minutes"), -1),
        (("sleep", "average_sleep_minutes"), -1),
        (("sleep", "average_efficiency_percent"), 101),
        (("sleep", "score", "average_duration"), 101),
        (("sleep", "sessions"), -1),
        (("workouts", "0", "duration_minutes"), -1),
        (("workouts", "0", "distance_km"), -1),
        (("general_activity", "total_steps"), -1),
        (("general_activity", "total_distance_km"), -1),
    ],
)
def test_rejects_mechanically_impossible_persisted_values(
    path: tuple[str, ...], value: object
) -> None:
    payload = json.loads(_summary_json())
    payload["sleep"] = _valid_sleep()
    payload["workouts"] = [_valid_monthly_workout()]
    payload["general_activity"] = {
        "total_steps": 1,
        "average_daily_steps": None,
        "steps_count_days": None,
        "total_distance_km": 1.0,
        "average_daily_distance_km": None,
        "distance_count_days": None,
        "average_step_length_cm": None,
        "step_length_count_days": None,
    }
    _set_path(payload, path, value)

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_daily_sleep_duration_and_score_outside_mechanical_ranges() -> None:
    payload = json.loads(JsonRenderer().render_month(_summary()))
    payload["report"].update({"reporting_days": 1, "data_through": "2026-08-01"})
    payload["days"] = [
        {
            "date": "2026-08-01",
            "general_activity": None,
            "sleep": {
                "session": {
                    "bedtime": "2026-08-01T00:00:00+00:00",
                    "wake_up": "2026-08-01T01:00:00+00:00",
                    "time_in_bed_minutes": 0,
                    "time_asleep_minutes": 0,
                    "awake_minutes": 0,
                    "efficiency_percent": 0,
                    "stages": {
                        "core_minutes": 0,
                        "deep_minutes": 0,
                        "rem_minutes": 0,
                        "unspecified_minutes": 0,
                    },
                },
                "score": {"bedtime": 0, "duration": 0, "wake_up": 0, "total": 101},
            },
            "workouts": [],
            "body_weight": None,
            "energy_expenditure": None,
            "nutrition": None,
            "calories_balance_kcal": None,
        }
    ]

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload), expected_kind=ReportKind.FULL)

    payload["days"][0]["sleep"]["score"]["total"] = 0
    payload["days"][0]["sleep"]["session"]["time_in_bed_minutes"] = -1

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload), expected_kind=ReportKind.FULL)


def test_monthly_score_uses_the_declared_effective_configuration_maximum() -> None:
    payload = json.loads(_summary_json())
    payload["sleep"] = _valid_sleep()
    payload["sleep"]["score"]["monthly_score_max"] = 100

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_unusual_valid_values_and_signed_derived_values_remain_accepted() -> None:
    payload = json.loads(_summary_json())
    payload["report"].update({"reporting_days": 1, "data_through": "2026-08-01"})
    payload["sleep"] = _valid_sleep()
    payload["sleep"].update({"average_sleep_minutes": 0, "average_awake_minutes": 0})
    payload["sleep"]["stages"] = {
        "core_minutes": 0,
        "deep_minutes": 0,
        "rem_minutes": 0,
        "unspecified_minutes": 0,
    }
    payload["body_weight"] = {
        "average_kg": 70,
        "start_kg": 75,
        "end_kg": 70,
        "change_kg": -5,
        "max_kg": 75,
        "min_kg": 70,
        "measurements": 1,
    }
    payload["calories_balance"] = {
        "average_calories_balance_kcal": -500,
        "total_calories_balance_kcal": -500,
        "calories_balance_count_days": 1,
    }

    report = parse_persisted_report(json.dumps(payload))

    assert report.body_weight is not None and report.body_weight.change_kg == -5
    assert report.calories_balance.average_calories_balance_kcal == -500


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


def test_strict_json_parser_normalizes_oversized_integer_failure() -> None:
    source = '{"value":' + "1" * 5_000 + "}"

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(source)


def test_strict_json_parser_normalizes_recursion_failure() -> None:
    source = "[" * 1_100 + "0" + "]" * 1_100

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(source)


def test_strict_number_normalizes_huge_integer_float_overflow() -> None:
    source = _summary_json().replace(
        '"average_calories_balance_kcal": null',
        '"average_calories_balance_kcal": ' + "1" + "0" * 1_000,
    )

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


def test_rejects_unknown_workout_identifier_without_other_workout_errors() -> None:
    payload = json.loads(_summary_json())
    workout = _valid_monthly_workout()
    workout["type"] = "unknown"
    payload["workouts"] = [workout]

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


@pytest.mark.parametrize(
    ("value", "count"),
    [(1.0, None), (None, 1)],
)
def test_rejects_coverage_value_count_nullability_mismatch(
    value: float | None, count: int | None
) -> None:
    payload = json.loads(_summary_json())
    payload["report"]["reporting_days"] = 1
    payload["report"]["data_through"] = "2026-08-01"
    payload["energy_expenditure"] = {
        "average_basal_kcal": value,
        "basal_count_days": count,
        "average_active_kcal": None,
        "active_count_days": None,
        "average_tdee_kcal": None,
        "tdee_count_days": None,
    }

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_coverage_count_zero_when_value_exists() -> None:
    payload = json.loads(_summary_json())
    payload["report"]["reporting_days"] = 1
    payload["report"]["data_through"] = "2026-08-01"
    payload["energy_expenditure"] = {
        "average_basal_kcal": 1.0,
        "basal_count_days": 0,
        "average_active_kcal": None,
        "active_count_days": None,
        "average_tdee_kcal": None,
        "tdee_count_days": None,
    }

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_body_weight_measurements_above_reporting_days() -> None:
    payload = json.loads(_summary_json())
    payload["report"]["reporting_days"] = 1
    payload["report"]["data_through"] = "2026-08-01"
    payload["body_weight"] = {
        "average_kg": 70.0,
        "start_kg": 70.0,
        "end_kg": 70.0,
        "change_kg": 0.0,
        "max_kg": 70.0,
        "min_kg": 70.0,
        "measurements": 2,
    }

    with pytest.raises(PersistedReportValidationError):
        parse_persisted_report(json.dumps(payload))


def test_rejects_out_of_range_daily_date() -> None:
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


def test_rejects_duplicate_daily_dates() -> None:
    payload = json.loads(JsonRenderer().render_month(_summary()))
    payload["report"]["reporting_days"] = 1
    payload["report"]["data_through"] = "2026-08-01"
    day = {
        "date": "2026-08-01",
        "general_activity": None,
        "sleep": None,
        "workouts": [],
        "body_weight": None,
        "energy_expenditure": None,
        "nutrition": None,
        "calories_balance_kcal": None,
    }
    payload["days"] = [day, day]

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
            "bedtime": "2026-08-01T00:00:00",
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
