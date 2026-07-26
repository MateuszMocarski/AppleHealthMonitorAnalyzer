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

    active_energy: float = 0.0
    basal_energy: float = 0.0


@dataclass
class AppleHealthData:
    workouts: list[Workout]
    daily_metrics: list[DailyMetrics]
    sleep_records: list[SleepRecord]
