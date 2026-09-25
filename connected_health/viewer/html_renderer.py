"""Provider-neutral semantic HTML rendering for validated Viewer reports."""

from __future__ import annotations

from html import escape
from typing import Any

from connected_health.viewer.report_contract import (
    DailyReport,
    DailySleep,
    FullReport,
    ViewerReport,
)


class HtmlRenderer:
    """Render only validated persisted Viewer report models into semantic HTML."""

    def render(self, report: ViewerReport) -> str:
        kind = "full" if isinstance(report, FullReport) else "summary"
        period = f"{report.report.year}-{report.report.month:02d}"
        parts = [
            f'<article class="viewer-report" data-report-kind="{escape(kind)}">',
            "<header>",
            f"<h1>Monthly report: {escape(period)}</h1>",
            f"<p>Reporting days: {self._value(report.report.reporting_days)}</p>",
            f"<p>Data through: {self._value(report.report.data_through)}</p>",
            "</header>",
            self._monthly_sections(report),
        ]

        if isinstance(report, FullReport):
            parts.append(self._daily_section(report))

        parts.append("</article>")
        return "".join(parts)

    def _monthly_sections(self, report: ViewerReport) -> str:
        return "".join(
            (
                self._section(
                    "General activity",
                    report.general_activity,
                    ("total_steps", "total_distance_km", "average_daily_steps"),
                ),
                self._section(
                    "Sleep",
                    report.sleep,
                    ("sessions", "average_sleep_minutes", "average_efficiency_percent"),
                ),
                self._workouts_section(report),
                self._section(
                    "Body weight",
                    report.body_weight,
                    ("average_kg", "start_kg", "end_kg", "measurements"),
                ),
                self._section(
                    "Energy expenditure",
                    report.energy_expenditure,
                    ("average_basal_kcal", "average_active_kcal", "average_tdee_kcal"),
                ),
                self._section(
                    "Nutrition",
                    report.nutrition,
                    (
                        "average_protein_g",
                        "average_carbohydrates_g",
                        "average_fat_g",
                        "average_calories_kcal",
                    ),
                ),
                self._section(
                    "Calories balance",
                    report.calories_balance,
                    ("average_calories_balance_kcal", "total_calories_balance_kcal"),
                ),
            )
        )

    def _workouts_section(self, report: ViewerReport) -> str:
        if not report.workouts:
            return "<section><h2>Workouts</h2><p>No workouts recorded.</p></section>"

        workouts = "".join(
            "<li>"
            f"{escape(workout.type)}: {self._value(workout.sessions)} session(s), "
            f"{self._value(workout.duration_minutes)} minutes"
            "</li>"
            for workout in report.workouts
        )
        return f"<section><h2>Workouts</h2><ul>{workouts}</ul></section>"

    def _daily_section(self, report: FullReport) -> str:
        if not report.days:
            return '<section data-viewer-daily="true"><h2>Daily details</h2></section>'

        days = "".join(self._daily_report(day) for day in report.days)
        return f'<section data-viewer-daily="true"><h2>Daily details</h2>{days}</section>'

    def _daily_report(self, day: DailyReport) -> str:
        return "".join(
            (
                '<article class="viewer-day">',
                f"<h3>{self._value(day.date)}</h3>",
                self._daily_fields(
                    "General activity",
                    day.general_activity,
                    ("steps", "distance_km", "step_length_cm"),
                ),
                self._daily_sleep(day.sleep),
                self._daily_workouts(day),
                self._daily_fields("Body weight", day.body_weight, ("weight_kg",)),
                self._daily_fields(
                    "Energy expenditure",
                    day.energy_expenditure,
                    ("basal_kcal", "active_kcal", "tdee_kcal"),
                ),
                self._daily_fields(
                    "Nutrition",
                    day.nutrition,
                    ("protein_g", "carbohydrates_g", "fat_g", "calories_kcal"),
                ),
                self._daily_value("Calories balance", day.calories_balance_kcal),
                "</article>",
            )
        )

    def _daily_sleep(self, sleep: DailySleep | None) -> str:
        if sleep is None:
            return self._daily_unavailable("Sleep")

        return "".join(
            (
                self._daily_fields(
                    "Sleep session",
                    sleep.session,
                    (
                        "bedtime",
                        "wake_up",
                        "time_in_bed_minutes",
                        "time_asleep_minutes",
                        "awake_minutes",
                        "efficiency_percent",
                    ),
                ),
                self._daily_fields(
                    "Sleep stages",
                    sleep.session.stages,
                    (
                        "core_minutes",
                        "deep_minutes",
                        "rem_minutes",
                        "unspecified_minutes",
                    ),
                ),
                self._daily_fields(
                    "Sleep score",
                    sleep.score,
                    ("bedtime", "duration", "wake_up", "total"),
                ),
            )
        )

    def _daily_workouts(self, day: DailyReport) -> str:
        if not day.workouts:
            return (
                '<section class="viewer-day-section"><h4>Workouts</h4>'
                "<p>No workouts recorded.</p></section>"
            )

        workouts = "".join(
            "<li><dl>"
            f"<dt>type</dt><dd>{escape(workout.type)}</dd>"
            f"<dt>sessions</dt><dd>{self._value(workout.sessions)}</dd>"
            f"<dt>duration minutes</dt><dd>{self._value(workout.duration_minutes)}</dd>"
            f"<dt>active energy kcal</dt><dd>{self._value(workout.active_energy_kcal)}</dd>"
            f"<dt>distance km</dt><dd>{self._value(workout.distance_km)}</dd>"
            "</dl></li>"
            for workout in day.workouts
        )
        return f'<section class="viewer-day-section"><h4>Workouts</h4><ul>{workouts}</ul></section>'

    def _daily_fields(self, title: str, source: Any, fields: tuple[str, ...]) -> str:
        if source is None:
            return self._daily_unavailable(title)

        values = "".join(
            f"<dt>{escape(field.replace('_', ' '))}</dt>"
            f"<dd>{self._value(getattr(source, field))}</dd>"
            for field in fields
        )
        return (
            f'<section class="viewer-day-section"><h4>{escape(title)}</h4>'
            f"<dl>{values}</dl></section>"
        )

    def _daily_value(self, title: str, value: Any) -> str:
        return (
            f'<section class="viewer-day-section"><h4>{escape(title)}</h4>'
            f"<p>{self._value(value)}</p></section>"
        )

    @staticmethod
    def _daily_unavailable(title: str) -> str:
        return (
            f'<section class="viewer-day-section"><h4>{escape(title)}</h4>'
            '<p class="unavailable">Unavailable</p></section>'
        )

    def _section(self, title: str, source: Any, fields: tuple[str, ...]) -> str:
        if source is None:
            return (
                f"<section><h2>{escape(title)}</h2>"
                '<p class="unavailable">Unavailable</p></section>'
            )

        values = "".join(
            f"<dt>{escape(field.replace('_', ' '))}</dt>"
            f"<dd>{self._value(getattr(source, field))}</dd>"
            for field in fields
        )
        return f"<section><h2>{escape(title)}</h2><dl>{values}</dl></section>"

    @staticmethod
    def _value(value: Any) -> str:
        if value is None:
            return '<span class="unavailable">Unavailable</span>'
        return escape(str(value))
