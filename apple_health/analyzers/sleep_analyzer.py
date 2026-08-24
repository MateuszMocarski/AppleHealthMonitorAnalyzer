from __future__ import annotations

from datetime import date, time, timedelta
from statistics import pstdev

from apple_health.config.app_config import AppConfig
from apple_health.enums import SleepStage
from apple_health.models import AppleHealthData, SleepRecord
from apple_health.report_models import (
    SleepMonthlySummary,
    SleepScore,
    SleepSession,
)


class SleepAnalyzer:
    def __init__(self, health_data: AppleHealthData, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig()

        self.config.sleep.score.validate()

        self.sleep_records = health_data.sleep_records
        self.sleep_sessions = self.analyze()

        self._primary_sleep_sessions_by_day = self._select_primary_sleep_sessions()

    def analyze(self) -> list[SleepSession]:
        session_gap_threshold = timedelta(minutes=self.config.sleep.session_gap_threshold_minutes)
        watch_sleep_records = [
            record
            for record in self.sleep_records
            if (self.config.source.apple_watch_source in record.source_name)
        ]

        sessions: list[SleepSession] = []
        current_session: list[SleepRecord] = []

        for record in watch_sleep_records:
            if not current_session:
                current_session.append(record)
                continue

            previous = current_session[-1]
            gap = record.start - previous.end

            if gap <= session_gap_threshold:
                current_session.append(record)
            else:
                sessions.append(self._build_sleep_session(current_session))
                current_session = [record]

        if current_session:
            sessions.append(self._build_sleep_session(current_session))

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

        time_asleep_minutes = core_minutes + deep_minutes + rem_minutes

        bedtime = records[0].start
        wake_up = records[-1].end

        return SleepSession(
            bedtime=bedtime,
            wake_up=wake_up,
            records=records,
            time_in_bed_minutes=(wake_up - bedtime).total_seconds() / 60,
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
    ) -> SleepMonthlySummary | None:
        sessions = [
            session
            for day, session in self._primary_sleep_sessions_by_day.items()
            if (day.year == year and day.month == month and day.day <= reporting_days)
        ]

        if not sessions:
            return None

        bedtimes = [session.bedtime.time() for session in sessions]

        wake_ups = [session.wake_up.time() for session in sessions]

        sleep_minutes = [session.time_asleep_minutes for session in sessions]

        awake_minutes = [session.awake_minutes for session in sessions]

        efficiency = [session.sleep_efficiency_percent for session in sessions]

        core = [session.core_minutes for session in sessions]

        deep = [session.deep_minutes for session in sessions]

        rem = [session.rem_minutes for session in sessions]

        sleep_scores = [self.score_session(session) for session in sessions]

        average_bedtime_score = self._average([score.bedtime_score for score in sleep_scores])

        average_duration_score = self._average([score.duration_score for score in sleep_scores])

        average_wake_up_score = self._average([score.wake_up_score for score in sleep_scores])

        average_sleep_score = self._average([score.total_score for score in sleep_scores])

        average_bonus = self._calculate_average_sleep_bonus(average_sleep_score)

        consistency_bonus = self._calculate_consistency_bonus(sleep_scores)

        return SleepMonthlySummary(
            total_sessions=len(sessions),
            average_bedtime=self._average_time(bedtimes),
            average_wake_up=self._average_time(wake_ups),
            average_sleep_minutes=self._average(sleep_minutes),
            average_awake_minutes=self._average(awake_minutes),
            average_sleep_efficiency=self._average(efficiency),
            average_core_minutes=self._average(core),
            average_deep_minutes=self._average(deep),
            average_rem_minutes=self._average(rem),
            average_bedtime_score=average_bedtime_score,
            average_duration_score=average_duration_score,
            average_wake_up_score=average_wake_up_score,
            average_sleep_score=average_sleep_score,
            average_bonus=average_bonus,
            consistency_bonus=consistency_bonus,
        )

    def _sum_stage_minutes(
        self,
        records: list[SleepRecord],
        stage: SleepStage,
    ) -> float:
        return sum(record.duration_minutes for record in records if record.stage == stage)

    def session_for_day(
        self,
        day: date,
    ) -> SleepSession | None:
        return self._primary_sleep_sessions_by_day.get(day)

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
            raise ValueError("Cannot calculate average of an empty time collection.")

        shifted_minutes = []

        for value in times:
            minutes = value.hour * 60 + value.minute

            if minutes >= 12 * 60:
                minutes -= 24 * 60

            shifted_minutes.append(minutes)

        average = sum(shifted_minutes) / len(shifted_minutes)

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
            raise ValueError("Cannot calculate average of an empty collection.")

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

            if current is None or session.time_asleep_minutes > current.time_asleep_minutes:
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

        if self.config.sleep.score.linear_penalties:
            return deviation_minutes / interval_minutes * penalty_points

        return (deviation_minutes // interval_minutes) * penalty_points

    @staticmethod
    def _minutes_relative_to_midnight(
        value: time,
    ) -> int:
        minutes = value.hour * 60 + value.minute

        if minutes >= 12 * 60:
            minutes -= 24 * 60

        return minutes

    def _calculate_bedtime_score(
        self,
        session: SleepSession,
    ) -> float:
        bedtime_minutes = self._minutes_relative_to_midnight(session.bedtime.time())

        target_minutes = self._minutes_relative_to_midnight(self.config.sleep.score.bedtime.target)

        if bedtime_minutes <= target_minutes:
            return 100.0

        delay_minutes = bedtime_minutes - target_minutes

        penalty = self._calculate_penalty(
            deviation_minutes=delay_minutes,
            interval_minutes=self.config.sleep.score.bedtime.penalty_interval_minutes,
            penalty_points=self.config.sleep.score.bedtime.penalty_points,
        )

        return max(
            0.0,
            100.0 - penalty,
        )

    def _calculate_duration_score(
        self,
        session: SleepSession,
    ) -> float:
        duration_minutes = session.time_asleep_minutes

        duration_config = self.config.sleep.score.duration

        lower_bound = duration_config.target_minutes - duration_config.tolerance_minutes

        upper_bound = duration_config.target_minutes + duration_config.tolerance_minutes

        if lower_bound <= duration_minutes <= upper_bound:
            return 100.0

        if duration_minutes < lower_bound:
            deviation_minutes = lower_bound - duration_minutes

            penalty_weight = penalty_weight = duration_config.undersleep_weight

        else:
            deviation_minutes = duration_minutes - upper_bound

            penalty_weight = penalty_weight = duration_config.oversleep_weight

        penalty = self._calculate_penalty(
            deviation_minutes=deviation_minutes,
            interval_minutes=duration_config.penalty_interval_minutes,
            penalty_points=duration_config.penalty_points,
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

        wake_up_config = self.config.sleep.score.wake_up

        wake_up_max_score = (
            bedtime_score * wake_up_config.bedtime_weight
            + duration_score * wake_up_config.duration_weight
        ) / (wake_up_config.bedtime_weight + wake_up_config.duration_weight)

        wake_up_minutes = self._minutes_relative_to_midnight(session.wake_up.time())

        target_minutes = self._minutes_relative_to_midnight(self.config.sleep.score.wake_up.target)

        if wake_up_minutes <= target_minutes:
            return wake_up_max_score

        delay_minutes = wake_up_minutes - target_minutes

        penalty = self._calculate_penalty(
            deviation_minutes=delay_minutes,
            interval_minutes=self.config.sleep.score.wake_up.penalty_interval_minutes,
            penalty_points=self.config.sleep.score.wake_up.penalty_points,
        )

        return max(
            0.0,
            wake_up_max_score - penalty,
        )

    def score_session(
        self,
        session: SleepSession,
    ) -> SleepScore:
        bedtime_score = self._calculate_bedtime_score(session)

        duration_score = self._calculate_duration_score(session)

        wake_up_score = self._calculate_wake_up_score(
            session,
            bedtime_score,
            duration_score,
        )

        weights = self.config.sleep.score.weights

        total_score = (
            bedtime_score * weights.bedtime
            + duration_score * weights.duration
            + wake_up_score * weights.wake_up
        ) / (weights.bedtime + weights.duration + weights.wake_up)

        return SleepScore(
            bedtime_score=bedtime_score,
            duration_score=duration_score,
            wake_up_score=wake_up_score,
            total_score=total_score,
        )

    def _calculate_average_sleep_bonus(
        self,
        average_sleep_score: float,
    ) -> float:
        bonus_config = self.config.sleep.score.monthly_bonus

        if not bonus_config.enabled:
            return 0.0

        for threshold, bonus in bonus_config.average_thresholds:
            if average_sleep_score >= threshold:
                return float(bonus)

        return 0.0

    def _calculate_consistency_bonus(
        self,
        sleep_scores: list[SleepScore],
    ) -> float:
        bonus_config = self.config.sleep.score.monthly_bonus

        if not bonus_config.enabled:
            return 0.0

        if len(sleep_scores) < 2:
            return 0.0

        standard_deviation = pstdev(score.total_score for score in sleep_scores)

        for threshold, bonus in bonus_config.consistency_thresholds:
            if standard_deviation < threshold:
                return float(bonus)

        return 0.0
