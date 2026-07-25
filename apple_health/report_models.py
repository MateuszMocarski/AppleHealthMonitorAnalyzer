from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from apple_health.enums import WorkoutType
from apple_health.models import SleepRecord


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
    
    sleep_session: SleepSession | None = None

    @property
    def average_step_length_cm(self) -> float:
        if self.total_steps == 0:
            return 0.0

        return self.total_distance_km * 100000 / self.total_steps

@dataclass(slots=True)
class MonthlySummary:
    year: int
    month: int

    reporting_days: int

    days: list[DailySummary]
    activities: list[ActivitySummary]
    activity_metrics: ActivityMetricsSummary
    
    sleep_summary: SleepMonthlySummary
    
    @property
    def data_through(self) -> date:
        return date(self.year, self.month, self.reporting_days)
    
@dataclass(slots=True)
class ActivityMetricsSummary:
    total_steps: int

    average_daily_steps: float

    total_distance_km: float

    average_daily_distance_km: float
    
    average_step_length_cm: float
    
@dataclass(slots=True)
class SleepSession:
    session_date: date
    
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
        return (
            self.time_asleep_minutes
            / self.time_in_bed_minutes
            * 100
        )
        
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