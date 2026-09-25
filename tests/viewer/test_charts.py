import re

from connected_health.viewer.charts import (
    ChartDatum,
    bar_chart,
    diverging_bar_chart,
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
    assert html.count("M110.00,110.00 L") == 2
    assert html.count('Z"></path>') == 2
    assert html.count("M110.00,110.00 L") == html.count('Z"></path>')
    assert "viewer-chart-donut-track" not in html
    assert "Core &lt;sleep&gt;" in html
    assert "NaN" not in html
    assert "Infinity" not in html


def test_one_slice_pie_is_a_filled_circle_without_a_hole() -> None:
    html = pie_chart("Sleep stages", (ChartDatum("Core", 90),), "minutes")

    assert '<circle cx="110.00" cy="110.00" r="94.00"></circle>' in html
    assert 'class="viewer-chart-slice' in html
    assert 'stroke="none"' in html
    assert "stroke-dasharray" not in html


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

    assert "0–100 points" not in html
    for tick in ("0", "25", "50", "75", "100"):
        assert f">{tick}</text>" in html
    assert html.count('class="viewer-chart-gridline"') == 5
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


def test_line_chart_emits_numeric_intermediate_ticks_gridlines_and_unfilled_path() -> None:
    html = line_chart(
        "Daily steps",
        tuple(ChartDatum(f"Aug {day}", day * 1000) for day in range(1, 5)),
        "steps",
        start_at_zero=True,
    )

    for tick in ("0", "1,000", "2,000", "3,000", "4,000"):
        assert f">{tick}</text>" in html
    assert html.count('class="viewer-chart-gridline"') == 5
    assert '<path class="viewer-chart-line" fill="none"' in html
    assert "<polygon" not in html
    assert "<path" in html


def test_diverging_bar_chart_has_a_zero_baseline_and_both_directions() -> None:
    html = diverging_bar_chart(
        "Daily calorie balance",
        (ChartDatum("Aug 1", -500), ChartDatum("Aug 2", 300), ChartDatum("Aug 3", 0)),
        "kcal",
    )

    assert 'class="viewer-chart-zero-line"' in html
    assert "viewer-chart-diverging-bar--negative" in html
    assert "viewer-chart-diverging-bar--positive" in html
    assert 'class="viewer-chart-zero-line"' in html
    assert html.count('class="viewer-chart-gridline"') >= 3
    assert ">0</text>" in html
    assert "NaN" not in html
    assert "Infinity" not in html


def test_dense_diverging_bar_chart_uses_thinner_bars_without_dropping_days() -> None:
    html = diverging_bar_chart(
        "Daily calorie balance",
        tuple(ChartDatum(f"Aug {day}", float(day if day % 2 else -day)) for day in range(1, 32)),
        "kcal",
    )

    widths = re.findall(r'width="([0-9.]+)" height="', html)

    assert len(widths) == 31
    assert all(float(width) < 12 for width in widths)
    assert html.count('class="viewer-chart-diverging-bar ') == 31


def test_long_daily_axes_thin_labels_without_dropping_plotted_values() -> None:
    values = tuple(ChartDatum(f"Aug {day}", float(day)) for day in range(1, 32))

    line = line_chart("Protein by day", values, "g")
    distance = line_chart("Daily distance", values, "km", start_at_zero=True)
    diverging = diverging_bar_chart("Calorie balance", values, "kcal")

    for chart in (line, distance, diverging):
        assert chart.count("viewer-chart-x-axis-label") == 7
        assert ">Aug 1</text>" in chart
        assert ">Aug 31</text>" in chart

    assert line.count('class="viewer-chart-point"') == 31
    assert distance.count('class="viewer-chart-point"') == 31
    assert diverging.count('class="viewer-chart-diverging-bar ') == 31


def test_time_axis_has_formatted_intermediate_clock_ticks() -> None:
    html = line_chart(
        "Bedtime by day",
        (ChartDatum("Aug 1", 1380), ChartDatum("Aug 2", 1500)),
        "",
        axis_formatter=_clock_label,
    )

    assert ">23:00</text>" in html
    assert any(f">{hour:02d}:" in html for hour in range(0, 24))
    assert "1500" not in html
    assert "25:00" not in html


def test_short_daily_axes_keep_every_label() -> None:
    html = diverging_bar_chart(
        "Calorie balance",
        (ChartDatum("Aug 1", -100), ChartDatum("Aug 2", 0), ChartDatum("Aug 3", 100)),
        "kcal",
    )

    assert html.count("viewer-chart-x-axis-label") == 3


def test_long_daily_steps_and_distance_charts_keep_independent_values_and_lines() -> None:
    values = tuple(ChartDatum(f"Aug {day}", day * 1000) for day in range(1, 32))

    steps = line_chart("Daily steps", values, "steps", start_at_zero=True)
    distance = line_chart("Daily distance", values, "km", start_at_zero=True)

    assert "Daily steps" in steps and "Daily distance" in distance
    assert steps.count('class="viewer-chart-point"') == 31
    assert distance.count('class="viewer-chart-point"') == 31
    assert steps.count('class="viewer-chart-line" fill="none"') == 1
    assert distance.count('class="viewer-chart-line" fill="none"') == 1
    assert "<polygon" not in steps + distance
