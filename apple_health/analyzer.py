from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, time, timedelta

from apple_health.constants import APPLE_WATCH_SOURCE
from apple_health.enums import SleepStage, WorkoutType
from apple_health.models import AppleHealthData, SleepRecord, Workout
from apple_health.report_models import (
    ActivityMetricsSummary,
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
    SleepScore,
    SleepSession,
)
from apple_health.sleep_score_config import *

class WorkoutAnalyzer:
    def __init__(self, health_data: AppleHealthData, sleep_analyzer: SleepAnalyzer) -> None:
        self.workouts = health_data.workouts
        self.daily_metrics = health_data.daily_metrics

        self._workouts_by_day = self._group_workouts_by_day()
        self._daily_metrics_by_day = self._group_daily_metrics_by_day()
        
        self.last_data_day = max(
            metrics.date
            for metrics in self.daily_metrics
        )

        sleep_analyzer: SleepAnalyzer
        self.sleep_analyzer = sleep_analyzer

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

        active_energy_kcal = metrics.active_energy if metrics else 0.0
        basal_energy_kcal = metrics.basal_energy if metrics else 0.0

        weight = (
            metrics.weight.value if metrics is not None and metrics.weight is not None else None
        )

        nutrition = metrics.nutrition if metrics else None

        total_steps = metrics.steps if metrics else 0
        total_distance_km = metrics.distance_km if metrics else 0.0

        sleep_session = self.sleep_analyzer.session_for_day(day) if self.sleep_analyzer else None
        
        sleep_score = (self.sleep_analyzer.score_session(sleep_session) if sleep_session is not None else None
)
        
        return DailySummary(
            date=day,
            weight=weight,
            nutrition=nutrition,
            activities=activities,
            total_duration_minutes=sum(activity.duration_minutes for activity in activities),
            total_active_energy_kcal=sum(activity.active_energy_kcal for activity in activities),
            active_energy_kcal=active_energy_kcal,
            basal_energy_kcal=basal_energy_kcal,
            total_steps=total_steps,
            total_distance_km=total_distance_km,
            sleep_session=sleep_session,
            sleep_score=sleep_score,
        )

    def summarize_month_activities(
        self,
        year: int,
        month: int,
        reporting_days: int,
    ) -> list[ActivitySummary]:
        monthly_workouts = [
            workout
            for day in self.workouts_by_day()
            if (day.year == year and day.month == month and day.day <= reporting_days)
            for workout in self.workouts_for_day(day)
        ]

        activities: dict[WorkoutType, list[Workout]] = {}

        for workout in monthly_workouts:
            activities.setdefault(workout.activity_type, []).append(workout)

        summaries: list[ActivitySummary] = []

        for activity_type, workouts in activities.items():
            distances = [
                workout.distance_km for workout in workouts if workout.distance_km is not None
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
        reporting_days: int,
    ) -> ActivityMetricsSummary:
        monthly_metrics = [
            metrics
            for metrics in self.daily_metrics
            if (
                metrics.date.year == year
                and metrics.date.month == month
                and metrics.date.day <= reporting_days
            )
        ]

        total_steps = sum(metrics.steps for metrics in monthly_metrics)
        total_distance = sum(metrics.distance_km for metrics in monthly_metrics)

        total_basal_energy_kcal = sum(metrics.basal_energy for metrics in monthly_metrics)
        total_active_energy_kcal = sum(metrics.active_energy for metrics in monthly_metrics)

        total_protein_g = sum(
            metrics.nutrition.protein_g
            for metrics in monthly_metrics
            if metrics.nutrition is not None
        )
        total_carbohydrates_g = sum(
            metrics.nutrition.carbohydrates_g
            for metrics in monthly_metrics
            if metrics.nutrition is not None
        )
        total_fat_g = sum(
            metrics.nutrition.fat_g for metrics in monthly_metrics if metrics.nutrition is not None
        )
        total_calories_kcal = sum(
            metrics.nutrition.calories_kcal
            for metrics in monthly_metrics
            if metrics.nutrition is not None
        )

        average_daily_steps = total_steps / reporting_days if reporting_days else 0.0
        average_daily_distance = total_distance / reporting_days if reporting_days else 0.0
        average_basal_energy_kcal = (
            total_basal_energy_kcal / reporting_days if reporting_days else 0.0
        )
        average_active_energy_kcal = (
            total_active_energy_kcal / reporting_days if reporting_days else 0.0
        )

        average_step_length_cm = 100000 * total_distance / total_steps if total_steps else 0.0

        average_protein_g = total_protein_g / reporting_days if reporting_days else 0.0
        average_carbohyrates_g = total_carbohydrates_g / reporting_days if reporting_days else 0.0
        average_fat_g = total_fat_g / reporting_days if reporting_days else 0.0
        average_calories_kcal = total_calories_kcal / reporting_days if reporting_days else 0.0

        weights = [
            metrics.weight.value for metrics in monthly_metrics if metrics.weight is not None
        ]

        if weights:
            min_weight = min(weights)
            max_weight = max(weights)
            start_weight = weights[0]
            end_weight = weights[-1]
            measurements = len(weights)
            average_weight = sum(weights) / len(weights)
        else:
            min_weight = None
            max_weight = None
            start_weight = None
            end_weight = None
            measurements = 0
            average_weight = None

        return ActivityMetricsSummary(
            total_steps=total_steps,
            average_daily_steps=average_daily_steps,
            total_distance_km=total_distance,
            average_daily_distance_km=average_daily_distance,
            average_step_length_cm=average_step_length_cm,
            average_basal_energy_kcal=average_basal_energy_kcal,
            average_active_energy_kcal=average_active_energy_kcal,
            average_weight=average_weight,
            start_weight=start_weight,
            end_weight=end_weight,
            max_weight=max_weight,
            min_weight=min_weight,
            measurements=measurements,
            average_protein_g=average_protein_g,
            average_carbohydrates_g=average_carbohyrates_g,
            average_fat_g=average_fat_g,
            average_calories_kcal=average_calories_kcal,
        )

    def _build_activity_summary(
        self,
        activity_type: WorkoutType,
        workouts: list[Workout],
    ) -> ActivitySummary:
        distance = [workout.distance_km for workout in workouts if workout.distance_km is not None]

        return ActivitySummary(
            activity_type=activity_type,
            sessions=len(workouts),
            duration_minutes=sum(workout.duration_minutes for workout in workouts),
            active_energy_kcal=sum(workout.active_energy_kcal or 0 for workout in workouts),
            distance_km=(sum(distance) if distance else None),
        )

    def summarize_month(
        self,
        year: int,
        month: int,
    ) -> list[DailySummary]:
        reporting_days = self._reporting_days(year, month)

        daily_summaries = [self.summarize_day(day) for day in self._days_in_month(year, month)]

        return MonthlySummary(
            year=year,
            month=month,
            reporting_days=reporting_days,
            days=daily_summaries,
            activities=self.summarize_month_activities(
                year,
                month,
                reporting_days,
            ),
            activity_metrics=self.summarize_month_metrics(
                year,
                month,
                reporting_days,
            ),
            sleep_summary=self.sleep_analyzer.summarize_month(
                year,
                month,
                reporting_days,
            ),
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
        last_complete_day = self.last_data_day - timedelta(days=1)

        if (year, month) < (
            last_complete_day.year,
            last_complete_day.month,
        ):
            return monthrange(year, month)[1]

        if (year, month) == (
            last_complete_day.year,
            last_complete_day.month,
        ):
            return last_complete_day.day

        return 0

    def _days_in_month(
        self,
        year: int,
        month: int,
    ) -> list[date]:
        return [date(year, month, day) for day in range(1, self._reporting_days(year, month) + 1)]


class SleepAnalyzer:
    SESSION_GAP_THRESHOLD = timedelta(minutes=30)

    def __init__(
        self,
        health_data: AppleHealthData,
    ) -> None:
        validate_sleep_score_config()

        self.sleep_records = health_data.sleep_records
        self.sleep_sessions = self.analyze()

        self._primary_sleep_sessions_by_day = (
            self._select_primary_sleep_sessions()
        )

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
        core_minutes = self._sum_stage_minutes(
            records,
            SleepStage.CORE,
        )

        deep_minutes = self._sum_stage_minutes(
            records,
            SleepStage.DEEP,
        )

        rem_minutes = self._sum_stage_minutes(
            records,
            SleepStage.REM,
        )

        awake_minutes = self._sum_stage_minutes(
            records,
            SleepStage.AWAKE,
        )

        time_asleep_minutes = (
            core_minutes
            + deep_minutes
            + rem_minutes
        )

        bedtime = records[0].start
        wake_up = records[-1].end

        return SleepSession(
            bedtime=bedtime,
            wake_up=wake_up,
            records=records,
            time_in_bed_minutes=(
                wake_up - bedtime
            ).total_seconds()
            / 60,
            time_asleep_minutes=time_asleep_minutes,
            core_minutes=core_minutes,
            deep_minutes=deep_minutes,
            rem_minutes=rem_minutes,
            awake_minutes=awake_minutes,
        )

    def summarize_month(
        self,
        year: int,
        month: int,
        reporting_days: int,
    ) -> SleepMonthlySummary:
        sessions = [
            session
            for day, session
            in self._primary_sleep_sessions_by_day.items()
            if (
                day.year == year
                and day.month == month
                and day.day <= reporting_days
            )
        ]

        bedtimes = [
            session.bedtime.time()
            for session in sessions
        ]

        wake_ups = [
            session.wake_up.time()
            for session in sessions
        ]

        sleep_minutes = [
            session.time_asleep_minutes
            for session in sessions
        ]

        awake_minutes = [
            session.awake_minutes
            for session in sessions
        ]

        efficiency = [
            session.sleep_efficiency_percent
            for session in sessions
        ]

        core = [
            session.core_minutes
            for session in sessions
        ]

        deep = [
            session.deep_minutes
            for session in sessions
        ]

        rem = [
            session.rem_minutes
            for session in sessions
        ]

        sleep_scores = [
            self.score_session(session).total_score
            for session in sessions
        ]

        return SleepMonthlySummary(
            total_sessions=len(sessions),
            average_bedtime=self._average_time(bedtimes),
            average_wake_up=self._average_time(wake_ups),
            average_sleep_minutes=self._average(
                sleep_minutes
            ),
            average_awake_minutes=self._average(
                awake_minutes
            ),
            average_sleep_efficiency=self._average(
                efficiency
            ),
            average_core_minutes=self._average(core),
            average_deep_minutes=self._average(deep),
            average_rem_minutes=self._average(rem),
            average_sleep_score=self._average(
                sleep_scores
            ),
        )

    def _sum_stage_minutes(
        self,
        records: list[SleepRecord],
        stage: SleepStage,
    ) -> float:
        return sum(
            record.duration_minutes
            for record in records
            if record.stage == stage
        )

    def session_for_day(
        self,
        day: date,
    ) -> SleepSession | None:
        return self._primary_sleep_sessions_by_day.get(
            day
        )

    @staticmethod
    def _average_time(
        times: list[time],
    ) -> time:
        """
        Calculates the average time of day.

        Times are shifted around midnight so that typical sleep hours
        become a linear range:

            23:30 -> -30
            00:30 ->  30
            02:00 -> 120
        """

        if not times:
            raise ValueError(
                "Cannot calculate average of an empty time collection."
            )

        shifted_minutes = []

        for value in times:
            minutes = (
                value.hour * 60
                + value.minute
            )

            if minutes >= 12 * 60:
                minutes -= 24 * 60

            shifted_minutes.append(minutes)

        average = (
            sum(shifted_minutes)
            / len(shifted_minutes)
        )

        if average < 0:
            average += 24 * 60

        average = round(average)

        hours, minutes = divmod(
            average,
            60,
        )

        return time(
            hour=hours,
            minute=minutes,
        )

    @staticmethod
    def _average(
        values: list[float],
    ) -> float:
        if not values:
            raise ValueError(
                "Cannot calculate average of an empty collection."
            )

        return sum(values) / len(values)

    def _select_primary_sleep_sessions(
        self,
    ) -> dict[date, SleepSession]:
        primary_sessions: dict[
            date,
            SleepSession,
        ] = {}

        for session in self.sleep_sessions:
            day = session.reporting_date
            current = primary_sessions.get(day)

            if (
                current is None
                or session.time_asleep_minutes
                > current.time_asleep_minutes
            ):
                primary_sessions[day] = session

        return primary_sessions

    def _calculate_penalty(
        self,
        deviation_minutes: float,
        interval_minutes: float,
        penalty_points: float,
    ) -> float:
        if deviation_minutes <= 0:
            return 0.0

        if SLEEP_SCORE_LINEAR_PENALTIES:
            return (
                deviation_minutes
                / interval_minutes
                * penalty_points
            )

        return (
            deviation_minutes
            // interval_minutes
        ) * penalty_points

    @staticmethod
    def _minutes_relative_to_midnight(
        value: time,
    ) -> int:
        minutes = (
            value.hour * 60
            + value.minute
        )

        if minutes >= 12 * 60:
            minutes -= 24 * 60

        return minutes

    def _calculate_bedtime_score(
        self,
        session: SleepSession,
    ) -> float:
        bedtime_minutes = (
            self._minutes_relative_to_midnight(
                session.bedtime.time()
            )
        )

        target_minutes = (
            self._minutes_relative_to_midnight(
                BEDTIME_TARGET
            )
        )

        if bedtime_minutes <= target_minutes:
            return 100.0

        delay_minutes = (
            bedtime_minutes
            - target_minutes
        )

        penalty = self._calculate_penalty(
            deviation_minutes=delay_minutes,
            interval_minutes=(
                BEDTIME_PENALTY_INTERVAL_MINUTES
            ),
            penalty_points=BEDTIME_PENALTY_POINTS,
        )

        return max(
            0.0,
            100.0 - penalty,
        )

    def _calculate_duration_score(
        self,
        session: SleepSession,
    ) -> float:
        duration_minutes = (
            session.time_asleep_minutes
        )

        lower_bound = (
            SLEEP_DURATION_TARGET_MINUTES
            - SLEEP_DURATION_TOLERANCE_MINUTES
        )

        upper_bound = (
            SLEEP_DURATION_TARGET_MINUTES
            + SLEEP_DURATION_TOLERANCE_MINUTES
        )

        if (
            lower_bound
            <= duration_minutes
            <= upper_bound
        ):
            return 100.0

        if duration_minutes < lower_bound:
            deviation_minutes = (
                lower_bound
                - duration_minutes
            )

            penalty_weight = (
                SLEEP_DURATION_UNDERSLEEP_WEIGHT
            )

        else:
            deviation_minutes = (
                duration_minutes
                - upper_bound
            )

            penalty_weight = (
                SLEEP_DURATION_OVERSLEEP_WEIGHT
            )

        penalty = self._calculate_penalty(
            deviation_minutes=deviation_minutes,
            interval_minutes=(
                SLEEP_DURATION_PENALTY_INTERVAL_MINUTES
            ),
            penalty_points=(
                SLEEP_DURATION_PENALTY_POINTS
            ),
        )

        penalty *= penalty_weight

        return max(
            0.0,
            100.0 - penalty,
        )

    def _calculate_wake_up_score(
        self,
        session: SleepSession,
        bedtime_score: float,
        duration_score: float,
    ) -> float:
        wake_up_max_score = (
            bedtime_score
            + duration_score
        ) / 2

        wake_up_minutes = (
            self._minutes_relative_to_midnight(
                session.wake_up.time()
            )
        )

        target_minutes = (
            self._minutes_relative_to_midnight(
                WAKE_UP_TARGET
            )
        )

        if wake_up_minutes <= target_minutes:
            return wake_up_max_score

        delay_minutes = (
            wake_up_minutes
            - target_minutes
        )

        penalty = self._calculate_penalty(
            deviation_minutes=delay_minutes,
            interval_minutes=(
                WAKE_UP_PENALTY_INTERVAL_MINUTES
            ),
            penalty_points=WAKE_UP_PENALTY_POINTS,
        )

        return max(
            0.0,
            wake_up_max_score - penalty,
        )

    def score_session(
        self,
        session: SleepSession,
    ) -> SleepScore:
        bedtime_score = (
            self._calculate_bedtime_score(
                session
            )
        )

        duration_score = (
            self._calculate_duration_score(
                session
            )
        )

        wake_up_score = (
            self._calculate_wake_up_score(
                session,
                bedtime_score,
                duration_score,
            )
        )

        return SleepScore(
            bedtime_score=bedtime_score,
            duration_score=duration_score,
            wake_up_score=wake_up_score,
        )