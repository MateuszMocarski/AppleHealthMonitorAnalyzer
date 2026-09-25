"""Strict validation for persisted JSON 1.0 Viewer reports.

This module models the public JSON document emitted by :class:`JsonRenderer`.
It intentionally does not recreate the internal ``MonthlySummary`` dataclasses.
"""

from __future__ import annotations

import calendar
import json
import math
import re
from datetime import date, datetime, time
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)
from pydantic import ValidationError as PydanticValidationError

from connected_health.enums import WorkoutType


class PersistedReportValidationError(ValueError):
    """Raised when a persisted Viewer report is not valid JSON 1.0."""


class ReportKind(StrEnum):
    FULL = "full"
    SUMMARY = "summary"


def _strict_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError("must be finite") from error
    if not math.isfinite(result):
        raise ValueError("must be finite")
    return result


def _strict_date(value: Any) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("must be an ISO date (YYYY-MM-DD)")
    return date.fromisoformat(value)


def _strict_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
        r"(?:\.\d{1,6})?[+-](?:[01]\d|2[0-3]):[0-5]\d",
        value,
    ):
        raise ValueError("must be an ISO datetime")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("must be an ISO datetime") from error


def _strict_time(value: Any) -> time:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("must be an HH:MM time")
    return time.fromisoformat(value)


