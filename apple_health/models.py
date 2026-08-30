from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from apple_health.enums import SleepStage, WorkoutType


@dataclass(slots=True)
class Workout:
    apple_activity_type: str

    activity_type: WorkoutType

    source_name: str
    source_version: str | None

    start: datetime
    end: datetime

    duration_minutes: float

    active_energy_kcal: float | None = None
    distance_km: float | None = None


@dataclass(slots=True)
class SleepRecord:
    stage: SleepStage

    source_name: str
    source_version: str | None

    start: datetime
    end: datetime

    duration_minutes: float


@dataclass
class DailyMetrics:
    date: date
    steps: int = 0
    distance_km: float = 0.0

    active_energy: float | None = None
    basal_energy: float | None = None

    weight: WeightMeasurement | None = None
    nutrition: NutritionData | None = None


@dataclass
class AppleHealthData:
    workouts: list[Workout]
    daily_metrics: list[DailyMetrics]
    sleep_records: list[SleepRecord]


@dataclass(slots=True)
class WeightMeasurement:
    value: float
    timestamp: datetime
    is_user_entered: bool


@dataclass(slots=True)
class NutritionData:
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbohydrates_g: float | None = None
    fat_g: float | None = None
