from __future__ import annotations

import json
from typing import Any

from apple_health.enums import WorkoutType
from apple_health.report_models import (
    ActivityMetricsSummary,
    ActivitySummary,
    MonthlySummary,
    SleepMonthlySummary,
)
from apple_health.sleep_score_config import SLEEP_MONTHLY_BONUS_MAX_POINTS


class JsonRenderer:
    SCHEMA_VERSION = "1.0"

    def render_month_summary(
        self,
        summary: MonthlySummary,
    ) -> str:
        payload = self._build_month_summary_payload(
            summary
        )

        return json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        )

    def render_month(
        self,
        summary: MonthlySummary,
    ) -> str:
        payload = self._build_month_summary_payload(
            summary
        )

        payload["days"] = [
            self._build_day(day)
            for day in summary.days
        ]

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
            "report": self._build_report_metadata(
                summary
            ),
            "general_activity": self._build_general_activity(
                summary.activity_metrics
            ),
            "sleep": self._build_sleep(
                summary.sleep_summary
            ),
            "workouts": self._build_workouts(
                summary.activities,
                summary.reporting_days,
            ),
            "body_weight": self._build_body_weight(
                summary.activity_metrics
            ),
            "energy_expenditure": self._build_energy_expenditure(
                summary.activity_metrics
            ),
            "nutrition": self._build_nutrition(
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
                summary.data_through.isoformat()
                if summary.data_through is not None
                else None
            ),
        }

    def _build_general_activity(
        self,
        metrics: ActivityMetricsSummary | None,
    ) -> dict[str, Any] | None:
        if metrics is None:
            return None

        if (
            metrics.total_steps is None
            and metrics.total_distance_km is None
        ):
            return None

        return {
            "total_steps": metrics.total_steps,
            "average_daily_steps": self._round_number(
                metrics.average_daily_steps
            ),
            "total_distance_km": self._round_number(
                metrics.total_distance_km
            ),
            "average_daily_distance_km": self._round_number(
                metrics.average_daily_distance_km
            ),
            "average_step_length_cm": self._round_number(
                metrics.average_step_length_cm
            ),
        }
        
    def _build_sleep(
        self,
        summary: SleepMonthlySummary | None,
    ) -> dict[str, Any] | None:
        if summary is None:
            return None

        return {
            "sessions": summary.total_sessions,
            "average_bedtime": (
                summary.average_bedtime.strftime("%H:%M")
            ),
            "average_wake_up": (
                summary.average_wake_up.strftime("%H:%M")
            ),
            "average_sleep_minutes": self._round_number(
                summary.average_sleep_minutes
            ),
            "average_awake_minutes": self._round_number(
                summary.average_awake_minutes
            ),
            "average_efficiency_percent": self._round_number(
                summary.average_sleep_efficiency
            ),
            "stages": {
                "core_minutes": self._round_number(
                    summary.average_core_minutes
                ),
                "deep_minutes": self._round_number(
                    summary.average_deep_minutes
                ),
                "rem_minutes": self._round_number(
                    summary.average_rem_minutes
                ),
            },
            "score": {
                "average_bedtime": self._round_number(
                    summary.average_bedtime_score
                ),
                "average_duration": self._round_number(
                    summary.average_duration_score
                ),
                "average_wake_up": self._round_number(
                    summary.average_wake_up_score
                ),
                "average_total": self._round_number(
                    summary.average_sleep_score
                ),
                "average_bonus": self._round_number(
                    summary.average_bonus
                ),
                "consistency_bonus": self._round_number(
                    summary.consistency_bonus
                ),
                "monthly_score": self._round_number(
                    summary.monthly_sleep_score
                ),
                "monthly_score_max": 100 + SLEEP_MONTHLY_BONUS_MAX_POINTS,
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

        divisor = (
            activity.sessions
            if is_cycling
            else reporting_days
        )

        average_basis = (
            "workout"
            if is_cycling
            else "daily"
        )

        return {
            "type": activity.activity_type.name.lower(),
            "sessions": activity.sessions,
            "duration_minutes": self._round_number(
                activity.duration_minutes
            ),
            "active_energy_kcal": self._round_number(
                activity.active_energy_kcal
            ),
            "distance_km": self._round_number(
                activity.distance_km
            ),
            "average_basis": average_basis,
            "average_duration_minutes": self._round_number(
                activity.duration_minutes / divisor
                if divisor
                else None
            ),
            "average_active_energy_kcal": self._round_number(
                activity.active_energy_kcal / divisor
                if divisor
                else None
            ),
            "average_distance_km": self._round_number(
                activity.distance_km / divisor
                if (
                    divisor
                    and activity.distance_km is not None
                )
                else None
            ),
        }

    def _build_body_weight(
        self,
        metrics: ActivityMetricsSummary | None,
    ) -> dict[str, Any] | None:
        if (
            metrics is None
            or metrics.measurements == 0
        ):
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

        if (
            metrics.average_basal_energy_kcal is None
            and metrics.average_active_energy_kcal is None
        ):
            return None

        return {
            "average_basal_kcal": self._round_number(
                metrics.average_basal_energy_kcal
            ),
            "average_active_kcal": self._round_number(
                metrics.average_active_energy_kcal
            ),
            "average_tdee_kcal": self._round_number(
                metrics.average_tdee_kcal
            ),
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
            "average_protein_g": self._round_number(
                metrics.average_protein_g
            ),
            "average_carbohydrates_g": self._round_number(
                metrics.average_carbohydrates_g
            ),
            "average_fat_g": self._round_number(
                metrics.average_fat_g
            ),
            "average_calories_kcal": self._round_number(
                metrics.average_calories_kcal
            ),
            "average_calories_balance_kcal": self._round_number(
                metrics.average_calories_balance
            ),
        }

    @staticmethod
    def _build_day(
        summary,
    ) -> dict[str, Any]:
        # Intentionally left minimal for now.
        # We will design the daily JSON contract separately after
        # the monthly summary contract is implemented and tested.
        return {
            "date": summary.date.isoformat(),
        }
        
    @staticmethod
    def _round_number(
        number: float | None,
    ) -> float | None:
        if number is None:
            return None

        return round(number, 2)