Number = Annotated[float, BeforeValidator(_strict_number)]
IsoDate = Annotated[date, BeforeValidator(_strict_date)]
IsoDatetime = Annotated[datetime, BeforeValidator(_strict_datetime)]
ClockTime = Annotated[time, BeforeValidator(_strict_time)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReportMetadata(StrictModel):
    type: Literal["monthly"]
    year: StrictInt
    month: StrictInt
    reporting_days: StrictInt
    data_through: IsoDate | None

    @model_validator(mode="after")
    def validate_period(self) -> ReportMetadata:
        if not 1 <= self.year <= 9999 or not 1 <= self.month <= 12:
            raise ValueError("report year and month must be valid calendar components")
        days_in_month = calendar.monthrange(self.year, self.month)[1]
        if not 0 <= self.reporting_days <= days_in_month:
            raise ValueError("reporting_days must be within the report month")
        expected = date(self.year, self.month, self.reporting_days) if self.reporting_days else None
        if self.data_through != expected:
            raise ValueError("data_through must match the report period and reporting_days")
        return self


class GeneralActivity(StrictModel):
    total_steps: StrictInt | None
    average_daily_steps: Number | None
    steps_count_days: StrictInt | None
    total_distance_km: Number | None
    average_daily_distance_km: Number | None
    distance_count_days: StrictInt | None
    average_step_length_cm: Number | None
    step_length_count_days: StrictInt | None


class SleepStages(StrictModel):
    core_minutes: Number
    deep_minutes: Number
    rem_minutes: Number
    unspecified_minutes: Number


class SleepScore(StrictModel):
    average_bedtime: Number
    average_duration: Number
    average_wake_up: Number
    average_total: Number
    average_bonus: Number
    consistency_bonus: Number
    monthly_score: Number
    monthly_score_max: Number


class ScoreThreshold(StrictModel):
    threshold: Number
    bonus: Number


class BedtimeConfiguration(StrictModel):
    target: ClockTime
    penalty_interval_minutes: StrictInt
    penalty_points: Number


class DurationConfiguration(StrictModel):
    target_minutes: StrictInt
    tolerance_minutes: StrictInt
    penalty_interval_minutes: StrictInt
    penalty_points: Number
    oversleep_weight: Number
    undersleep_weight: Number


class WakeUpConfiguration(StrictModel):
    target: ClockTime
    bedtime_weight: Number
    duration_weight: Number
    penalty_interval_minutes: StrictInt
    penalty_points: Number


class ScoreWeights(StrictModel):
    bedtime: Number
    duration: Number
    wake_up: Number


class MonthlyBonusConfiguration(StrictModel):
    enabled: StrictBool
    max_points: StrictInt
    average_thresholds: list[ScoreThreshold]
    consistency_thresholds: list[ScoreThreshold]


class SleepConfiguration(StrictModel):
    session_gap_threshold_minutes: StrictInt
    linear_penalties: StrictBool
    bedtime: BedtimeConfiguration
    duration: DurationConfiguration
    wake_up: WakeUpConfiguration
    weights: ScoreWeights
    monthly_bonus: MonthlyBonusConfiguration


class MonthlySleep(StrictModel):
    sessions: StrictInt
    average_bedtime: ClockTime
    average_wake_up: ClockTime
    average_sleep_minutes: Number
    average_awake_minutes: Number
    average_efficiency_percent: Number
    stages: SleepStages
    score: SleepScore
    configuration: SleepConfiguration


class MonthlyWorkout(StrictModel):
    type: StrictStr
    sessions: StrictInt
    duration_minutes: Number
    active_energy_kcal: Number | None
    distance_km: Number | None
    average_basis: Literal["daily", "workout"]
    average_duration_minutes: Number | None
    average_active_energy_kcal: Number | None
    average_distance_km: Number | None

    @model_validator(mode="after")
    def validate_workout(self) -> MonthlyWorkout:
        _validate_workout_type(self.type)
        return self


class BodyWeight(StrictModel):
    average_kg: Number | None
    start_kg: Number | None
    end_kg: Number | None
    change_kg: Number | None
    max_kg: Number | None
    min_kg: Number | None
    measurements: StrictInt


class EnergyExpenditure(StrictModel):
    average_basal_kcal: Number | None
    basal_count_days: StrictInt | None
    average_active_kcal: Number | None
    active_count_days: StrictInt | None
    average_tdee_kcal: Number | None
    tdee_count_days: StrictInt | None


class Nutrition(StrictModel):
    average_protein_g: Number | None
    protein_count_days: StrictInt | None
    average_carbohydrates_g: Number | None
    carbohydrates_count_days: StrictInt | None
    average_fat_g: Number | None
    fat_count_days: StrictInt | None
    average_calories_kcal: Number | None
    calories_count_days: StrictInt | None


class CaloriesBalance(StrictModel):
    average_calories_balance_kcal: Number | None
    total_calories_balance_kcal: Number | None
    calories_balance_count_days: StrictInt | None


class DailyGeneralActivity(StrictModel):
    steps: StrictInt | None
    distance_km: Number | None
    step_length_cm: Number | None


class DailySleepSession(StrictModel):
    bedtime: IsoDatetime
    wake_up: IsoDatetime
    time_in_bed_minutes: Number
    time_asleep_minutes: Number
    awake_minutes: Number
    efficiency_percent: Number
    stages: SleepStages


class DailySleepScore(StrictModel):
    bedtime: Number
    duration: Number
    wake_up: Number
    total: Number


class DailySleep(StrictModel):
    session: DailySleepSession
    score: DailySleepScore | None


class DailyWorkout(StrictModel):
    type: StrictStr
    sessions: StrictInt
    duration_minutes: Number
    active_energy_kcal: Number | None
    distance_km: Number | None

    @model_validator(mode="after")
    def validate_workout(self) -> DailyWorkout:
        _validate_workout_type(self.type)
        return self


class DailyBodyWeight(StrictModel):
    weight_kg: Number


class DailyEnergyExpenditure(StrictModel):
    basal_kcal: Number | None
    active_kcal: Number | None
    tdee_kcal: Number | None


class DailyNutrition(StrictModel):
    protein_g: Number | None
    carbohydrates_g: Number | None
    fat_g: Number | None
    calories_kcal: Number | None


class DailyReport(StrictModel):
    date: IsoDate
    general_activity: DailyGeneralActivity | None
    sleep: DailySleep | None
    workouts: list[DailyWorkout]
    body_weight: DailyBodyWeight | None
    energy_expenditure: DailyEnergyExpenditure | None
    nutrition: DailyNutrition | None
    calories_balance_kcal: Number | None


class SummaryReport(StrictModel):
    schema_version: Literal["1.0"]
    report: ReportMetadata
    general_activity: GeneralActivity | None
    sleep: MonthlySleep | None
    workouts: list[MonthlyWorkout]
    body_weight: BodyWeight | None
    energy_expenditure: EnergyExpenditure | None
    nutrition: Nutrition | None
    calories_balance: CaloriesBalance


class FullReport(SummaryReport):
    days: list[DailyReport]


ViewerReport = SummaryReport | FullReport


def _validate_workout_type(value: str) -> None:
    if value not in {workout.name.lower() for workout in WorkoutType}:
        raise ValueError("must be a canonical workout identifier")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PersistedReportValidationError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise PersistedReportValidationError(f"non-finite JSON constant is not permitted: {value}")


def parse_persisted_report(
    source: str | bytes,
    *,
    expected_kind: ReportKind | None = None,
) -> ViewerReport:
    """Strictly parse and validate one persisted JSON 1.0 report.

    ``expected_kind`` is the persisted artifact's declared kind when known.  It
    prevents a Summary document from being accepted for ``full.json`` (and vice
    versa) before any presentation code sees it.
    """
    try:
        payload = json.loads(
            source,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except PersistedReportValidationError:
        raise
    except (TypeError, UnicodeDecodeError, ValueError, RecursionError) as error:
        raise PersistedReportValidationError("malformed JSON report") from error

    if not isinstance(payload, dict):
        raise PersistedReportValidationError("top-level JSON value must be an object")

    actual_kind = ReportKind.FULL if "days" in payload else ReportKind.SUMMARY
    if expected_kind is not None and actual_kind != expected_kind:
        raise PersistedReportValidationError(
            f"expected a {expected_kind.value} report, got a {actual_kind.value} report"
        )

    model = FullReport if actual_kind is ReportKind.FULL else SummaryReport
    try:
        report = model.model_validate(payload)
        _validate_cross_field_invariants(report)
    except (PydanticValidationError, ValueError) as error:
        raise PersistedReportValidationError("invalid JSON 1.0 report") from error
    return report


def _validate_cross_field_invariants(report: ViewerReport) -> None:
    reporting_days = report.report.reporting_days
    _validate_coverage_pairs(report.general_activity, reporting_days)
    _validate_coverage_pairs(report.energy_expenditure, reporting_days)
    _validate_coverage_pairs(report.nutrition, reporting_days)
    _validate_coverage_pairs(report.calories_balance, reporting_days)

    if (
        report.body_weight is not None
        and not 0 <= report.body_weight.measurements <= reporting_days
    ):
        raise ValueError("body-weight measurements must not exceed reporting_days")

    if isinstance(report, FullReport):
        dates = [day.date for day in report.days]
        if len(set(dates)) != len(dates):
            raise ValueError("daily report dates must not be duplicated")
        if any(day.year != report.report.year or day.month != report.report.month for day in dates):
            raise ValueError("daily report dates must belong to the report period")
        if any(day.day > reporting_days for day in dates):
            raise ValueError("daily report dates must not exceed reporting_days")


def _validate_coverage_pairs(section: Any, reporting_days: int) -> None:
    if section is None:
        return
    for name in section.__class__.model_fields:
        if not name.endswith("_count_days"):
            continue
        count = getattr(section, name)
        value_name = name.removesuffix("_count_days")
        if value_name == "calories_balance":
            value_name = "average_calories_balance_kcal"
        elif value_name == "steps":
            value_name = "average_daily_steps"
        elif value_name == "distance":
            value_name = "average_daily_distance_km"
        elif value_name == "step_length":
            value_name = "average_step_length_cm"
        elif value_name in {"basal", "active", "tdee"}:
            value_name = f"average_{value_name}_kcal"
        elif value_name in {"protein", "carbohydrates", "fat", "calories"}:
            value_name = (
                f"average_{value_name}_g" if value_name != "calories" else "average_calories_kcal"
            )
        value = getattr(section, value_name)
        if (value is None) != (count is None):
            raise ValueError(f"{name} and {value_name} must both be present or null")
        if count is not None and not 1 <= count <= reporting_days:
            raise ValueError(f"{name} must be within reporting_days")
