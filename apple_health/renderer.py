from __future__ import annotations

from apple_health.report_models import ActivitySummary
from apple_health.report_models import DailySummary


class ConsoleRenderer:
    def render_month(self, summaries: list[DailySummary]) -> None:
        for summary in summaries:
            self._render_day(summary)

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