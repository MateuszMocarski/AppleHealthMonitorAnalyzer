from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from apple_health.enums import SleepStage, WorkoutType


@dataclass(slots=True, init=False)
class Workout:
    activity_type: WorkoutType
    start: datetime
    end: datetime
    duration_minutes: float
    active_energy_kcal: float | None = None
    distance_km: float | None = None

    def __init__(
        self,
        activity_type: WorkoutType,
        start: datetime,
        end: datetime,
        duration_minutes: float,
        active_energy_kcal: float | None = None,
        distance_km: float | None = None,
        **_legacy_apple_fields: object,
    ) -> None:
        """Create canonical workout data.

        The ignored keyword sink keeps old third-party fixtures working during the
        compatibility window without storing Apple raw values on the domain model.
        """
        self.activity_type = activity_type
        self.start = start
        self.end = end
        self.duration_minutes = duration_minutes
        self.active_energy_kcal = active_energy_kcal
        self.distance_km = distance_km


@dataclass(slots=True, init=False)
class SleepRecord:
    stage: SleepStage
    start: datetime
    end: datetime
    duration_minutes: float

    def __init__(
        self,
        stage: SleepStage,
        start: datetime,
        end: datetime,
        duration_minutes: float,
        **_legacy_apple_fields: object,
    ) -> None:
        """Create canonical sleep evidence without provider source metadata."""
        self.stage = stage
        self.start = start
        self.end = end
        self.duration_minutes = duration_minutes


@dataclass
class DailyMetrics:
    date: date
    steps: int | None = None
    distance_km: float | None = None

    active_energy: float | None = None
    basal_energy: float | None = None

    weight: WeightMeasurement | None = None
    nutrition: NutritionData | None = None


@dataclass
class HealthData:
    workouts: list[Workout]
    daily_metrics: list[DailyMetrics]
    sleep_records: list[SleepRecord]


# Temporary compatibility name for the Apple-only public surface during the
# incremental provider-boundary migration.  New shared code must use
# ``HealthData``.
AppleHealthData = HealthData


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
