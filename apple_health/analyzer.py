from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date, timedelta

from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import WorkoutType
from apple_health.models import SleepRecord, Workout
from apple_health.models import AppleHealthData
from apple_health.report_models import ActivitySummary, SleepSession
from apple_health.report_models import DailySummary
from apple_health.report_models import MonthlySummary
from apple_health.report_models import ActivityMetricsSummary


class WorkoutAnalyzer:
    def __init__(self, health_data: AppleHealthData) -> None:
        self.workouts = health_data.workouts
        self.daily_metrics = health_data.daily_metrics

        self._workouts_by_day = self._group_workouts_by_day()
        self._daily_metrics_by_day = self._group_daily_metrics_by_day()

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
    
    def daily_metrics_for_day(self, day: date):
        return self._daily_metrics_by_day.get(day)

    def summarize_day(self, day: date) -> DailySummary:
        grouped: dict[WorkoutType, list[Workout]] = defaultdict(list)

        for workout in self.workouts_for_day(day):
            grouped[workout.activity_type].append(workout)

        activities = [
            self._build_activity_summary(activity_type, workouts)
            for activity_type, workouts in grouped.items()
        ]
        
        metrics = self.daily_metrics_for_day(day)

        total_steps = metrics.steps if metrics else 0
        total_distance_km = metrics.distance_km if metrics else 0.0

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
            total_steps=total_steps,
            total_distance_km=total_distance_km,
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
            
            average_step_length_cm = 100000 * total_distance / total_steps
            
            return ActivityMetricsSummary(
                total_steps=total_steps,
                average_daily_steps=average_daily_steps,
                total_distance_km=total_distance,
                average_daily_distance_km=average_daily_distance,
                average_step_length_cm=average_step_length_cm
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
            for day in self._days_in_month(year, month)
        ]

        return MonthlySummary(
            year=year,
            month=month,
            reporting_days=self._reporting_days(year, month),
            days=daily_summaries,
            activities=self.summarize_month_activities(year, month),
            activity_metrics=self.summarize_month_metrics(year, month),
        )
        
    def _group_daily_metrics_by_day(self):
        daily_metrics_by_day = {}

        for metrics in self.daily_metrics:
            daily_metrics_by_day[metrics.date] = metrics

        return daily_metrics_by_day
        
    def _reporting_days(
        self,
        year: int,
        month: int,
    ) -> int:
        today = date.today()

        if year == today.year and month == today.month:
            return today.day

        return monthrange(year, month)[1]
    
    def _days_in_month(
        self,
        year: int,
        month: int,
    ) -> list[date]:
        return [
            date(year, month, day)
            for day in range(1, self._reporting_days(year, month) + 1)
        ]

class SleepAnalyzer:
    SESSION_GAP_THRESHOLD = timedelta(minutes=30)

    def __init__(
        self,
        health_data: AppleHealthData,
    ) -> None:
        self.sleep_records = health_data.sleep_records

    def analyze(self) -> list[SleepSession]:
        watch_sleep_records = [
            record
            for record in self.sleep_records
            if APPLE_WATCH_SOURCE in record.source_name
        ]

        sessions: list[SleepSession] = []
        current_session: list[SleepRecord] = []

        for record in watch_sleep_records:
            if not current_session:
                current_session.append(record)
                continue

            previous = current_session[-1]
            gap = record.start - previous.end

            if gap <= self.SESSION_GAP_THRESHOLD:
                current_session.append(record)
            else:
                sessions.append(
                    self._build_sleep_session(current_session)
                )
                current_session = [record]

        if current_session:
            sessions.append(
                self._build_sleep_session(current_session)
            )

        return sessions

    def _build_sleep_session(
        self,
        records: list[SleepRecord],
    ) -> SleepSession:
        bedtime = records[0].start
        wake_up = records[-1].end

        return SleepSession(
            session_date=wake_up.date(),
            bedtime=bedtime,
            wake_up=wake_up,
            records=records,
            time_in_bed_minutes=(
                wake_up - bedtime
            ).total_seconds() / 60,
            time_asleep_minutes=0.0,
            core_minutes=0.0,
            deep_minutes=0.0,
            rem_minutes=0.0,
            awake_minutes=0.0,
        )