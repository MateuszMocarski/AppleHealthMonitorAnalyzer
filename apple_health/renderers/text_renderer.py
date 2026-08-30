from __future__ import annotations

import calendar
from io import StringIO

from apple_health.config.app_config import AppConfig
from apple_health.enums import WorkoutType
from apple_health.report_models import (
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
    SleepScore,
)


class _TextWriter:
    def __init__(self) -> None:
        self._output = StringIO()

    def write(self, *values: object) -> None:
        print(*values, file=self._output)

    def getvalue(self) -> str:
        return self._output.getvalue()


class TextRenderer:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig()

    def render_month(self, monthly_summary: MonthlySummary) -> str:
        writer = _TextWriter()
        self._render_month(writer, monthly_summary)
        return writer.getvalue()

    def _render_month(self, writer: _TextWriter, monthly_summary: MonthlySummary) -> None:
        self._render_month_summary(writer, monthly_summary)
        writer.write()
        for daily_summary in monthly_summary.days:
            self._render_day(writer, daily_summary)

    def render_month_summary(self, summary: MonthlySummary) -> str:
        writer = _TextWriter()
        self._render_month_summary(writer, summary)
        return writer.getvalue()

    def _render_month_summary(self, writer: _TextWriter, summary: MonthlySummary) -> None:
        self._render_month_header(writer, summary)
        self._render_monthly_general_activity(writer, summary)
        self._render_monthly_sleep_section(writer, summary)
        self._render_monthly_workouts(writer, summary)
        self._render_monthly_weight(writer, summary)
        self._render_monthly_expenditures(writer, summary)
        self._render_monthly_nutrition(writer, summary)

    def _render_month_header(self, writer: _TextWriter, summary: MonthlySummary) -> None:
        writer.write("Apple Health Monthly Report")
        writer.write(f"{calendar.month_name[summary.month]} {summary.year}")
        if summary.data_through is None:
            date_through = "No complete reporting days available."
        else:
            date_through = f"Data available through: {summary.data_through}"
        writer.write(date_through)
        writer.write("=" * len(date_through))
        writer.write()

    def _render_monthly_general_activity(
        self,
        writer: _TextWriter,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics
        if metrics is None or (metrics.total_steps is None and metrics.total_distance_km is None):
            return
        self._render_general_activity(
            writer,
            total_steps=metrics.total_steps,
            total_distance_km=metrics.total_distance_km,
            average_step_length_cm=metrics.average_step_length_cm,
            average_daily_steps=metrics.average_daily_steps,
            average_daily_distance_km=metrics.average_daily_distance_km,
        )
        writer.write()

    def _render_monthly_sleep_section(self, writer: _TextWriter, summary: MonthlySummary) -> None:
        if summary.sleep_summary is None:
            return
        self._render_monthly_sleep(writer, summary.sleep_summary)
        writer.write()
        self._render_monthly_sleep_score(writer, summary.sleep_summary)
        writer.write()
        self._render_sleep_configuration(writer)
        writer.write()

    def _render_monthly_workouts(self, writer: _TextWriter, summary: MonthlySummary) -> None:
        if not summary.activities:
            return
        writer.write("Workouts")
        writer.write("--------")
        for activity in summary.activities:
            self._render_activity(writer, activity, reporting_days=summary.reporting_days)

    def _render_monthly_weight(self, writer: _TextWriter, summary: MonthlySummary) -> None:
        metrics = summary.activity_metrics
        if metrics is None or metrics.measurements == 0:
            return
        weight_header = "Body weight:"
        writer.write(weight_header)
        writer.write("-" * len(weight_header))
        writer.write(f"  Average weight:   {metrics.average_weight:.2f} kg")
        writer.write(f"  Start weight:     {metrics.start_weight:.2f} kg")
        writer.write(f"  End weight:       {metrics.end_weight:.2f} kg")
        writer.write(f"  Change:           {metrics.weight_change:+.2f} kg")
        writer.write(f"  Max weight:       {metrics.max_weight:.2f} kg")
        writer.write(f"  Min weight:       {metrics.min_weight:.2f} kg")
        writer.write(
            f"  Measurements:     " f"{metrics.measurements:.0f}/{summary.reporting_days} days"
        )
        writer.write()

    def _render_monthly_expenditures(
        self,
        writer: _TextWriter,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics
        if metrics is None or all(
            average is None
            for average in (
                metrics.average_basal_energy_kcal,
                metrics.average_active_energy_kcal,
                metrics.average_tdee_kcal,
            )
        ):
            return

        writer.write("Average energy expenditure")
        writer.write("--------------------------")

        if metrics.average_basal_energy_kcal is not None:
            value, count_days = metrics.average_basal_energy_kcal
            writer.write(
                f"  Basal energy:   {value:.0f} kcal based on {count_days} days"
            )

        if metrics.average_active_energy_kcal is not None:
            value, count_days = metrics.average_active_energy_kcal
            writer.write(
                f"  Active energy:  {value:.0f} kcal based on {count_days} days"
            )

        if metrics.average_tdee_kcal is not None:
            value, count_days = metrics.average_tdee_kcal
            writer.write(
                f"  TDEE:           {value:.0f} kcal based on {count_days} days"
            )

        writer.write()

    def _render_monthly_nutrition(
        self,
        writer: _TextWriter,
        summary: MonthlySummary,
    ) -> None:
        metrics = summary.activity_metrics
        if metrics is None or all(
            average is None
            for average in (
                metrics.average_protein_g,
                metrics.average_carbohydrates_g,
                metrics.average_fat_g,
                metrics.average_calories_kcal,
                metrics.average_calories_balance_kcal,
            )
        ):
            return

        writer.write("Average nutrition")
        writer.write("-----------------")

        if metrics.average_protein_g is not None:
            value, count_days = metrics.average_protein_g
            writer.write(
                f"  Protein:  {value:.0f} g based on {count_days} days"
            )

        if metrics.average_carbohydrates_g is not None:
            value, count_days = metrics.average_carbohydrates_g
            writer.write(
                f"  Carbs:    {value:.0f} g based on {count_days} days"
            )

        if metrics.average_fat_g is not None:
            value, count_days = metrics.average_fat_g
            writer.write(
                f"  Fat:      {value:.0f} g based on {count_days} days"
            )

        if metrics.average_calories_kcal is not None:
            value, count_days = metrics.average_calories_kcal
            writer.write(
                f"  Calories: {value:.0f} kcal based on {count_days} days"
            )

        if metrics.average_calories_balance_kcal is not None:
            value, count_days = metrics.average_calories_balance_kcal
            writer.write()
            writer.write(
                f"Average calories balance: "
                f"{value:.0f} kcal based on {count_days} days"
            )

    def _render_day(self, writer: _TextWriter, summary: DailySummary) -> None:
        self._render_day_header(writer, summary)
        self._render_daily_sleep_section(writer, summary)
        self._render_daily_general_activity(writer, summary)
        self._render_daily_workouts(writer, summary)
        self._render_daily_weight(writer, summary)
        self._render_day_expenditures(writer, summary)
        self._render_daily_nutrition_section(writer, summary)
        self._render_day_footer(writer)

    def _render_day_header(self, writer: _TextWriter, summary: DailySummary) -> None:
        writer.write(summary.date)
        writer.write("=" * len(str(summary.date)))

    def _render_daily_sleep_section(self, writer: _TextWriter, summary: DailySummary) -> None:
        self._render_daily_sleep(writer, summary)
        if summary.sleep_score is not None:
            self._render_sleep_score(writer, summary.sleep_score)
            writer.write()

    def _render_daily_general_activity(self, writer: _TextWriter, summary: DailySummary) -> None:
        self._render_general_activity(
            writer,
            total_steps=summary.total_steps,
            total_distance_km=summary.total_distance_km,
            average_step_length_cm=summary.average_step_length_cm,
        )
        writer.write()

    def _render_daily_workouts(self, writer: _TextWriter, summary: DailySummary) -> None:
        if not summary.activities:
            if summary.total_steps > 0:
                writer.write("No workouts.")
            else:
                writer.write("No activities.")
            writer.write()
            return
        writer.write("Workouts")
        writer.write("--------")
        for activity in summary.activities:
            self._render_activity(writer, activity)
        writer.write("Workouts summary")
        writer.write("----------------")
        writer.write(f"  Duration: {self._format_minutes(summary.total_duration_minutes)}")
        writer.write(f"  Energy:   {summary.total_active_energy_kcal:.0f} kcal")
        writer.write()

    def _render_daily_weight(self, writer: _TextWriter, summary: DailySummary) -> None:
        if summary.weight is not None:
            header = f"Weight: {summary.weight}"
        else:
            header = "No weight measurement for that day"
        writer.write(header)
        writer.write("-" * len(header))
        writer.write()

    def _render_day_expenditures(
        self,
        writer: _TextWriter,
        summary: DailySummary,
    ) -> None:
        writer.write("Daily energy expenditure")
        writer.write("------------------------")

        if summary.basal_energy_kcal is not None:
            writer.write(
                f"  Basal energy:   {summary.basal_energy_kcal:.0f} kcal"
            )

        if summary.active_energy_kcal is not None:
            writer.write(
                f"  Active energy:  {summary.active_energy_kcal:.0f} kcal"
            )

        if summary.tdee_kcal is not None:
            writer.write(
                f"  TDEE:           {summary.tdee_kcal:.0f} kcal"
            )

    def _render_daily_nutrition_section(
        self,
        writer: _TextWriter,
        summary: DailySummary,
    ) -> None:
        writer.write()

        nutrition = summary.nutrition

        if nutrition is None or all(
            value is None
            for value in (
                nutrition.protein_g,
                nutrition.carbohydrates_g,
                nutrition.fat_g,
                nutrition.calories_kcal,
            )
        ):
            writer.write("No nutrition data for that day")
            writer.write("------------------------------")
            return

        self._render_day_nutrition(writer, summary)

        if summary.calories_balance_kcal is not None:
            writer.write()
            writer.write(
                f"Calories balance: {summary.calories_balance_kcal:.0f} kcal"
            )

    @staticmethod
    def _render_day_footer(writer: _TextWriter) -> None:
        writer.write("-" * 60)
        writer.write()

    def _render_activity(
        self,
        writer: _TextWriter,
        activity: ActivitySummary,
        reporting_days: int | None = None,
    ) -> None:
        writer.write(activity.activity_type.value.title())
        writer.write(f"  Sessions: {activity.sessions}")
        writer.write(f"  Duration: {self._format_minutes(activity.duration_minutes)}")
        writer.write(f"  Energy:   {activity.active_energy_kcal:.0f} kcal")
        if activity.distance_km is not None:
            writer.write(f"  Distance: {activity.distance_km:.2f} km")
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
            writer.write()
            writer.write(
                f"  Average {averaging_label} Duration: " f"{self._format_minutes(avg_duration)}"
            )
            writer.write(f"  Average {averaging_label} Energy:   {avg_energy:.0f} kcal")
            if activity.distance_km is not None:
                writer.write(
                    f"  Average {averaging_label} Distance: "
                    f"{activity.distance_km / divisor:.2f} km"
                )
        writer.write()

    def _render_general_activity(
        self,
        writer: _TextWriter,
        total_steps: int,
        total_distance_km: float,
        average_step_length_cm: float,
        average_daily_steps: float | None = None,
        average_daily_distance_km: float | None = None,
    ) -> None:
        writer.write("General activity")
        writer.write("----------------")
        writer.write("Steps")
        writer.write("-----")
        writer.write(f"  Total:         {total_steps:,}")
        if average_daily_steps is not None:
            writer.write(f"  Average daily: {average_daily_steps:.0f}")
        writer.write()
        writer.write("Walking/Running distance")
        writer.write("------------------------")
        writer.write(f"  Total:               {total_distance_km:.2f} km")
        if average_daily_distance_km is not None:
            writer.write(f"  Average daily:       {average_daily_distance_km:.2f} km")
        writer.write(f"  Average step length: {average_step_length_cm:.2f} cm")

    def _render_daily_sleep(self, writer: _TextWriter, summary: DailySummary) -> None:
        if summary.sleep_session is None:
            return
        sleep = summary.sleep_session
        writer.write("Sleep")
        writer.write("-----")
        writer.write(f"  Bedtime:          {sleep.bedtime:%H:%M}")
        writer.write(f"  Wake up:          {sleep.wake_up:%H:%M}")
        writer.write(
            f"  Time asleep:      "
            f"{self._format_minutes(sleep.time_asleep_minutes)} "
            f"({sleep.awake_minutes:.0f} min awake)"
        )
        writer.write(f"  Sleep efficiency: {sleep.sleep_efficiency_percent:.0f}%")
        writer.write()

    def _render_monthly_sleep(self, writer: _TextWriter, summary: SleepMonthlySummary) -> None:
        writer.write("Sleep")
        writer.write("-----")
        writer.write(f"  Sessions:           {summary.total_sessions}")
        writer.write()
        writer.write(f"  Average bedtime:    {summary.average_bedtime:%H:%M}")
        writer.write(f"  Average wake up:    {summary.average_wake_up:%H:%M}")
        writer.write()
        writer.write(f"  Average sleep:      {self._format_minutes(summary.average_sleep_minutes)}")
        writer.write(f"  Average awake:      {summary.average_awake_minutes:.0f} min")
        writer.write(f"  Average efficiency: {summary.average_sleep_efficiency:.0f}%")
        writer.write()
        writer.write("Sleep Stages")
        writer.write("------------")
        writer.write(f"  Core:               {self._format_minutes(summary.average_core_minutes)}")
        writer.write(f"  Deep:               {self._format_minutes(summary.average_deep_minutes)}")
        writer.write(f"  REM:                {self._format_minutes(summary.average_rem_minutes)}")

    def _render_sleep_score(self, writer: _TextWriter, sleep_score: SleepScore) -> None:
        header = "Sleep score"
        writer.write(header)
        writer.write("-" * len(header))
        writer.write(f"  Bedtime:  {sleep_score.bedtime_score:.0f}/100")
        writer.write(f"  Duration: {sleep_score.duration_score:.0f}/100")
        writer.write(f"  Wake-up:  {sleep_score.wake_up_score:.0f}/100")
        writer.write(f"  Total:    {sleep_score.total_score:.0f}/100")

    def _render_monthly_sleep_score(
        self,
        writer: _TextWriter,
        summary: SleepMonthlySummary,
    ) -> None:
        header = "Sleep score"
        writer.write(header)
        writer.write("-" * len(header))
        writer.write(f"  Average bedtime:  {summary.average_bedtime_score:.0f}/100")
        writer.write(f"  Average duration: {summary.average_duration_score:.0f}/100")
        writer.write(f"  Average wake up:  {summary.average_wake_up_score:.0f}/100")
        writer.write(f"  Average total:    {summary.average_sleep_score:.0f}/100")
        writer.write()
        if not self.config.sleep.score.monthly_bonus.enabled:
            writer.write("  Monthly bonus system: disabled")
            return
        writer.write(f"  Average bonus:     +{summary.average_bonus:.0f}")
        writer.write(f"  Consistency bonus: +{summary.consistency_bonus:.0f}")
        monthly_score_max = 100 + self.config.sleep.score.monthly_bonus.max_points
        writer.write(
            f"  Monthly score:     " f"{summary.monthly_sleep_score:.0f}/{monthly_score_max}"
        )

    def _render_day_nutrition(
        self,
        writer: _TextWriter,
        summary: DailySummary,
    ) -> None:
        nutrition = summary.nutrition
        if nutrition is None:
            return

        writer.write("Daily nutrition")
        writer.write("---------------")

        if nutrition.protein_g is not None:
            writer.write(f"  Protein:   {nutrition.protein_g:.0f} g")

        if nutrition.carbohydrates_g is not None:
            writer.write(
                f"  Carbs:     {nutrition.carbohydrates_g:.0f} g"
            )

        if nutrition.fat_g is not None:
            writer.write(f"  Fat:       {nutrition.fat_g:.0f} g")

        if nutrition.calories_kcal is not None:
            writer.write(
                f"  Calories:  {nutrition.calories_kcal:.0f} kcal"
            )

    @staticmethod
    def _format_minutes(minutes: float) -> str:
        total_minutes = round(minutes)
        hours, mins = divmod(total_minutes, 60)
        return f"{hours} h {mins} min"

    def _render_sleep_configuration(self, writer: _TextWriter) -> None:
        sleep = self.config.sleep
        score = sleep.score
        header = "Sleep configuration"
        writer.write(header)
        writer.write("-" * len(header))
        writer.write(f"  Session gap threshold: {sleep.session_gap_threshold_minutes} min")
        writer.write()
        writer.write("  Scoring mode:")
        writer.write(f"    Linear penalties: {('yes' if score.linear_penalties else 'no')}")
        writer.write()
        writer.write("  Bedtime:")
        writer.write(f"    Target:           {score.bedtime.target.strftime('%H:%M')}")
        writer.write(f"    Penalty interval: {score.bedtime.penalty_interval_minutes} min")
        writer.write(f"    Penalty points:   {score.bedtime.penalty_points:g}")
        writer.write()
        writer.write("  Sleep duration:")
        writer.write(f"    Target:           {score.duration.target_minutes} min")
        writer.write(f"    Tolerance:        {score.duration.tolerance_minutes} min")
        writer.write(f"    Penalty interval: {score.duration.penalty_interval_minutes} min")
        writer.write(f"    Penalty points:   {score.duration.penalty_points:g}")
        writer.write(f"    Oversleep weight: {score.duration.oversleep_weight:g}")
        writer.write(f"    Undersleep weight: {score.duration.undersleep_weight:g}")
        writer.write()
        writer.write("  Wake-up:")
        writer.write(f"    Target:           {score.wake_up.target.strftime('%H:%M')}")
        writer.write(f"    Bedtime weight:   {score.wake_up.bedtime_weight:g}")
        writer.write(f"    Duration weight:  {score.wake_up.duration_weight:g}")
        writer.write(f"    Penalty interval: {score.wake_up.penalty_interval_minutes} min")
        writer.write(f"    Penalty points:   {score.wake_up.penalty_points:g}")
        writer.write()
        writer.write("  Daily score weights:")
        writer.write(f"    Bedtime:  {score.weights.bedtime:g}")
        writer.write(f"    Duration: {score.weights.duration:g}")
        writer.write(f"    Wake-up:  {score.weights.wake_up:g}")
        writer.write()
        writer.write("  Monthly bonus:")
        writer.write(f"    Enabled: {('yes' if score.monthly_bonus.enabled else 'no')}")
        writer.write(f"    Maximum points: {score.monthly_bonus.max_points}")
        writer.write("    Average thresholds:")
        for threshold, bonus in score.monthly_bonus.average_thresholds:
            writer.write(f"      {threshold:g}/100 -> +{bonus:g}")
        writer.write("    Consistency thresholds:")
        for threshold, bonus in score.monthly_bonus.consistency_thresholds:
            writer.write(f"      < {threshold:g} std dev -> +{bonus:g}")
        writer.write()
