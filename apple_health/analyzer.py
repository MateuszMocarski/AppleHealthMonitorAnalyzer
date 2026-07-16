from __future__ import annotations

from collections import defaultdict
from datetime import date

from apple_health.enums import WorkoutType
from apple_health.models import Workout
from apple_health.report_models import ActivitySummary
from apple_health.report_models import DailySummary


class WorkoutAnalyzer:
    def __init__(self, workouts: list[Workout]) -> None:
        self.workouts = workouts
        self._workouts_by_day = self._group_workouts_by_day()

    def _group_workouts_by_day(self) -> dict[date, list[Workout]]:
        workouts_by_day: dict[date, list[Workout]] = defaultdict(list)

        for workout in self.workouts:
            workouts_by_day[workout.start.date()].append(workout)

        return dict(workouts_by_day)

    def workouts_by_day(self) -> dict[date, list[Workout]]:
        return self._workouts_by_day

    def active_days(self) -> int:
        return len(self._workouts_by_day)

    def workouts_for_day(self, day: date) -> list[Workout]:
        return self._workouts_by_day.get(day, [])

    def summarize_day(self, day: date) -> DailySummary:
        grouped: dict[WorkoutType, list[Workout]] = defaultdict(list)

        for workout in self.workouts_for_day(day):
            grouped[workout.activity_type].append(workout)

        activities = [
            self._build_activity_summary(activity_type, workouts)
            for activity_type, workouts in grouped.items()
        ]

        return DailySummary(
            date=day,
            activities=activities,
            total_duration_minutes=sum(
                activity.duration_minutes
                for activity in activities
            ),
            total_active_energy_kcal=sum(
                activity.active_energy_kcal
                for activity in activities
            ),
        )

    def _build_activity_summary(
        self,
        activity_type: WorkoutType,
        workouts: list[Workout],
    ) -> ActivitySummary:
        distance = [
            workout.distance_km
            for workout in workouts
            if workout.distance_km is not None
        ]

        return ActivitySummary(
            activity_type=activity_type,
            sessions=len(workouts),
            duration_minutes=sum(
                workout.duration_minutes
                for workout in workouts
            ),
            active_energy_kcal=sum(
                workout.active_energy_kcal or 0
                for workout in workouts
            ),
            distance_km=(
                sum(distance)
                if distance
                else None
            ),
        )