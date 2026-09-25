from connected_health.viewer.charts import (
    ChartDatum,
    bar_chart,
    diverging_bar_chart,
    dual_axis_line_chart,
    line_chart,
    pie_chart,
)


def _clock_label(value: float) -> str:
    minutes = int(value) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def test_pie_chart_renders_valid_accessible_slices_and_escapes_labels() -> None:
    html = pie_chart(
        "Sleep stages",
        (ChartDatum("Core <sleep>", 300), ChartDatum("REM", 90)),
        "minutes",
    )

    assert '<figure class="viewer-chart viewer-chart--pie">' in html
    assert '<svg class="viewer-chart-svg viewer-chart-svg--pie" role="img"' in html
    assert html.count('class="viewer-chart-slice') == 2
    assert " A94.00,94.00 " in html
    assert "viewer-chart-donut-track" not in html
    assert "Core &lt;sleep&gt;" in html
    assert "NaN" not in html
    assert "Infinity" not in html


def test_zero_total_pie_is_a_controlled_empty_state() -> None:
    html = pie_chart(
        "Workout duration",
        (ChartDatum("Walking", 0), ChartDatum("Cycling", None)),
        "minutes",
    )

    assert "viewer-chart--empty" in html
    assert "Unavailable" in html
    assert "viewer-chart-slice" not in html


def test_bar_chart_supports_a_fixed_scale() -> None:
    html = bar_chart(
        "Sleep Score components",
        (ChartDatum("Bedtime", 80), ChartDatum("Duration", 90)),
        "points",
        maximum=100,
    )

    assert "0–100 points" in html
    assert "Bedtime" in html
    assert "Duration" in html


def test_line_chart_leaves_missing_points_absent() -> None:
    html = line_chart(
        "Protein by day",
        (ChartDatum("Aug 1", 100), ChartDatum("Aug 2", None), ChartDatum("Aug 3", 120)),
        "g",
    )

    assert "Aug 2" in html
    assert "<title>Aug 2:" not in html
    assert html.count('class="viewer-chart-point"') == 2
    assert "NaN" not in html
    assert "Infinity" not in html


def test_line_chart_uses_an_optional_user_facing_value_formatter_for_point_titles() -> None:
    html = line_chart(
        "Bedtime by day",
        (ChartDatum("Aug 2", 1500),),
        "",
        axis_formatter=_clock_label,
        value_formatter=_clock_label,
    )

    assert "<title>Aug 2: 01:00</title>" in html
    assert "<title>Aug 2: 1500</title>" not in html


def test_dual_axis_chart_keeps_distinct_zero_based_axis_labels() -> None:
    html = dual_axis_line_chart(
        "Steps and distance",
        ("Aug 1", "Aug 2"),
        (1000, None),
        (1.5, 2.0),
        left_label="Steps",
        right_label="Distance (km)",
    )

    assert "Steps" in html
    assert "Distance (km)" in html
    assert 'class="viewer-chart-line viewer-chart-line--left"' in html
    assert 'class="viewer-chart-line viewer-chart-line--right"' in html
    assert "<title>Aug 1: Steps 1,000</title>" in html
    assert "<title>Aug 1: Distance (km) 1.5</title>" in html


def test_diverging_bar_chart_has_a_zero_baseline_and_both_directions() -> None:
    html = diverging_bar_chart(
        "Daily calorie balance",
        (ChartDatum("Aug 1", -500), ChartDatum("Aug 2", 300), ChartDatum("Aug 3", 0)),
        "kcal",
    )

    assert 'class="viewer-chart-zero-line"' in html
    assert "viewer-chart-diverging-bar--negative" in html
    assert "viewer-chart-diverging-bar--positive" in html
    assert "NaN" not in html
    assert "Infinity" not in html


def test_long_daily_axes_thin_labels_without_dropping_plotted_values() -> None:
    values = tuple(ChartDatum(f"Aug {day}", float(day)) for day in range(1, 32))

    line = line_chart("Protein by day", values, "g")
    dual = dual_axis_line_chart(
        "Steps and distance",
        tuple(item.label for item in values),
        tuple(item.value for item in values),
        tuple(item.value / 10 for item in values),
        left_label="Steps",
        right_label="Distance (km)",
    )
    diverging = diverging_bar_chart("Calorie balance", values, "kcal")

    for chart in (line, dual, diverging):
        assert chart.count("viewer-chart-x-axis-label") == 7
        assert ">Aug 1</text>" in chart
        assert ">Aug 31</text>" in chart

    assert line.count('class="viewer-chart-point"') == 31
    assert dual.count('class="viewer-chart-point ') == 62
    assert diverging.count('class="viewer-chart-diverging-bar ') == 31


def test_short_daily_axes_keep_every_label() -> None:
    html = diverging_bar_chart(
        "Calorie balance",
        (ChartDatum("Aug 1", -100), ChartDatum("Aug 2", 0), ChartDatum("Aug 3", 100)),
        "kcal",
    )

    assert html.count("viewer-chart-x-axis-label") == 3
