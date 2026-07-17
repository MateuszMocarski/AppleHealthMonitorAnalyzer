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

        for activity in summary.activities:
            self._render_activity(activity)

        print("Total")
        print(f"  Duration: {summary.total_duration_minutes:.1f} min")
        print(f"  Energy:   {summary.total_active_energy_kcal:.0f} kcal")
        print("-" * 60)
        print()

    def _render_activity(self, activity: ActivitySummary) -> None:
        print(activity.activity_type.value.title())
        print(f"  Sessions: {activity.sessions}")
        print(f"  Duration: {activity.duration_minutes:.1f} min")
        print(f"  Energy:   {activity.active_energy_kcal:.0f} kcal")

        if activity.distance_km is not None:
            print(f"  Distance: {activity.distance_km:.2f} km")

        print()
        
    def render_month_summary(
        self,
        summary: MonthlySummary,
    ) -> None:
        
        header = f"Month summary for {calendar.month_name[summary.month]}-{summary.year}"
        print(header)
        print("=" * len(header))
        
        for activity in summary.activities:
            print(activity.activity_type.value.title())
            print(f"  Sessions: {activity.sessions}")
            print(f"  Duration: {activity.duration_minutes:.1f} min")
            print(f"  Energy:   {activity.active_energy_kcal:.0f} kcal")

            if activity.distance_km is not None:
                print(f"  Distance: {activity.distance_km:.2f} km")
                
            divisor = (
                activity.sessions
                if activity.activity_type is WorkoutType.CYCLING
                else summary.reporting_days
            )
            
            averaging_label = (
                "Workout"
                if activity.activity_type is WorkoutType.CYCLING
                else "Daily"
            )
            
            avg_duration = activity.duration_minutes / divisor
            avg_energy = activity.active_energy_kcal / divisor

            if activity.distance_km is not None:
                avg_distance = activity.distance_km / divisor
            
            print()
            print(f"  Average {averaging_label} Duration: {avg_duration:.1f} min")
            print(f"  Average {averaging_label} Energy:   {avg_energy:.0f} kcal")
            if activity.distance_km is not None:
                print(f"  Average {averaging_label} Distance: {avg_distance:.2f} km")
            print()