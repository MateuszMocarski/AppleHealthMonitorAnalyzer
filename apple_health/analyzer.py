from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date

from apple_health.enums import WorkoutType
from apple_health.models import Workout
from apple_health.models import AppleHealthData
from apple_health.report_models import ActivitySummary
from apple_health.report_models import DailySummary
from apple_health.report_models import MonthlySummary
from apple_health.report_models import ActivityMetricsSummary


class WorkoutAnalyzer:
    def __init__(self, health_data: AppleHealthData) -> None:
        self.workouts = health_data.workouts
        self.daily_metrics = health_data.daily_metrics

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
        
    def summarize_month_activities(
        self,
        year: int,
        month: int,
    ) -> list[ActivitySummary]:
        monthly_workouts = [
            workout
            for day in self.workouts_by_day()
            if day.year == year and day.month == month
            for workout in self.workouts_for_day(day)
        ]
        
        activities: dict[WorkoutType, list[Workout]] = {}

        for workout in monthly_workouts:
            activities.setdefault(workout.activity_type, []).append(workout)
    
        summaries: list[ActivitySummary] = []

        for activity_type, workouts in activities.items():
            distances = [
                workout.distance_km
                for workout in workouts
                if workout.distance_km is not None
            ]

            summaries.append(
                ActivitySummary(
                    activity_type=activity_type,
                    sessions=len(workouts),
                    duration_minutes=sum(w.duration_minutes for w in workouts),
                    active_energy_kcal=sum(w.active_energy_kcal for w in workouts),
                    distance_km=sum(distances) if distances else None,
                )
            )
        return summaries
    
    def summarize_month_metrics(
        self,
        year: int,
        month: int,
    ) -> ActivityMetricsSummary:    
            monthly_metrics = [
                metrics
                for metrics in self.daily_metrics
                if metrics.date.year == year
                and metrics.date.month == month
            ]
            total_steps = sum(
                metrics.steps
                for metrics in monthly_metrics
            )

            total_distance = sum(
                metrics.distance_km
                for metrics in monthly_metrics
            )
            reporting_days = self._reporting_days(year, month)

            average_daily_steps = total_steps / reporting_days
            average_daily_distance = total_distance / reporting_days
            
            return ActivityMetricsSummary(
                total_steps=total_steps,
                average_daily_steps=average_daily_steps,
                total_distance_km=total_distance,
                average_daily_distance_km=average_daily_distance,
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
        
    def summarize_month(
        self,
        year: int,
        month: int,
    ) -> list[DailySummary]:
        daily_summaries = [
            self.summarize_day(day)
            for day in sorted(self.workouts_by_day())
            if day.year == year and day.month == month
        ]

        return MonthlySummary(
            year=year,
            month=month,
            reporting_days=self._reporting_days(year, month),
            days=daily_summaries,
            activities=self.summarize_month_activities(year, month),
            activity_metrics=self.summarize_month_metrics(year, month),
        )
        
    def _reporting_days(
        self,
        year: int,
        month: int,
    ) -> int:
        today = date.today()

        if year == today.year and month == today.month:
            return today.day

        return monthrange(year, month)[1]