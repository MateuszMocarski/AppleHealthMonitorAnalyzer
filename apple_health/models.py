from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apple_health.enums import WorkoutType


@dataclass(slots=True)
class Workout:
    activity_type: WorkoutType

    source_name: str
    source_version: str | None

    start: datetime
    end: datetime

    duration_minutes: float

    active_energy_kcal: float | None = None
    distance_km: float | None = None