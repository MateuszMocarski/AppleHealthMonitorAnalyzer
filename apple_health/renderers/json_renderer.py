from __future__ import annotations

import json
from typing import Any

from apple_health.config.app_config import AppConfig
from apple_health.enums import WorkoutType
from apple_health.report_models import (
    ActivityMetricsSummary,
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
)


class JsonRenderer:
    def __init__(
        self,
        config: AppConfig | None = None,
    ) -> None:
        self.config = config or AppConfig()

    SCHEMA_VERSION = "1.0"

    def render_month_summary(
        self,
        summary: MonthlySummary,
    ) -> str:
        payload = self._build_month_summary_payload(summary)

        return json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )

    def render_month(
        self,
        summary: MonthlySummary,
    ) -> str:
        payload = self._build_month_summary_payload(summary)

        payload["days"] = [self._build_day(day) for day in summary.days]

        return json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )

    def _build_month_summary_payload(
        self,
        summary: MonthlySummary,
    ) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "report": self._build_report_metadata(summary),
            "general_activity": self._build_general_activity(summary.activity_metrics),
            "sleep": self._build_sleep(summary.sleep_summary),
            "workouts": self._build_workouts(
                summary.activities,
                summary.reporting_days,
            ),
            "body_weight": self._build_body_weight(summary.activity_metrics),
            "energy_expenditure": self._build_energy_expenditure(summary.activity_metrics),
            "nutrition": self._build_nutrition(summary.activity_metrics),
            "average_calories_balance_kcal": self._build_average_calories_balance(
                summary.activity_metrics
            ),
        }

    @staticmethod
    def _build_report_metadata(
        summary: MonthlySummary,
    ) -> dict[str, Any]:
        return {
            "type": "monthly",
            "year": summary.year,
            "month": summary.month,
            "reporting_days": summary.reporting_days,
            "data_through": (
                summary.data_through.isoformat() if summary.data_through is not None else None
            ),
        }

    def _build_general_activity(
        self,
        metrics: ActivityMetricsSummary | None,
    ) -> dict[str, Any] | None:
        if metrics is None:
            return None

        if metrics.total_steps is None and metrics.total_distance_km is None:
            return None

        return {
            "total_steps": metrics.total_steps,
            "average_daily_steps": self._round_number(metrics.average_daily_steps),
            "total_distance_km": self._round_number(metrics.total_distance_km),
            "average_daily_distance_km": self._round_number(metrics.average_daily_distance_km),
            "average_step_length_cm": self._round_number(metrics.average_step_length_cm),
        }

    def _build_sleep(
        self,
        summary: SleepMonthlySummary | None,
    ) -> dict[str, Any] | None:
        if summary is None:
            return None

        return {
            "sessions": summary.total_sessions,
            "average_bedtime": (summary.average_bedtime.strftime("%H:%M")),
            "average_wake_up": (summary.average_wake_up.strftime("%H:%M")),
            "average_sleep_minutes": self._round_number(summary.average_sleep_minutes),
            "average_awake_minutes": self._round_number(summary.average_awake_minutes),
            "average_efficiency_percent": self._round_number(summary.average_sleep_efficiency),
            "stages": {
                "core_minutes": self._round_number(summary.average_core_minutes),
                "deep_minutes": self._round_number(summary.average_deep_minutes),
                "rem_minutes": self._round_number(summary.average_rem_minutes),
            },
            "score": {
                "average_bedtime": self._round_number(summary.average_bedtime_score),
                "average_duration": self._round_number(summary.average_duration_score),
                "average_wake_up": self._round_number(summary.average_wake_up_score),
                "average_total": self._round_number(summary.average_sleep_score),
                "average_bonus": self._round_number(summary.average_bonus),
                "consistency_bonus": self._round_number(summary.consistency_bonus),
                "monthly_score": self._round_number(summary.monthly_sleep_score),
                "monthly_score_max": 100 + self.config.sleep.score.monthly_bonus.max_points,
            },
        }

    def _build_workouts(
        self,
        activities: list[ActivitySummary],
        reporting_days: int,
    ) -> list[dict[str, Any]]:
        return [
            self._build_workout(
                activity,
                reporting_days,
            )
            for activity in activities
        ]

    def _build_workout(
        self,
        activity: ActivitySummary,
        reporting_days: int,
    ) -> dict[str, Any]:
        is_cycling = activity.activity_type in (
            WorkoutType.OUTDOOR_CYCLING,
            WorkoutType.INDOOR_CYCLING,
        )

        divisor = activity.sessions if is_cycling else reporting_days

        average_basis = "workout" if is_cycling else "daily"

        return {
            "type": activity.activity_type.name.lower(),
            "sessions": activity.sessions,
            "duration_minutes": self._round_number(activity.duration_minutes),
            "active_energy_kcal": self._round_number(activity.active_energy_kcal),
            "distance_km": self._round_number(activity.distance_km),
            "average_basis": average_basis,
            "average_duration_minutes": self._round_number(
                activity.duration_minutes / divisor if divisor else None
            ),
            "average_active_energy_kcal": self._round_number(
                activity.active_energy_kcal / divisor if divisor else None
            ),
            "average_distance_km": self._round_number(
                activity.distance_km / divisor
                if (divisor and activity.distance_km is not None)
                else None
            ),
        }

    def _build_body_weight(
        self,
        metrics: ActivityMetricsSummary | None,
    ) -> dict[str, Any] | None:
        if metrics is None or metrics.measurements == 0:
            return None

        return {
            "average_kg": self._round_number(metrics.average_weight),
            "start_kg": metrics.start_weight,
            "end_kg": metrics.end_weight,
            "change_kg": self._round_number(metrics.weight_change),
            "max_kg": metrics.max_weight,
            "min_kg": metrics.min_weight,
            "measurements": metrics.measurements,
        }

    def _build_energy_expenditure(
        self,
        metrics: ActivityMetricsSummary | None,
    ) -> dict[str, Any] | None:
        if metrics is None:
            return None

        if metrics.average_basal_energy_kcal is None and metrics.average_active_energy_kcal is None:
            return None

        return {
            "average_basal_kcal": self._round_number(metrics.average_basal_energy_kcal),
            "average_active_kcal": self._round_number(metrics.average_active_energy_kcal),
            "average_tdee_kcal": self._round_number(metrics.average_tdee_kcal),
        }

    def _build_nutrition(
        self,
        metrics: ActivityMetricsSummary | None,
    ) -> dict[str, Any] | None:
        if metrics is None:
            return None

        if (
            metrics.average_protein_g is None
            and metrics.average_carbohydrates_g is None
            and metrics.average_fat_g is None
            and metrics.average_calories_kcal is None
        ):
            return None

        return {
            "average_protein_g": self._round_number(metrics.average_protein_g),
            "average_carbohydrates_g": self._round_number(metrics.average_carbohydrates_g),
            "average_fat_g": self._round_number(metrics.average_fat_g),
            "average_calories_kcal": self._round_number(metrics.average_calories_kcal),
        }

    def _build_average_calories_balance(
        self,
        metrics: ActivityMetricsSummary,
    ) -> float | None:
        if metrics is None:
            return None
        return self._round_number(metrics.average_calories_balance)

    @staticmethod
    def _round_number(
        number: float | None,
    ) -> float | None:
        if number is None:
            return None

        return round(number, 2)

    def _build_day(
        self,
        summary: DailySummary,
    ) -> dict[str, Any]:
        return {
            "date": summary.date.isoformat(),
            "general_activity": self._build_daily_general_activity(summary),
            "sleep": self._build_daily_sleep(summary),
            "workouts": self._build_daily_workouts(summary),
            "body_weight": self._build_daily_body_weight(summary),
            "energy_expenditure": self._build_daily_energy_expenditure(summary),
            "nutrition": self._build_daily_nutrition(summary),
            "calories_balance_kcal": self._round_number(summary.calories_balance_kcal),
        }

    def _build_daily_general_activity(
        self,
        summary: DailySummary,
    ) -> dict[str, Any]:
        return {
            "steps": summary.total_steps,
            "distance_km": self._round_number(summary.total_distance_km),
            "step_length_cm": self._round_number(summary.average_step_length_cm),
        }

    def _build_daily_sleep(
        self,
        summary: DailySummary,
    ) -> dict[str, Any] | None:
        if summary.sleep_session is None:
            return None

        return {
            "session": self._build_daily_sleep_session(summary),
            "score": self._build_daily_sleep_score(summary),
        }

    def _build_daily_sleep_session(
        self,
        summary: DailySummary,
    ) -> dict[str, Any]:
        sleep = summary.sleep_session

        if sleep is None:
            return {}

        return {
            "bedtime": sleep.bedtime.isoformat(),
            "wake_up": sleep.wake_up.isoformat(),
            "time_in_bed_minutes": self._round_number(sleep.time_in_bed_minutes),
            "time_asleep_minutes": self._round_number(sleep.time_asleep_minutes),
            "awake_minutes": self._round_number(sleep.awake_minutes),
            "efficiency_percent": self._round_number(sleep.sleep_efficiency_percent),
            "stages": {
                "core_minutes": self._round_number(sleep.core_minutes),
                "deep_minutes": self._round_number(sleep.deep_minutes),
                "rem_minutes": self._round_number(sleep.rem_minutes),
            },
        }

    def _build_daily_sleep_score(
        self,
        summary: DailySummary,
    ) -> dict[str, Any] | None:
        score = summary.sleep_score

        if score is None:
            return None

        return {
            "bedtime": self._round_number(score.bedtime_score),
            "duration": self._round_number(score.duration_score),
            "wake_up": self._round_number(score.wake_up_score),
            "total": self._round_number(score.total_score),
        }

    def _build_daily_workouts(
        self,
        summary: DailySummary,
    ) -> list[dict[str, Any]]:
        return [self._build_daily_workout(activity) for activity in summary.activities]

    def _build_daily_workout(
        self,
        activity: ActivitySummary,
    ) -> dict[str, Any]:
        return {
            "type": activity.activity_type.name.lower(),
            "sessions": activity.sessions,
            "duration_minutes": self._round_number(activity.duration_minutes),
            "active_energy_kcal": self._round_number(activity.active_energy_kcal),
            "distance_km": self._round_number(activity.distance_km),
        }

    def _build_daily_body_weight(
        self,
        summary: DailySummary,
    ) -> dict[str, Any] | None:
        if summary.weight is None:
            return None

        return {
            "weight_kg": self._round_number(summary.weight),
        }

    def _build_daily_energy_expenditure(
        self,
        summary: DailySummary,
    ) -> dict[str, Any]:
        return {
            "basal_kcal": self._round_number(summary.basal_energy_kcal),
            "active_kcal": self._round_number(summary.active_energy_kcal),
            "tdee_kcal": self._round_number(summary.tdee_kcal),
        }

    def _build_daily_nutrition(
        self,
        summary: DailySummary,
    ) -> dict[str, Any] | None:
        nutrition = summary.nutrition

        if nutrition is None:
            return None

        return {
            "protein_g": self._round_number(nutrition.protein_g),
            "carbohydrates_g": self._round_number(nutrition.carbohydrates_g),
            "fat_g": self._round_number(nutrition.fat_g),
            "calories_kcal": self._round_number(nutrition.calories_kcal),
        }
