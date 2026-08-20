from __future__ import annotations

import calendar
from contextlib import redirect_stdout
from io import StringIO

from apple_health.enums import WorkoutType
from apple_health.report_models import (
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
    SleepScore,
)
from apple_health.sleep_score_config import SLEEP_MONTHLY_BONUS_ENABLED


class TextRenderer:
    def render_month(
        self,
        monthly_summary: MonthlySummary,
    ) -> str:
        output = StringIO()

        with redirect_stdout(output):
            self._render_month(monthly_summary)

        return output.getvalue()

    def _render_month(
        self,
        monthly_summary: MonthlySummary,
    ) -> None:
        self._render_month_summary(monthly_summary)

        print()

        for daily_summary in monthly_summary.days:
            self._render_day(daily_summary)

    def render_month_summary(
        self,
        summary: MonthlySummary,
    ) -> str:
        output = StringIO()

        with redirect_stdout(output):
            self._render_month_summary(summary)

        return output.getvalue()

    def _render_month_summary(
        self,
        summary: MonthlySummary,
    ) -> None:
        self._render_month_header(summary)
        self._render_monthly_general_activity(summary)
        self._render_monthly_sleep_section(summary)
        self._render_monthly_workouts(summary)
        self._render_monthly_weight(summary)
        self._render_monthly_expenditures(summary)
        self._render_monthly_nutrition(summary)

    def _render_month_header(
        self,
        summary: MonthlySummary,
    ) -> None:
        print("Apple Health Monthly Report")
        print(f"{calendar.month_name[summary.month]} {summary.year}")

        if summary.data_through is None:
            date_through = "No complete reporting days available."
        else:
            date_through = f"Data available through: {summary.data_through}"

        print(date_through)
        print("=" * len(date_through))
        print()

    def _render_monthly_general_activity(
        self,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics

        if metrics is None or (metrics.total_steps is None and metrics.total_distance_km is None):
            return

        self._render_general_activity(
            total_steps=metrics.total_steps,
            total_distance_km=metrics.total_distance_km,
            average_step_length_cm=metrics.average_step_length_cm,
            average_daily_steps=metrics.average_daily_steps,
            average_daily_distance_km=metrics.average_daily_distance_km,
        )

        print()

    def _render_monthly_sleep_section(
        self,
        summary: MonthlySummary,
    ) -> None:
        if summary.sleep_summary is None:
            return

        self._render_monthly_sleep(summary.sleep_summary)

        print()

        self._render_monthly_sleep_score(summary.sleep_summary)

        print()

    def _render_monthly_workouts(
        self,
        summary: MonthlySummary,
    ) -> None:
        if not summary.activities:
            return

        print("Workouts")
        print("--------")

        for activity in summary.activities:
            self._render_activity(
                activity,
                reporting_days=summary.reporting_days,
            )

    def _render_monthly_weight(
        self,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics

        if metrics.measurements == 0:
            return

        weight_header = "Body weight:"
        print(weight_header)
        print("-" * len(weight_header))
        print(f"  Average weight:   {metrics.average_weight:.2f} kg")
        print(f"  Start weight:     {metrics.start_weight:.2f} kg")
        print(f"  End weight:       {metrics.end_weight:.2f} kg")
        print(f"  Change:           {metrics.weight_change:+.2f} kg")
        print(f"  Max weight:       {metrics.max_weight:.2f} kg")
        print(f"  Min weight:       {metrics.min_weight:.2f} kg")
        print(f"  Measurements:     {metrics.measurements:.0f}" f"/{summary.reporting_days} days")
        print()

    def _render_monthly_expenditures(
        self,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics

        if (
            metrics is None
            or metrics.average_basal_energy_kcal is None
            or metrics.average_active_energy_kcal is None
        ):
            return

        print("Average energy expenditure")
        print("--------------------------")
        print(f"  Basal energy:   {metrics.average_basal_energy_kcal:.0f} kcal")
        print(f"  Active energy:  {metrics.average_active_energy_kcal:.0f} kcal")
        print(f"  TDEE:           {metrics.average_tdee_kcal:.0f} kcal")

        print()

    def _render_monthly_nutrition(
        self,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics

        if metrics is None or metrics.average_calories_kcal is None:
            return

        print("Average nutrition")
        print("-----------------")
        print(f"  Protein:  {metrics.average_protein_g:.0f} g")
        print(f"  Carbs:    {metrics.average_carbohydrates_g:.0f} g")
        print(f"  Fat:      {metrics.average_fat_g:.0f} g")
        print(f"  Calories: {metrics.average_calories_kcal:.0f} kcal")

        if metrics.average_calories_balance is not None:
            print()
            print(f"Average calories balance: " f"{metrics.average_calories_balance:.0f} kcal")

    def _render_day(
        self,
        summary: DailySummary,
    ) -> None:
        self._render_day_header(summary)
        self._render_daily_sleep_section(summary)
        self._render_daily_general_activity(summary)
        self._render_daily_workouts(summary)
        self._render_daily_weight(summary)
        self._render_day_expenditures(summary)
        self._render_daily_nutrition_section(summary)
        self._render_day_footer()

    def _render_day_header(
        self,
        summary: DailySummary,
    ) -> None:
        print(summary.date)
        print("=" * len(str(summary.date)))

    def _render_daily_sleep_section(
        self,
        summary: DailySummary,
    ) -> None:
        self._render_daily_sleep(summary)

        if summary.sleep_score is not None:
            self._render_sleep_score(summary.sleep_score)
            print()

    def _render_daily_general_activity(
        self,
        summary: DailySummary,
    ) -> None:
        self._render_general_activity(
            total_steps=summary.total_steps,
            total_distance_km=summary.total_distance_km,
            average_step_length_cm=summary.average_step_length_cm,
        )

        print()

    def _render_daily_workouts(
        self,
        summary: DailySummary,
    ) -> None:
        if not summary.activities:
            if summary.total_steps > 0:
                print("No workouts.")
            else:
                print("No activities.")

            print()
            return

        print("Workouts")
        print("--------")

        for activity in summary.activities:
            self._render_activity(activity)

        print("Workouts summary")
        print("----------------")
        print(f"  Duration: " f"{self._format_minutes(summary.total_duration_minutes)}")
        print(f"  Energy:   " f"{summary.total_active_energy_kcal:.0f} kcal")
        print()

    def _render_daily_weight(
        self,
        summary: DailySummary,
    ) -> None:
        if summary.weight is not None:
            header = f"Weight: {summary.weight}"
        else:
            header = "No weight measurement for that day"

        print(header)
        print("-" * len(header))
        print()

    def _render_day_expenditures(self, summary: DailySummary) -> None:
        print("Daily energy expenditure")
        print("------------------------")
        print(f"  Basal energy:   {summary.basal_energy_kcal:.0f} kcal")
        print(f"  Active energy:  {summary.active_energy_kcal:.0f} kcal")
        print(f"  TDEE:           {summary.tdee_kcal:.0f} kcal")

    def _render_daily_nutrition_section(
        self,
        summary: DailySummary,
    ) -> None:
        print()

        if summary.nutrition is None:
            print("No nutrition data for that day")
            print("------------------------------")
            return

        self._render_day_nutrition(summary)

        if summary.calories_balance_kcal is not None:
            print()
            print(f"Calories balance: " f"{summary.calories_balance_kcal:.0f} kcal")

    @staticmethod
    def _render_day_footer() -> None:
        print("-" * 60)
        print()

    def _render_activity(
        self, activity: ActivitySummary, reporting_days: int | None = None
    ) -> None:
        print(activity.activity_type.value.title())
        print(f"  Sessions: {activity.sessions}")
        print(f"  Duration: {self._format_minutes(activity.duration_minutes)}")
        print(f"  Energy:   {activity.active_energy_kcal:.0f} kcal")

        if activity.distance_km is not None:
            print(f"  Distance: {activity.distance_km:.2f} km")

        if reporting_days is not None:
            divisor = (
                activity.sessions
                if activity.activity_type
                in (
                    WorkoutType.OUTDOOR_CYCLING,
                    WorkoutType.INDOOR_CYCLING,
                )
                else reporting_days
            )

            averaging_label = (
                "Workout"
                if activity.activity_type
                in (
                    WorkoutType.OUTDOOR_CYCLING,
                    WorkoutType.INDOOR_CYCLING,
                )
                else "Daily"
            )

            avg_duration = activity.duration_minutes / divisor
            avg_energy = activity.active_energy_kcal / divisor

            print()
            print(f"  Average {averaging_label} Duration: {self._format_minutes(avg_duration)}")
            print(f"  Average {averaging_label} Energy:   {avg_energy:.0f} kcal")

            if activity.distance_km is not None:
                print(
                    f"  Average {averaging_label} Distance: {activity.distance_km / divisor:.2f} km"
                )

        print()

    def _render_general_activity(
        self,
        total_steps: int,
        total_distance_km: float,
        average_step_length_cm: float,
        average_daily_steps: float | None = None,
        average_daily_distance_km: float | None = None,
    ) -> None:
        print("General activity")
        print("----------------")

        print("Steps")
        print("-----")
        print(f"  Total:         {total_steps:,}")

        if average_daily_steps is not None:
            print(f"  Average daily: {average_daily_steps:.0f}")

        print()

        print("Walking/Running distance")
        print("------------------------")
        print(f"  Total:               {total_distance_km:.2f} km")

        if average_daily_distance_km is not None:
            print(f"  Average daily:       {average_daily_distance_km:.2f} km")

        print(f"  Average step length: {average_step_length_cm:.2f} cm")

    def _render_daily_sleep(self, summary: DailySummary) -> None:
        if summary.sleep_session is None:
            return

        sleep = summary.sleep_session

        print("Sleep")
        print("-----")
        print(f"  Bedtime:          {sleep.bedtime:%H:%M}")
        print(f"  Wake up:          {sleep.wake_up:%H:%M}")
        print(
            f"  Time asleep:      {self._format_minutes(sleep.time_asleep_minutes)} "
            f"({sleep.awake_minutes:.0f} min awake)"
        )
        print(f"  Sleep efficiency: {sleep.sleep_efficiency_percent:.0f}%")
        print()

    def _render_monthly_sleep(self, summary: SleepMonthlySummary) -> None:
        print("Sleep")
        print("-----")
        print(f"  Sessions:           {summary.total_sessions}")
        print()
        print(f"  Average bedtime:    {summary.average_bedtime:%H:%M}")
        print(f"  Average wake up:    {summary.average_wake_up:%H:%M}")
        print()
        print(f"  Average sleep:      {self._format_minutes(summary.average_sleep_minutes)}")
        print(f"  Average awake:      {summary.average_awake_minutes:.0f} min")
        print(f"  Average efficiency: {summary.average_sleep_efficiency:.0f}%")
        print()
        print("Sleep Stages")
        print("------------")
        print(f"  Core:               {self._format_minutes(summary.average_core_minutes)}")
        print(f"  Deep:               {self._format_minutes(summary.average_deep_minutes)}")
        print(f"  REM:                {self._format_minutes(summary.average_rem_minutes)}")

    def _render_sleep_score(
        self,
        sleep_score: SleepScore,
    ) -> None:
        header = "Sleep score"
        print(header)
        print("-" * len(header))

        print(f"  Bedtime:  {sleep_score.bedtime_score:.0f}/100")
        print(f"  Duration: {sleep_score.duration_score:.0f}/100")
        print(f"  Wake-up:  {sleep_score.wake_up_score:.0f}/100")
        print(f"  Total:    {sleep_score.total_score:.0f}/100")

    def _render_monthly_sleep_score(
        self,
        summary: SleepMonthlySummary,
    ) -> None:
        header = "Sleep score"
        print(header)
        print("-" * len(header))

        print(f"  Average bedtime:  {summary.average_bedtime_score:.0f}/100")
        print(f"  Average duration: {summary.average_duration_score:.0f}/100")
        print(f"  Average wake up:  {summary.average_wake_up_score:.0f}/100")
        print(f"  Average total:    {summary.average_sleep_score:.0f}/100")

        print()

        if not SLEEP_MONTHLY_BONUS_ENABLED:
            print("  Monthly bonus system: disabled")
            return

        print(f"  Average bonus:     +{summary.average_bonus:.0f}")
        print(f"  Consistency bonus: +{summary.consistency_bonus:.0f}")
        print(f"  Monthly score:     " f"{summary.monthly_sleep_score:.0f}/120")

    def _render_day_nutrition(self, summary: DailySummary) -> None:
        print("Daily nutrition")
        print("---------------")
        print(f"  Protein:   {summary.nutrition.protein_g:.0f} g")
        print(f"  Carbs:     {summary.nutrition.carbohydrates_g:.0f} g")
        print(f"  Fat:       {summary.nutrition.fat_g:.0f} g")
        print(f"  Calories:  {summary.nutrition.calories_kcal:.0f} kcal")

    @staticmethod
    def _format_minutes(minutes: float) -> str:
        total_minutes = round(minutes)

        hours, mins = divmod(total_minutes, 60)

        return f"{hours} h {mins} min"
