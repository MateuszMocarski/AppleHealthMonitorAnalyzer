from __future__ import annotations

import calendar

from apple_health.enums import WorkoutType
from apple_health.report_models import (
    ActivitySummary,
    DailySummary,
    MonthlySummary,
    SleepMonthlySummary,
)


class ConsoleRenderer:
    def render_month(self, monthly_summary: MonthlySummary) -> None:
        self._render_month_summary(monthly_summary)

        print()

        for daily_summary in monthly_summary.days:
            self._render_day(daily_summary)

    def _render_day(self, summary: DailySummary) -> None:
        print(summary.date)
        print("=" * len(str(summary.date)))

        self._render_daily_sleep(summary)

        self._render_general_activity(
            total_steps=summary.total_steps,
            total_distance_km=summary.total_distance_km,
            average_step_length_cm=summary.average_step_length_cm,
        )

        print()

        if not summary.activities:
            if summary.total_steps > 0:
                print("No workouts.")
            else:
                print("No activities.")

            print("-" * 60)
            print()

            return

        for activity in summary.activities:
            self._render_activity(activity)

        print("Total")
        print(f"  Duration: {self._format_minutes(summary.total_duration_minutes)}")
        print(f"  Energy:   {summary.total_active_energy_kcal:.0f} kcal")
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

    def _render_month_summary(
        self,
        summary: MonthlySummary,
    ) -> None:

        print("Apple Health Monthly Report")
        print(f"{calendar.month_name[summary.month]} {summary.year}")
        date_through = f"Data available through: {summary.data_through}"
        print(date_through)
        print("=" * len(date_through))

        metrics = summary.activity_metrics

        self._render_general_activity(
            total_steps=metrics.total_steps,
            total_distance_km=metrics.total_distance_km,
            average_step_length_cm=metrics.average_step_length_cm,
            average_daily_steps=metrics.average_daily_steps,
            average_daily_distance_km=metrics.average_daily_distance_km,
        )

        print()

        self._render_monthly_sleep(summary.sleep_summary)

        print()

        print("Activities")
        print("----------")
        print()

        for activity in summary.activities:
            self._render_activity(
                activity,
                reporting_days=summary.reporting_days,
            )

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

    @staticmethod
    def _format_minutes(minutes: float) -> str:
        total_minutes = round(minutes)

        hours, mins = divmod(total_minutes, 60)

        return f"{hours} h {mins} min"
