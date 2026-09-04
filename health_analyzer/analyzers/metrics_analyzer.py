from __future__ import annotations

from datetime import date

from health_analyzer.models import HealthData, DailyMetrics
from health_analyzer.report_models import ActivityMetricsSummary


class MetricsAnalyzer:
    def __init__(
        self,
        health_data: HealthData,
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
    ) -> ActivityMetricsSummary | None:
        monthly_metrics = [
            metrics
            for metrics in self.daily_metrics
            if (
                metrics.date.year == year
                and metrics.date.month == month
                and metrics.date.day <= reporting_days
            )
        ]

        if not monthly_metrics:
            return None

        step_values = [metrics.steps for metrics in monthly_metrics if metrics.steps is not None]

        distance_values = [
            metrics.distance_km for metrics in monthly_metrics if metrics.distance_km is not None
        ]

        total_steps = sum(step_values) if step_values else None

        total_distance = sum(distance_values) if distance_values else None

        average_daily_steps = self._average_with_count(
            step_values,
        )

        average_daily_distance = self._average_with_count(
            distance_values,
        )

        step_length_metrics = [
            metrics
            for metrics in monthly_metrics
            if (metrics.steps is not None and metrics.distance_km is not None)
        ]

        if step_length_metrics:
            step_length_steps = sum(metrics.steps for metrics in step_length_metrics)

            step_length_distance = sum(metrics.distance_km for metrics in step_length_metrics)

            average_step_length_cm = (
                (100000 * step_length_distance / step_length_steps if step_length_steps else 0.0),
                len(step_length_metrics),
            )
        else:
            average_step_length_cm = None

        basal_energy_values = [
            metrics.basal_energy for metrics in monthly_metrics if metrics.basal_energy is not None
        ]

        active_energy_values = [
            metrics.active_energy
            for metrics in monthly_metrics
            if metrics.active_energy is not None
        ]

        average_basal_energy_kcal = self._average_with_count(basal_energy_values)

        average_active_energy_kcal = self._average_with_count(active_energy_values)

        tdee_values = [
            metrics.basal_energy + metrics.active_energy
            for metrics in monthly_metrics
            if (metrics.basal_energy is not None and metrics.active_energy is not None)
        ]

        average_tdee_kcal = self._average_with_count(tdee_values)

        calorie_balance_values = [
            metrics.nutrition.calories_kcal - metrics.basal_energy - metrics.active_energy
            for metrics in monthly_metrics
            if (
                metrics.nutrition is not None
                and metrics.nutrition.calories_kcal is not None
                and metrics.basal_energy is not None
                and metrics.active_energy is not None
            )
        ]

        average_calories_balance_kcal = self._average_with_count(calorie_balance_values)

        protein_values = [
            metrics.nutrition.protein_g
            for metrics in monthly_metrics
            if (metrics.nutrition is not None and metrics.nutrition.protein_g is not None)
        ]

        carbohydrate_values = [
            metrics.nutrition.carbohydrates_g
            for metrics in monthly_metrics
            if (metrics.nutrition is not None and metrics.nutrition.carbohydrates_g is not None)
        ]

        fat_values = [
            metrics.nutrition.fat_g
            for metrics in monthly_metrics
            if (metrics.nutrition is not None and metrics.nutrition.fat_g is not None)
        ]

        calorie_values = [
            metrics.nutrition.calories_kcal
            for metrics in monthly_metrics
            if (metrics.nutrition is not None and metrics.nutrition.calories_kcal is not None)
        ]

        average_protein_g = self._average_with_count(protein_values)
        average_carbohydrates_g = self._average_with_count(carbohydrate_values)
        average_fat_g = self._average_with_count(fat_values)
        average_calories_kcal = self._average_with_count(calorie_values)

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
            average_tdee_kcal=average_tdee_kcal,
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
            average_calories_balance_kcal=average_calories_balance_kcal,
        )

    @staticmethod
    def _average_with_count(
        values: list[float | int],
    ) -> tuple[float, int] | None:
        if not values:
            return None

        return sum(values) / len(values), len(values)
