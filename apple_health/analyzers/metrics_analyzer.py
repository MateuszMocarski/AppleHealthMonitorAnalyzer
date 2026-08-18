from __future__ import annotations

from datetime import date

from apple_health.models import AppleHealthData, DailyMetrics
from apple_health.report_models import ActivityMetricsSummary


class MetricsAnalyzer:
    def __init__(
        self,
        health_data: AppleHealthData,
    ) -> None:
        self.daily_metrics = health_data.daily_metrics
        self._daily_metrics_by_day = self._group_daily_metrics_by_day()

    def _group_daily_metrics_by_day(
        self,
    ) -> dict[date, DailyMetrics]:
        daily_metrics_by_day = {}

        for metrics in self.daily_metrics:
            daily_metrics_by_day[metrics.date] = metrics

        return daily_metrics_by_day

    def metrics_for_day(
        self,
        day: date,
    ) -> DailyMetrics | None:
        return self._daily_metrics_by_day.get(day)

    def summarize_month(
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

        average_carbohydrates_g = total_carbohydrates_g / reporting_days if reporting_days else 0.0

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
            average_carbohydrates_g=average_carbohydrates_g,
            average_fat_g=average_fat_g,
            average_calories_kcal=average_calories_kcal,
        )
