"""Provider-neutral HTML rendering for validated Viewer reports."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time
from html import escape
from typing import Any

from connected_health.viewer.charts import (
    ChartDatum,
    bar_chart,
    diverging_bar_chart,
    donut_chart,
    dual_axis_line_chart,
    line_chart,
)
from connected_health.viewer.report_contract import (
    DailyReport,
    DailySleep,
    FullReport,
    MonthlyWorkout,
    ViewerReport,
)


class HtmlRenderer:
    """Render validated persisted Viewer reports without analysis calculations."""

    def render(self, report: ViewerReport) -> str:
        kind = "Full" if isinstance(report, FullReport) else "Summary"
        parts = [
            f'<article class="viewer-report" data-report-kind="{kind.lower()}">',
            self._report_header(report, kind),
            '<div class="viewer-monthly-dashboard">',
            self._general_activity_section(report),
            self._sleep_section(report),
            self._workouts_section(report),
            self._body_weight_section(report),
            self._energy_section(report),
            self._nutrition_section(report),
            self._calories_balance_section(report),
            "</div>",
        ]
        if isinstance(report, FullReport):
            parts.append(self._daily_section(report))
        else:
            parts.append(self._summary_daily_notice())
        parts.append("</article>")
        return "".join(parts)

    def _report_header(self, report: ViewerReport, kind: str) -> str:
        month = calendar.month_name[report.report.month]
        return (
            '<header class="viewer-report-header">'
            '<p class="viewer-report-eyebrow">Monthly health report</p>'
            f"<h1>{escape(month)} {report.report.year}</h1>"
            '<div class="viewer-report-meta">'
            f'<span class="viewer-report-kind">{escape(kind)} report</span>'
            '<dl class="viewer-report-details">'
            "<div><dt>Reporting days</dt>"
            f"<dd>{self._value(report.report.reporting_days)}</dd></div>"
            "<div><dt>Data through</dt>"
            f"<dd>{self._date_value(report.report.data_through)}</dd></div>"
            "</dl></div></header>"
        )

    def _general_activity_section(self, report: ViewerReport) -> str:
        activity = report.general_activity
        if activity is None:
            return self._unavailable_section_with_charts(
                "General activity",
                "activity",
                self._activity_charts(report),
            )
        metrics = "".join(
            (
                self._metric("Total steps", activity.total_steps),
                self._metric(
                    "Average daily steps",
                    activity.average_daily_steps,
                    coverage=activity.steps_count_days,
                ),
                self._metric("Total distance", activity.total_distance_km, "km"),
                self._metric(
                    "Average daily distance",
                    activity.average_daily_distance_km,
                    "km",
                    activity.distance_count_days,
                ),
                self._metric(
                    "Average step length",
                    activity.average_step_length_cm,
                    "cm",
                    activity.step_length_count_days,
                ),
            )
        )
        return self._section(
            "General activity",
            "activity",
            f'<dl class="viewer-metric-grid">{metrics}</dl>{self._activity_charts(report)}',
            grid=False,
        )

    def _sleep_section(self, report: ViewerReport) -> str:
        sleep = report.sleep
        if sleep is None:
            return self._unavailable_section_with_charts(
                "Sleep",
                "sleep",
                self._full_sleep_trends(report),
            )
        session_metrics = "".join(
            (
                self._metric("Sessions", sleep.sessions),
                self._metric("Average bedtime", self._time_value(sleep.average_bedtime)),
                self._metric("Average wake-up", self._time_value(sleep.average_wake_up)),
                self._metric("Average sleep duration", sleep.average_sleep_minutes, "minutes"),
                self._metric("Average awake duration", sleep.average_awake_minutes, "minutes"),
                self._metric("Average efficiency", sleep.average_efficiency_percent, "%"),
            )
        )
        stage_metrics = "".join(
            (
                self._metric("Core sleep", sleep.stages.core_minutes, "minutes"),
                self._metric("Deep sleep", sleep.stages.deep_minutes, "minutes"),
                self._metric("REM sleep", sleep.stages.rem_minutes, "minutes"),
                self._metric("Unspecified sleep", sleep.stages.unspecified_minutes, "minutes"),
            )
        )
        score_metrics = "".join(
            (
                self._metric("Average bedtime score", sleep.score.average_bedtime),
                self._metric("Average duration score", sleep.score.average_duration),
                self._metric("Average wake-up score", sleep.score.average_wake_up),
                self._metric("Average sleep score", sleep.score.average_total),
                self._metric("Average bonus", sleep.score.average_bonus),
                self._metric("Consistency bonus", sleep.score.consistency_bonus),
                self._metric("Monthly score", sleep.score.monthly_score),
                self._metric("Maximum monthly score", sleep.score.monthly_score_max),
            )
        )
        content = (
            '<dl class="viewer-metric-grid">'
            f"{session_metrics}</dl>"
            '<section class="viewer-monthly-subsection"><h3>Sleep stages</h3>'
            f'<dl class="viewer-metric-grid">{stage_metrics}</dl></section>'
            '<section class="viewer-monthly-subsection"><h3>Sleep score</h3>'
            f'<dl class="viewer-metric-grid">{score_metrics}</dl></section>'
            f"{self._sleep_charts(sleep)}"
            f"{self._full_sleep_trends(report)}"
            f"{self._sleep_configuration(sleep.configuration)}"
        )
        return self._section("Sleep", "sleep", content, grid=False)

    def _workouts_section(self, report: ViewerReport) -> str:
        if not report.workouts:
            return self._section(
                "Workouts",
                "workouts",
                '<p class="viewer-empty-state">No workouts recorded.</p>',
                grid=False,
            )
        workouts = "".join(self._workout_card(workout) for workout in report.workouts)
        return self._section(
            "Workouts",
            "workouts",
            '<div class="viewer-workout-list">'
            f"{workouts}</div>{self._workout_charts(report.workouts)}",
            grid=False,
        )

    def _workout_card(self, workout: MonthlyWorkout) -> str:
        workout_type = escape(workout.type.replace("_", " ").capitalize())
        average_basis = "Per day" if workout.average_basis == "daily" else "Per workout"
        metrics = "".join(
            (
                self._metric("Sessions", workout.sessions),
                self._metric("Total duration", workout.duration_minutes, "minutes"),
                self._metric("Active energy", workout.active_energy_kcal, "kcal"),
                self._metric("Distance", workout.distance_km, "km"),
                self._metric("Average basis", average_basis),
                self._metric("Average duration", workout.average_duration_minutes, "minutes"),
                self._metric("Average active energy", workout.average_active_energy_kcal, "kcal"),
                self._metric("Average distance", workout.average_distance_km, "km"),
            )
        )
        return (
            '<article class="viewer-workout-card">'
            f"<h3>{workout_type}</h3>"
            f'<dl class="viewer-metric-grid">{metrics}</dl></article>'
        )

    def _body_weight_section(self, report: ViewerReport) -> str:
        body_weight = report.body_weight
        if body_weight is None:
            return self._unavailable_section_with_charts(
                "Body weight",
                "body-weight",
                self._weight_chart(report),
            )
        metrics = "".join(
            (
                self._metric("Average weight", body_weight.average_kg, "kg"),
                self._metric("Starting weight", body_weight.start_kg, "kg"),
                self._metric("Ending weight", body_weight.end_kg, "kg"),
                self._metric("Change", body_weight.change_kg, "kg"),
                self._metric("Minimum weight", body_weight.min_kg, "kg"),
                self._metric("Maximum weight", body_weight.max_kg, "kg"),
                self._metric("Measurements", body_weight.measurements),
            )
        )
        return self._section(
            "Body weight",
            "body-weight",
            f'<dl class="viewer-metric-grid">{metrics}</dl>{self._weight_chart(report)}',
            grid=False,
        )

    def _energy_section(self, report: ViewerReport) -> str:
        energy = report.energy_expenditure
        if energy is None:
            return self._unavailable_section("Energy expenditure", "energy")
        return self._section(
            "Energy expenditure",
            "energy",
            (
                self._metric(
                    "Average basal energy",
                    energy.average_basal_kcal,
                    "kcal",
                    energy.basal_count_days,
                ),
                self._metric(
                    "Average active energy",
                    energy.average_active_kcal,
                    "kcal",
                    energy.active_count_days,
                ),
                self._metric(
                    "Average TDEE", energy.average_tdee_kcal, "kcal", energy.tdee_count_days
                ),
            ),
        )

    def _nutrition_section(self, report: ViewerReport) -> str:
        nutrition = report.nutrition
        if nutrition is None:
            return self._unavailable_section_with_charts(
                "Nutrition",
                "nutrition",
                self._nutrition_charts(report),
            )
        metrics = "".join(
            (
                self._metric(
                    "Average protein",
                    nutrition.average_protein_g,
                    "g",
                    nutrition.protein_count_days,
                ),
                self._metric(
                    "Average carbohydrates",
                    nutrition.average_carbohydrates_g,
                    "g",
                    nutrition.carbohydrates_count_days,
                ),
                self._metric("Average fat", nutrition.average_fat_g, "g", nutrition.fat_count_days),
                self._metric(
                    "Average calories",
                    nutrition.average_calories_kcal,
                    "kcal",
                    nutrition.calories_count_days,
                ),
            )
        )
        return self._section(
            "Nutrition",
            "nutrition",
            f'<dl class="viewer-metric-grid">{metrics}</dl>{self._nutrition_charts(report)}',
            grid=False,
        )

    def _calories_balance_section(self, report: ViewerReport) -> str:
        balance = report.calories_balance
        metrics = "".join(
            (
                self._metric(
                    "Average calorie balance",
                    balance.average_calories_balance_kcal,
                    "kcal",
                    balance.calories_balance_count_days,
                ),
                self._metric(
                    "Total calorie balance",
                    balance.total_calories_balance_kcal,
                    "kcal",
                    balance.calories_balance_count_days,
                ),
            )
        )
        return self._section(
            "Calorie balance",
            "calorie-balance",
            f'<dl class="viewer-metric-grid">{metrics}</dl>{self._calorie_balance_chart(report)}',
            grid=False,
        )

    def _activity_charts(self, report: ViewerReport) -> str:
        if not isinstance(report, FullReport):
            return ""
        days = self._ordered_days(report)
        return self._chart_grid(
            dual_axis_line_chart(
                "Daily steps and distance",
                [self._day_label(day.date) for day in days],
                [
                    day.general_activity.steps if day.general_activity is not None else None
                    for day in days
                ],
                [
                    day.general_activity.distance_km if day.general_activity is not None else None
                    for day in days
                ],
                left_label="Steps",
                right_label="Distance (km)",
            )
        )

    def _sleep_charts(self, sleep: Any) -> str:
        charts = [
            donut_chart(
                "Average sleep stages",
                (
                    ChartDatum("Core", sleep.stages.core_minutes),
                    ChartDatum("Deep", sleep.stages.deep_minutes),
                    ChartDatum("REM", sleep.stages.rem_minutes),
                    ChartDatum("Unspecified", sleep.stages.unspecified_minutes),
                ),
                "minutes",
            ),
            bar_chart(
                "Average Sleep Score components",
                (
                    ChartDatum("Bedtime", sleep.score.average_bedtime),
                    ChartDatum("Duration", sleep.score.average_duration),
                    ChartDatum("Wake-up", sleep.score.average_wake_up),
                ),
                "points",
                maximum=100,
            ),
            self._chart_kpis(
                (
                    ("Monthly score", sleep.score.monthly_score, None),
                    ("Maximum monthly score", sleep.score.monthly_score_max, None),
                    ("Average bonus", sleep.score.average_bonus, None),
                    ("Consistency bonus", sleep.score.consistency_bonus, None),
                )
            ),
        ]
        return self._chart_grid(*charts)

    def _full_sleep_trends(self, report: ViewerReport) -> str:
        if not isinstance(report, FullReport):
            return ""
        days = self._ordered_days(report)
        return self._chart_grid(
            line_chart(
                "Bedtime by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        (
                            self._bedtime_minutes(day.sleep.session.bedtime)
                            if day.sleep is not None
                            else None
                        ),
                    )
                    for day in days
                ],
                "",
                axis_label="Bedtime",
                axis_formatter=self._clock_label,
            ),
            line_chart(
                "Wake-up time by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        (
                            self._clock_minutes(day.sleep.session.wake_up)
                            if day.sleep is not None
                            else None
                        ),
                    )
                    for day in days
                ],
                "",
                axis_label="Wake-up",
                axis_formatter=self._clock_label,
            ),
        )

    def _workout_charts(self, workouts: list[MonthlyWorkout]) -> str:
        duration = donut_chart(
            "Total workout duration by type",
            tuple(
                ChartDatum(self._workout_label(workout.type), workout.duration_minutes)
                for workout in workouts
            ),
            "minutes",
        )
        with_energy = [workout for workout in workouts if workout.active_energy_kcal is not None]
        energy = donut_chart(
            "Total active energy by type",
            tuple(
                ChartDatum(self._workout_label(workout.type), workout.active_energy_kcal)
                for workout in with_energy
            ),
            "kcal",
        )
        missing_note = ""
        if len(with_energy) != len(workouts):
            missing_note = (
                '<p class="viewer-chart-note">'
                "Some workout types have unavailable active-energy data; "
                "the chart includes only types with persisted active energy.</p>"
            )
        return self._chart_grid(duration, f"{energy}{missing_note}")

    def _weight_chart(self, report: ViewerReport) -> str:
        if not isinstance(report, FullReport):
            return ""
        return self._chart_grid(
            line_chart(
                "Body weight by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        day.body_weight.weight_kg if day.body_weight is not None else None,
                    )
                    for day in self._ordered_days(report)
                ],
                "kg",
                axis_label="Weight (kg)",
            )
        )

    def _nutrition_charts(self, report: ViewerReport) -> str:
        if not isinstance(report, FullReport):
            return ""
        days = self._ordered_days(report)
        charts = (
            line_chart(
                "Protein by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        day.nutrition.protein_g if day.nutrition is not None else None,
                    )
                    for day in days
                ],
                "g",
                axis_label="Protein (g)",
            ),
            line_chart(
                "Carbohydrates by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        day.nutrition.carbohydrates_g if day.nutrition is not None else None,
                    )
                    for day in days
                ],
                "g",
                axis_label="Carbohydrates (g)",
            ),
            line_chart(
                "Fat by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        day.nutrition.fat_g if day.nutrition is not None else None,
                    )
                    for day in days
                ],
                "g",
                axis_label="Fat (g)",
            ),
            line_chart(
                "Calories by day",
                [
                    ChartDatum(
                        self._day_label(day.date),
                        day.nutrition.calories_kcal if day.nutrition is not None else None,
                    )
                    for day in days
                ],
                "kcal",
                axis_label="Calories (kcal)",
            ),
        )
        return self._chart_grid(*charts)

    def _calorie_balance_chart(self, report: ViewerReport) -> str:
        if not isinstance(report, FullReport):
            return ""
        return self._chart_grid(
            diverging_bar_chart(
                "Daily calorie balance",
                [
                    ChartDatum(self._day_label(day.date), day.calories_balance_kcal)
                    for day in self._ordered_days(report)
                ],
                "kcal",
            )
        )

    def _sleep_configuration(self, configuration: Any) -> str:
        monthly_bonus = configuration.monthly_bonus
        groups = (
            self._config_section(
                "General",
                (
                    (
                        "Session gap threshold",
                        self._value(configuration.session_gap_threshold_minutes, "minutes"),
                    ),
                    ("Penalty style", "Linear" if configuration.linear_penalties else "Step"),
                ),
            ),
            self._config_section(
                "Bedtime",
                (
                    ("Target", self._time_value(configuration.bedtime.target)),
                    (
                        "Penalty interval",
                        self._value(configuration.bedtime.penalty_interval_minutes, "minutes"),
                    ),
                    ("Penalty points", self._value(configuration.bedtime.penalty_points)),
                ),
            ),
            self._config_section(
                "Duration",
                (
                    ("Target", self._value(configuration.duration.target_minutes, "minutes")),
                    ("Tolerance", self._value(configuration.duration.tolerance_minutes, "minutes")),
                    (
                        "Penalty interval",
                        self._value(configuration.duration.penalty_interval_minutes, "minutes"),
                    ),
                    ("Penalty points", self._value(configuration.duration.penalty_points)),
                    ("Oversleep weight", self._value(configuration.duration.oversleep_weight)),
                    ("Undersleep weight", self._value(configuration.duration.undersleep_weight)),
                ),
            ),
            self._config_section(
                "Wake-up",
                (
                    ("Target", self._time_value(configuration.wake_up.target)),
                    ("Bedtime weight", self._value(configuration.wake_up.bedtime_weight)),
                    ("Duration weight", self._value(configuration.wake_up.duration_weight)),
                    (
                        "Penalty interval",
                        self._value(configuration.wake_up.penalty_interval_minutes, "minutes"),
                    ),
                    ("Penalty points", self._value(configuration.wake_up.penalty_points)),
                ),
            ),
            self._config_section(
                "Score weights",
                (
                    ("Bedtime", self._value(configuration.weights.bedtime)),
                    ("Duration", self._value(configuration.weights.duration)),
                    ("Wake-up", self._value(configuration.weights.wake_up)),
                ),
            ),
            self._config_section(
                "Monthly bonus",
                (
                    ("Enabled", "Yes" if monthly_bonus.enabled else "No"),
                    ("Maximum points", self._value(monthly_bonus.max_points)),
                ),
                "<h5>Average thresholds</h5><ul>"
                f"{self._threshold_list(monthly_bonus.average_thresholds)}</ul>"
                "<h5>Consistency thresholds</h5><ul>"
                f"{self._threshold_list(monthly_bonus.consistency_thresholds)}</ul>",
            ),
        )
        return "".join(
            (
                '<button class="viewer-config-button" type="button" data-viewer-config-open>',
                "Sleep score configuration</button>",
                '<dialog class="viewer-sleep-config-dialog" data-viewer-sleep-config>',
                "<header><h3>Sleep score configuration</h3>",
                '<button type="button" data-viewer-config-close '
                'aria-label="Close sleep score configuration">'
                "Close</button></header>",
                '<div class="viewer-config-groups">',
                *groups,
                "</div></dialog>",
            )
        )

    @staticmethod
    def _config_section(title: str, rows: tuple[tuple[str, str], ...], extra: str = "") -> str:
        details = "".join(f"<dt>{escape(label)}</dt><dd>{value}</dd>" for label, value in rows)
        return f"<section><h4>{escape(title)}</h4><dl>{details}</dl>{extra}</section>"

    def _threshold_list(self, thresholds: list[Any]) -> str:
        return (
            "".join(
                f"<li>{self._value(item.threshold)}: {self._value(item.bonus)} bonus</li>"
                for item in thresholds
            )
            or "<li>Unavailable</li>"
        )

    @staticmethod
    def _chart_grid(*charts: str) -> str:
        rendered = "".join(chart for chart in charts if chart)
        return f'<div class="viewer-chart-grid">{rendered}</div>' if rendered else ""

    def _chart_kpis(self, values: tuple[tuple[str, Any, str | None], ...]) -> str:
        metrics = "".join(self._metric(label, value, unit) for label, value, unit in values)
        return f'<dl class="viewer-chart-kpis">{metrics}</dl>'

    @staticmethod
    def _ordered_days(report: FullReport) -> list[DailyReport]:
        return sorted(report.days, key=lambda day: day.date)

    @staticmethod
    def _day_label(value: date) -> str:
        return value.strftime("%b %d").replace(" 0", " ")

    @staticmethod
    def _workout_label(value: str) -> str:
        return value.replace("_", " ").capitalize()

    @staticmethod
    def _clock_minutes(value: datetime) -> float:
        return float(value.hour * 60 + value.minute + value.second / 60)

    def _bedtime_minutes(self, value: datetime) -> float:
        minutes = self._clock_minutes(value)
        return minutes + 24 * 60 if minutes < 12 * 60 else minutes

    @staticmethod
    def _clock_label(value: float) -> str:
        minutes = int(round(value)) % (24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _section(
        self, title: str, name: str, content: tuple[str, ...] | str, *, grid: bool = True
    ) -> str:
        if isinstance(content, tuple):
            content = "".join(content)
        if grid:
            content = f'<dl class="viewer-metric-grid">{content}</dl>'
        return (
            f'<section class="viewer-monthly-section viewer-monthly-section--{name}">'
            f"<h2>{escape(title)}</h2>{content}</section>"
        )

    def _unavailable_section(self, title: str, name: str) -> str:
        return (
            f'<section class="viewer-monthly-section viewer-monthly-section--{name} '
            'viewer-monthly-section--unavailable">'
            f'<h2>{escape(title)}</h2><p class="viewer-unavailable">Unavailable</p></section>'
        )

    def _unavailable_section_with_charts(self, title: str, name: str, charts: str) -> str:
        return (
            f'<section class="viewer-monthly-section viewer-monthly-section--{name} '
            'viewer-monthly-section--unavailable">'
            f"<h2>{escape(title)}</h2>"
            '<p class="viewer-unavailable">Unavailable</p>'
            f"{charts}</section>"
        )

    def _metric(
        self, label: str, value: Any, unit: str | None = None, coverage: int | None = None
    ) -> str:
        coverage_html = ""
        if coverage is not None:
            day_label = "day" if coverage == 1 else "days"
            coverage_html = (
                f'<span class="viewer-metric-coverage">Coverage: {coverage} {day_label}</span>'
            )
        return (
            '<div class="viewer-metric">'
            f"<dt>{escape(label)}</dt><dd>{self._value(value, unit)}{coverage_html}</dd></div>"
        )

    def _daily_section(self, report: FullReport) -> str:
        if not report.days:
            return (
                '<section class="viewer-daily-view" data-viewer-daily="true">'
                '<header class="viewer-daily-header"><h2>Daily details</h2></header>'
                '<p class="viewer-empty-state">'
                "No daily details are available for this Full report."
                "</p></section>"
            )

        ordered_days = sorted(report.days, key=lambda day: day.date)
        latest_day = ordered_days[-1]
        previous_disabled = " disabled" if len(ordered_days) == 1 else ""
        days = "".join(
            self._daily_report(day, hidden=day.date != latest_day.date) for day in ordered_days
        )
        return "".join(
            (
                '<section class="viewer-daily-view" data-viewer-daily="true">',
                '<header class="viewer-daily-header"><h2>Daily details</h2>',
                '<div class="viewer-daily-navigation" data-viewer-daily-navigation>',
                '<button type="button" data-viewer-day-previous'
                f"{previous_disabled}>Previous day</button>",
                '<p class="viewer-daily-current-day" aria-live="polite">',
                f'<time data-viewer-current-day datetime="{latest_day.date.isoformat()}">',
                f"{self._date_value(latest_day.date)}</time></p>",
                '<button type="button" data-viewer-day-next disabled>Next day</button>',
                "</div></header>",
                days,
                "</section>",
            )
        )

    def _summary_daily_notice(self) -> str:
        return (
            '<section class="viewer-daily-summary-notice">'
            "<h2>Daily details</h2>"
            "<p>Daily details are not available in Summary reports.</p>"
            "</section>"
        )

    def _daily_report(self, day: DailyReport, *, hidden: bool) -> str:
        hidden_attribute = " hidden" if hidden else ""
        day_identifier = day.date.isoformat()
        day_label = self._date_value(day.date)
        return "".join(
            (
                '<article class="viewer-day" '
                f'data-viewer-day="{day_identifier}" data-viewer-day-label="{day_label}"'
                f"{hidden_attribute}>",
                '<header class="viewer-day-header"><h3>',
                f'<time data-viewer-day-label datetime="{day_identifier}">',
                f"{day_label}</time></h3></header>",
                '<div class="viewer-daily-dashboard">',
                self._daily_fields(
                    "General activity",
                    day.general_activity,
                    (
                        ("Steps", "steps", None),
                        ("Distance", "distance_km", "km"),
                        ("Step length", "step_length_cm", "cm"),
                    ),
                ),
                self._daily_sleep(day.sleep),
                self._daily_workouts(day),
                self._daily_fields(
                    "Body weight", day.body_weight, (("Weight", "weight_kg", "kg"),)
                ),
                self._daily_fields(
                    "Energy expenditure",
                    day.energy_expenditure,
                    (
                        ("Basal energy", "basal_kcal", "kcal"),
                        ("Active energy", "active_kcal", "kcal"),
                        ("TDEE", "tdee_kcal", "kcal"),
                    ),
                ),
                self._daily_nutrition(day),
                self._daily_value("Calorie balance", day.calories_balance_kcal, "kcal"),
                "</div></article>",
            )
        )

    def _daily_sleep(self, sleep: DailySleep | None) -> str:
        if sleep is None:
            return self._daily_unavailable("Sleep")
        fields = "".join(
            (
                self._daily_fields(
                    "Sleep session",
                    sleep.session,
                    (
                        ("Bedtime", "bedtime", None),
                        ("Wake-up", "wake_up", None),
                        ("Time in bed", "time_in_bed_minutes", "minutes"),
                        ("Time asleep", "time_asleep_minutes", "minutes"),
                        ("Awake duration", "awake_minutes", "minutes"),
                        ("Efficiency", "efficiency_percent", "%"),
                    ),
                ),
                self._daily_fields(
                    "Sleep stages",
                    sleep.session.stages,
                    (
                        ("Core sleep", "core_minutes", "minutes"),
                        ("Deep sleep", "deep_minutes", "minutes"),
                        ("REM sleep", "rem_minutes", "minutes"),
                        ("Unspecified sleep", "unspecified_minutes", "minutes"),
                    ),
                ),
                self._daily_fields(
                    "Sleep score",
                    sleep.score,
                    (
                        ("Bedtime score", "bedtime", None),
                        ("Duration score", "duration", None),
                        ("Wake-up score", "wake_up", None),
                        ("Total score", "total", None),
                    ),
                ),
            )
        )
        charts = [
            donut_chart(
                "Sleep stages",
                (
                    ChartDatum("Core", sleep.session.stages.core_minutes),
                    ChartDatum("Deep", sleep.session.stages.deep_minutes),
                    ChartDatum("REM", sleep.session.stages.rem_minutes),
                    ChartDatum("Unspecified", sleep.session.stages.unspecified_minutes),
                ),
                "minutes",
            )
        ]
        if sleep.score is not None:
            charts.extend(
                (
                    bar_chart(
                        "Sleep Score components",
                        (
                            ChartDatum("Bedtime", sleep.score.bedtime),
                            ChartDatum("Duration", sleep.score.duration),
                            ChartDatum("Wake-up", sleep.score.wake_up),
                        ),
                        "points",
                        maximum=100,
                    ),
                    self._chart_kpis((("Total score", sleep.score.total, None),)),
                )
            )
        return f"{fields}{self._chart_grid(*charts)}"

    def _daily_nutrition(self, day: DailyReport) -> str:
        nutrition = day.nutrition
        fields = self._daily_fields(
            "Nutrition",
            nutrition,
            (
                ("Protein", "protein_g", "g"),
                ("Carbohydrates", "carbohydrates_g", "g"),
                ("Fat", "fat_g", "g"),
                ("Calories", "calories_kcal", "kcal"),
            ),
        )
        if nutrition is None:
            return fields
        chart = bar_chart(
            "Daily macros",
            (
                ChartDatum("Protein", nutrition.protein_g),
                ChartDatum("Carbohydrates", nutrition.carbohydrates_g),
                ChartDatum("Fat", nutrition.fat_g),
            ),
            "g",
        )
        calories_kpi = self._chart_kpis((("Calories", nutrition.calories_kcal, "kcal"),))
        return f"{fields}{self._chart_grid(chart, calories_kpi)}"

    def _daily_workouts(self, day: DailyReport) -> str:
        if not day.workouts:
            return (
                '<section class="viewer-daily-section viewer-daily-section--workouts">'
                '<h4>Workouts</h4><p class="viewer-empty-state">No workouts recorded.</p></section>'
            )
        workouts = "".join(
            '<li class="viewer-daily-workout-card">'
            f"<h5>{escape(workout.type.replace('_', ' ').capitalize())}</h5>"
            '<dl class="viewer-metric-grid viewer-daily-metric-grid">'
            f"{self._metric('Sessions', workout.sessions)}"
            f"{self._metric('Duration', workout.duration_minutes, 'minutes')}"
            f"{self._metric('Active energy', workout.active_energy_kcal, 'kcal')}"
            f"{self._metric('Distance', workout.distance_km, 'km')}</dl></li>"
            for workout in day.workouts
        )
        return (
            '<section class="viewer-daily-section viewer-daily-section--workouts">'
            f'<h4>Workouts</h4><ul class="viewer-daily-workout-list">{workouts}</ul></section>'
        )

    def _daily_fields(
        self, title: str, source: Any, fields: tuple[tuple[str, str, str | None], ...]
    ) -> str:
        if source is None:
            return self._daily_unavailable(title)
        values = "".join(
            self._daily_metric(label, getattr(source, field), unit) for label, field, unit in fields
        )
        return (
            '<section class="viewer-daily-section">'
            f"<h4>{escape(title)}</h4>"
            f'<dl class="viewer-metric-grid viewer-daily-metric-grid">{values}</dl></section>'
        )

    def _daily_value(self, title: str, value: Any, unit: str | None = None) -> str:
        return (
            '<section class="viewer-daily-section">'
            f"<h4>{escape(title)}</h4>"
            '<dl class="viewer-metric-grid viewer-daily-metric-grid">'
            f"{self._daily_metric('Daily balance', value, unit)}</dl></section>"
        )

    @staticmethod
    def _daily_unavailable(title: str) -> str:
        return (
            '<section class="viewer-daily-section viewer-daily-section--unavailable">'
            f"<h4>{escape(title)}</h4>"
            '<p class="viewer-unavailable unavailable">Unavailable</p></section>'
        )

    def _daily_metric(self, label: str, value: Any, unit: str | None = None) -> str:
        if isinstance(value, datetime):
            rendered_value = self._datetime_value(value)
        else:
            rendered_value = self._value(value, unit)
        return (
            '<div class="viewer-metric">' f"<dt>{escape(label)}</dt><dd>{rendered_value}</dd></div>"
        )

    @staticmethod
    def _time_value(value: time) -> str:
        return value.strftime("%H:%M")

    def _date_value(self, value: date | None) -> str:
        if value is None:
            return '<span class="viewer-unavailable unavailable">Unavailable</span>'
        return escape(value.strftime("%B %d, %Y").replace(" 0", " "))

    @staticmethod
    def _datetime_value(value: datetime) -> str:
        return escape(value.strftime("%B %d, %Y at %H:%M %z").replace(" 0", " "))

    @staticmethod
    def _value(value: Any, unit: str | None = None) -> str:
        if value is None:
            return '<span class="viewer-unavailable unavailable">Unavailable</span>'
        if isinstance(value, float):
            rendered = f"{value:,.2f}".rstrip("0").rstrip(".")
        elif isinstance(value, int):
            rendered = f"{value:,}"
        else:
            rendered = str(value)
        unit_html = (
            f' <span class="viewer-metric-unit">{escape(unit)}</span>' if unit is not None else ""
        )
        return f"{escape(rendered)}{unit_html}"
