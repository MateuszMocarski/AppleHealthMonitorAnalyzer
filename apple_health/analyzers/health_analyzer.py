from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from apple_health.analyzers.activity_analyzer import ActivityAnalyzer
from apple_health.analyzers.metrics_analyzer import MetricsAnalyzer
from apple_health.analyzers.sleep_analyzer import SleepAnalyzer
from apple_health.models import AppleHealthData
from apple_health.report_models import DailySummary, MonthlySummary


class HealthAnalyzer:
    def __init__(self, health_data: AppleHealthData) -> None:

        self.activity_analyzer = ActivityAnalyzer(health_data)

        self.metrics_analyzer = MetricsAnalyzer(health_data)

        self.sleep_analyzer = SleepAnalyzer(health_data)

        self.last_data_day = max(metrics.date for metrics in health_data.daily_metrics)

    def summarize_day(self, day: date) -> DailySummary:

        activities = self.activity_analyzer.summarize_day(day)

        metrics = self.metrics_analyzer.metrics_for_day(day)

        active_energy_kcal = metrics.active_energy if metrics else 0.0
        basal_energy_kcal = metrics.basal_energy if metrics else 0.0

        weight = (
            metrics.weight.value if metrics is not None and metrics.weight is not None else None
        )

        nutrition = metrics.nutrition if metrics else None

        total_steps = metrics.steps if metrics else 0
        total_distance_km = metrics.distance_km if metrics else 0.0

        sleep_session = self.sleep_analyzer.session_for_day(day) if self.sleep_analyzer else None

        sleep_score = (
            self.sleep_analyzer.score_session(sleep_session) if sleep_session is not None else None
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

    def summarize_month(
        self,
        year: int,
        month: int,
    ) -> MonthlySummary:
        reporting_days = self._reporting_days(year, month)

        daily_summaries = [self.summarize_day(day) for day in self._days_in_month(year, month)]

        return MonthlySummary(
            year=year,
            month=month,
            reporting_days=reporting_days,
            days=daily_summaries,
            activities=self.activity_analyzer.summarize_month(
                year,
                month,
                reporting_days,
            ),
            activity_metrics=self.metrics_analyzer.summarize_month(
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
