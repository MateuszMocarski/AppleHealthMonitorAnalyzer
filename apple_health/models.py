from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from apple_health.enums import WorkoutType


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
    
    
@dataclass
class DailyMetrics:
    date: date
    steps: int = 0
    distance_km: float = 0.0
    
@dataclass
class AppleHealthData:
    workouts: list[Workout]
    daily_metrics: list[DailyMetrics]