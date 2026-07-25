from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from apple_health.enums import WorkoutType


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
    
@dataclass(slots=True)
class MonthlySummary:
    year: int
    month: int

    reporting_days: int

    days: list[DailySummary]
    activities: list[ActivitySummary]
    activity_metrics: ActivityMetricsSummary
    
@dataclass(slots=True)
class ActivityMetricsSummary:
    total_steps: int

    average_daily_steps: float

    total_distance_km: float

    average_daily_distance_km: float