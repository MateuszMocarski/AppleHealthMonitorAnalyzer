from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from apple_health.enums import WorkoutType
from apple_health.models import NutritionData, SleepRecord


@dataclass(slots=True)
class ActivitySummary:
    activity_type: WorkoutType

    sessions: int

    duration_minutes: float

    active_energy_kcal: float

    distance_km: float | None


@dataclass(slots=True)
class DailySummary:
    date: date

    activities: list[ActivitySummary]

    total_duration_minutes: float
    total_active_energy_kcal: float

    total_steps: int
    total_distance_km: float

    active_energy_kcal: float
    basal_energy_kcal: float

    weight: float | None = None

    nutrition: NutritionData | None = None

    sleep_session: SleepSession | None = None

    sleep_score: SleepScore | None = None

    @property
    def average_step_length_cm(self) -> float:
        if self.total_steps == 0:
            return 0.0

        return self.total_distance_km * 100000 / self.total_steps

    @property
    def tdee_kcal(self) -> float:
        return self.active_energy_kcal + self.basal_energy_kcal

    @property
    def calories_balance_kcal(self) -> float | None:
        if self.nutrition is None:
            return None

        return self.nutrition.calories_kcal - self.tdee_kcal


@dataclass(slots=True)
class MonthlySummary:
    year: int
    month: int

    reporting_days: int

    days: list[DailySummary]
    activities: list[ActivitySummary]
    activity_metrics: ActivityMetricsSummary | None

    sleep_summary: SleepMonthlySummary | None

    @property
    def data_through(self) -> date | None:
        if self.reporting_days == 0:
            return None

        return date(
            self.year,
            self.month,
            self.reporting_days,
        )


@dataclass(slots=True)
class ActivityMetricsSummary:
    total_steps: int | None

    average_daily_steps: float | None

    total_distance_km: float | None

    average_daily_distance_km: float | None

    average_step_length_cm: float | None

    average_weight: float | None
    start_weight: float | None
    end_weight: float | None
    max_weight: float | None
    min_weight: float | None
    measurements: int

    average_basal_energy_kcal: tuple[float, int] | None
    average_active_energy_kcal: tuple[float, int] | None
    average_tdee_kcal: tuple[float, int] | None

    average_protein_g: tuple[float, int] | None
    average_carbohydrates_g: tuple[float, int] | None
    average_fat_g: tuple[float, int] | None
    average_calories_kcal: tuple[float, int] | None

    average_calories_balance_kcal: tuple[float, int] | None

    @property
    def weight_change(self) -> float | None:
        if self.start_weight is None or self.end_weight is None:
            return None

        return self.end_weight - self.start_weight


@dataclass(slots=True)
class SleepSession:
    bedtime: datetime
    wake_up: datetime

    records: list[SleepRecord]

    time_in_bed_minutes: float
    time_asleep_minutes: float

    core_minutes: float
    deep_minutes: float
    rem_minutes: float
    awake_minutes: float

    @property
    def sleep_efficiency_percent(self) -> float:
        return self.time_asleep_minutes / self.time_in_bed_minutes * 100

    @property
    def reporting_date(self) -> date:
        if self.bedtime.hour >= 12:
            return self.bedtime.date() + timedelta(days=1)

        return self.bedtime.date()


@dataclass(slots=True)
class SleepMonthlySummary:
    total_sessions: int

    average_bedtime: time
    average_wake_up: time

    average_sleep_minutes: float
    average_awake_minutes: float
    average_sleep_efficiency: float

    average_core_minutes: float
    average_deep_minutes: float
    average_rem_minutes: float

    average_bedtime_score: float
    average_duration_score: float
    average_wake_up_score: float
    average_sleep_score: float

    average_bonus: float = 0.0
    consistency_bonus: float = 0.0

    @property
    def monthly_sleep_score(self) -> float:
        return self.average_sleep_score + self.average_bonus + self.consistency_bonus


@dataclass(slots=True)
class SleepScore:
    bedtime_score: float
    duration_score: float
    wake_up_score: float
    total_score: float
