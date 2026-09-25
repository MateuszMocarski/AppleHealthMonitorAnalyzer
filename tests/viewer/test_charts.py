from connected_health.viewer.charts import (
    ChartDatum,
    bar_chart,
    diverging_bar_chart,
    donut_chart,
    dual_axis_line_chart,
    line_chart,
)


def test_donut_chart_renders_valid_accessible_slices_and_escapes_labels() -> None:
    html = donut_chart(
        "Sleep stages",
        (ChartDatum("Core <sleep>", 300), ChartDatum("REM", 90)),
        "minutes",
    )

    assert '<figure class="viewer-chart viewer-chart--donut">' in html
    assert '<svg class="viewer-chart-svg" role="img"' in html
    assert html.count('class="viewer-chart-slice') == 2
    assert "Core &lt;sleep&gt;" in html
    assert "NaN" not in html
    assert "Infinity" not in html


def test_zero_total_donut_is_a_controlled_empty_state() -> None:
    html = donut_chart(
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
