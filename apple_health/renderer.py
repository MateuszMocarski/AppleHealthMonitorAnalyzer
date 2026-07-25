from __future__ import annotations

from apple_health.report_models import ActivitySummary
from apple_health.report_models import DailySummary
from apple_health.report_models import MonthlySummary
from apple_health.enums import WorkoutType

import calendar

class ConsoleRenderer:
    def render_month(self, monthly_summary: MonthlySummary) -> None:
        self.render_month_summary(monthly_summary)

        print()

        for daily_summary in monthly_summary.days:
            self._render_day(daily_summary)

    def _render_day(self, summary: DailySummary) -> None:
        print(summary.date)
        print("=" * len(str(summary.date)))
        
        self._render_general_activity(
            total_steps=summary.total_steps,
            total_distance_km=summary.total_distance_km,
            average_step_length_cm=summary.average_step_length_cm,
        )

        print()
        
        self._render_sleep(summary)
        
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

    def _render_activity(self, activity: ActivitySummary) -> None:
        print(activity.activity_type.value.title())
        print(f"  Sessions: {activity.sessions}")
        print(f"  Duration: {self._format_minutes(activity.duration_minutes)}")
        print(f"  Energy:   {activity.active_energy_kcal:.0f} kcal")

        if activity.distance_km is not None:
            print(f"  Distance: {activity.distance_km:.2f} km")

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
        
    def render_month_summary(
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
        
        print("Activities")
        print("----------")
        print()
        
        for activity in summary.activities:
            print(activity.activity_type.value.title())
            print(f"  Sessions: {activity.sessions}")
            print(f"  Duration: {self._format_minutes(activity.duration_minutes)}")
            print(f"  Energy:   {activity.active_energy_kcal:.0f} kcal")

            if activity.distance_km is not None:
                print(f"  Distance: {activity.distance_km:.2f} km")
                
            divisor = (
                activity.sessions
                if activity.activity_type in (WorkoutType.OUTDOOR_CYCLING, WorkoutType.INDOOR_CYCLING)
                else summary.reporting_days
            )
            
            averaging_label = (
                "Workout"
                if activity.activity_type in (WorkoutType.OUTDOOR_CYCLING, WorkoutType.INDOOR_CYCLING)
                else "Daily"
            )
            
            avg_duration = activity.duration_minutes / divisor
            avg_energy = activity.active_energy_kcal / divisor

            if activity.distance_km is not None:
                avg_distance = activity.distance_km / divisor
            
            print()
            print(f"  Average {averaging_label} Duration: {self._format_minutes(avg_duration)}")
            print(f"  Average {averaging_label} Energy:   {avg_energy:.0f} kcal")
            if activity.distance_km is not None:
                print(f"  Average {averaging_label} Distance: {avg_distance:.2f} km")
            print()
            
    def _render_sleep(self, summary: DailySummary) -> None:
        if summary.sleep_session is None:
            return

        sleep = summary.sleep_session

        print("Sleep")
        print("-----")
        print(f"  Bedtime:          {sleep.bedtime:%H:%M}")
        print(f"  Wake up:          {sleep.wake_up:%H:%M}")
        print(f"  Time asleep:      {self._format_minutes(sleep.time_asleep_minutes)} ({sleep.awake_minutes:.0f} min awake)")
        print(f"  Sleep efficiency: {sleep.sleep_efficiency_percent:.0f}%")
        print()
        
    @staticmethod
    def _format_minutes(minutes: float) -> str:
        total_minutes = round(minutes)

        hours, mins = divmod(total_minutes, 60)

        return f"{hours} h {mins} min"