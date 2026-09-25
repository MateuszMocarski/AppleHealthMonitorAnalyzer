"""Provider-neutral SVG presentation primitives for validated Viewer values."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class ChartDatum:
    """One already-validated presentation value; ``None`` remains missing."""

    label: str
    value: float | None


def pie_chart(title: str, values: Sequence[ChartDatum], unit: str) -> str:
    """Render a proportional pie without inventing slices for missing values."""
    drawable = [(item, _finite(item.value)) for item in values]
    drawable = [(item, value) for item, value in drawable if value is not None and value > 0]
    total = sum(value for _, value in drawable)
    if total <= 0:
        return empty_chart(title, "Unavailable: no positive values are available to chart.")

    center = 110.0
    radius = 94.0
    first_angle = -math.pi / 2
    angle = first_angle
    slices: list[str] = []
    for index, (item, value) in enumerate(drawable):
        sweep = 2 * math.pi * value / total
        end_angle = first_angle + 2 * math.pi if index == len(drawable) - 1 else angle + sweep
        start_x = center + radius * math.cos(angle)
        start_y = center + radius * math.sin(angle)
        end_x = center + radius * math.cos(end_angle)
        end_y = center + radius * math.sin(end_angle)
        if len(drawable) == 1:
            shape = f'<circle cx="{center:.2f}" cy="{center:.2f}" r="{radius:.2f}"></circle>'
        else:
            large_arc = 1 if sweep > math.pi else 0
            shape = (
                f'<path d="M{center:.2f},{center:.2f} '
                f"L{start_x:.2f},{start_y:.2f} "
                f"A{radius:.2f},{radius:.2f} 0 {large_arc} 1 "
                f'{end_x:.2f},{end_y:.2f} Z"></path>'
            )
        slices.append(
            f'<g class="viewer-chart-slice viewer-chart-slice--{index % 6}" stroke="none">'
            f"<title>{escape(item.label)}: {_format(value)} {escape(unit)}</title>"
            f"{shape}</g>"
        )
        angle = end_angle

    legend = "".join(
        '<li><span class="viewer-chart-swatch '
        f'viewer-chart-swatch--{index % 6}"></span>'
        f'<span class="viewer-chart-legend-label">{escape(item.label)}</span>'
        f'<span class="viewer-chart-legend-value">{_format(value)} {escape(unit)}</span></li>'
        for index, (item, value) in enumerate(drawable)
    )
    description = f"{title}. Total plotted value: {_format(total)} {unit}."
    return _figure(
        title,
        "pie",
        description,
        '<svg class="viewer-chart-svg viewer-chart-svg--pie" role="img" viewBox="0 0 220 220">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        f"{''.join(slices)}</svg>"
        f'<ul class="viewer-chart-legend">{legend}</ul>',
    )


def bar_chart(
    title: str,
    values: Sequence[ChartDatum],
    unit: str,
    *,
    maximum: float | None = None,
) -> str:
    """Render one-value bars, optionally against a fixed presentation maximum."""
    plotted = [(item, _finite(item.value)) for item in values]
    plotted = [(item, value) for item, value in plotted if value is not None]
    if not plotted:
        return ""
    chart_maximum = (
        maximum if maximum is not None else _nice_ceiling(max(value for _, value in plotted))
    )
    if chart_maximum <= 0:
        chart_maximum = 1.0
    ticks = _fixed_scale_ticks(chart_maximum)
    left, right, top, bottom = 46.0, 402.0, 34.0, 204.0
    width = (right - left) / max(len(plotted), 1)
    bars = []
    for index, (item, value) in enumerate(plotted):
        height = max(0.0, min(value, chart_maximum)) / chart_maximum * (bottom - top)
        x = left + index * width + width * 0.18
        bar_width = width * 0.64
        y = bottom - height
        bars.append(
            f'<rect class="viewer-chart-bar viewer-chart-bar--{index % 6}" x="{x:.2f}" '
            f'y="{y:.2f}" width="{bar_width:.2f}" height="{height:.2f}">'
            f"<title>{escape(item.label)}: {_format(value)} {escape(unit)}</title></rect>"
            '<text class="viewer-chart-axis-label" '
            f'x="{x + bar_width / 2:.2f}" y="230">{escape(item.label)}</text>'
        )
    grid = _horizontal_axis(ticks, 0.0, chart_maximum, top, bottom, left, right)
    description = f"{title}; fixed scale from 0 to {_format(chart_maximum)} {unit}."
    return _figure(
        title,
        "bar",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 420 250">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        f'<text class="viewer-chart-unit-label" x="{left}" y="20">{escape(unit)}</text>'
        f'{grid}<line class="viewer-chart-axis" x1="{left}" y1="{bottom}" '
        f'x2="{right}" y2="{bottom}"></line>{"".join(bars)}</svg>',
    )


def line_chart(
    title: str,
    values: Sequence[ChartDatum],
    unit: str,
    *,
    start_at_zero: bool = False,
    axis_label: str | None = None,
    axis_formatter: Callable[[float], str] | None = None,
    value_formatter: Callable[[float], str] | None = None,
) -> str:
    """Render a single series, retaining missing values as breaks in the path."""
    points = [(item.label, _finite(item.value)) for item in values]
    present = [value for _, value in points if value is not None]
    if not present:
        return ""
    if start_at_zero:
        lower = 0.0
        upper = max(_nice_ceiling(max(present)), 1.0)
    else:
        lower, upper, _ = _numeric_axis_bounds(min(present), max(present))
    return _line_figure(
        title,
        points,
        unit,
        lower,
        upper,
        axis_label or unit,
        axis_formatter or _format,
        value_formatter or _format,
        time_axis=axis_formatter is not None,
    )


def diverging_bar_chart(title: str, values: Sequence[ChartDatum], unit: str) -> str:
    """Render a zero-baseline bar chart for positive and negative persisted values."""
    plotted = [(item, _finite(item.value)) for item in values]
    if not any(value is not None for _, value in plotted):
        return ""
    maximum_value = max((abs(value) for _, value in plotted if value is not None), default=0.0)
    ticks = _symmetric_ticks(maximum_value)
    maximum = max(abs(ticks[0]), abs(ticks[-1]))
    x_positions = _x_positions(len(plotted), 32.0, 288.0)
    top, bottom = 34.0, 186.0
    center = (top + bottom) / 2
    bars = []
    for index, ((item, value), x) in enumerate(zip(plotted, x_positions, strict=True)):
        if value is None:
            continue
        height = abs(value) / maximum * (bottom - top) / 2
        y = center - height if value >= 0 else center
        bars.append(
            '<rect class="viewer-chart-diverging-bar '
            f'viewer-chart-diverging-bar--{"positive" if value >= 0 else "negative"}" '
            f'x="{x - 6:.2f}" y="{y:.2f}" width="12" height="{height:.2f}">'
            f"<title>{escape(item.label)}: {_format(value)} {escape(unit)}</title></rect>"
        )
    labels = _x_labels([item.label for item, _ in plotted], x_positions, y=232.0)
    grid = _horizontal_axis(ticks, -maximum, maximum, top, bottom, 32.0, 288.0)
    description = f"{title}; zero baseline separates deficit and surplus."
    return _figure(
        title,
        "diverging-bar",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 320 244">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        f'<text class="viewer-chart-unit-label" x="32" y="20">{escape(unit)}</text>'
        f'{grid}<line class="viewer-chart-zero-line" x1="32" y1="{center:.2f}" '
        f'x2="288" y2="{center:.2f}"></line>{"".join(bars)}{labels}</svg>',
    )


def empty_chart(title: str, message: str) -> str:
    """Return a controlled state instead of invalid or invented SVG geometry."""
    return (
        '<figure class="viewer-chart viewer-chart--empty">'
        f"<figcaption>{escape(title)}</figcaption>"
        f'<p class="viewer-chart-empty">{escape(message)}</p></figure>'
    )


def _line_figure(
    title: str,
    points: Sequence[tuple[str, float | None]],
    unit: str,
    lower: float,
    upper: float,
    axis_label: str,
    axis_formatter: Callable[[float], str],
    value_formatter: Callable[[float], str],
    *,
    time_axis: bool,
) -> str:
    x_left, x_right = 48.0, 288.0
    top, bottom = 34.0, 134.0
    x_positions = _x_positions(len(points), x_left, x_right)
    ticks = _axis_ticks(lower, upper, step_override=60.0 if time_axis else None)
    lower, upper = ticks[0], ticks[-1]
    path = _line_path([value for _, value in points], x_positions, lower, upper, top, bottom)
    dots = "".join(
        '<circle class="viewer-chart-point" '
        f'cx="{x:.2f}" cy="{_y(value, lower, upper, top, bottom):.2f}" r="3">'
        f"<title>{escape(label)}: {escape(value_formatter(value))}{_unit_suffix(unit)}</title>"
        "</circle>"
        for (label, value), x in zip(points, x_positions, strict=True)
        if value is not None
    )
    labels = _x_labels([label for label, _ in points], x_positions)
    description = f"{title}; values are shown only for days with persisted data."
    grid = _horizontal_axis(ticks, lower, upper, top, bottom, x_left, x_right, axis_formatter)
    return _figure(
        title,
        "line",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 320 184">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        f'<text class="viewer-chart-unit-label" x="{x_left}" y="20">{escape(axis_label)}</text>'
        f'{grid}<line class="viewer-chart-axis" x1="{x_left}" y1="{bottom}" '
        f'x2="{x_right}" y2="{bottom}"></line>'
        f'<path class="viewer-chart-line" fill="none" d="{path}"></path>{dots}{labels}</svg>',
    )


def _figure(title: str, modifier: str, description: str, content: str) -> str:
    return (
        f'<figure class="viewer-chart viewer-chart--{escape(modifier)}">'
        f"<figcaption>{escape(title)}</figcaption>{content}</figure>"
    )


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except OverflowError, ValueError:
        return None
    return numeric if math.isfinite(numeric) else None


def _format(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _x_positions(length: int, start: float = 32.0, end: float = 268.0) -> list[float]:
    if length <= 1:
        return [(start + end) / 2] * length
    return [start + index * (end - start) / (length - 1) for index in range(length)]


def _y(value: float, lower: float, upper: float, top: float, bottom: float) -> float:
    return bottom - (value - lower) / (upper - lower) * (bottom - top)


def _line_path(
    values: Sequence[float | None],
    x_positions: Sequence[float],
    lower: float,
    upper: float,
    top: float,
    bottom: float,
) -> str:
    commands: list[str] = []
    needs_move = True
    for value, x in zip(values, x_positions, strict=True):
        if value is None:
            needs_move = True
            continue
        command = "M" if needs_move else "L"
        commands.append(f"{command}{x:.2f},{_y(value, lower, upper, top, bottom):.2f}")
        needs_move = False
    return " ".join(commands)


def _x_labels(labels: Iterable[str], x_positions: Sequence[float], *, y: float = 178.0) -> str:
    tick_indexes = _x_tick_indexes(len(x_positions))
    return "".join(
        '<text class="viewer-chart-axis-label viewer-chart-x-axis-label" '
        f'x="{x_positions[index]:.2f}" y="{y:.2f}">{escape(label)}</text>'
        for index, label in enumerate(labels)
        if index in tick_indexes
    )


def _x_tick_indexes(length: int, maximum_ticks: int = 7) -> set[int]:
    """Keep chart geometry intact while making long daily axes readable."""
    if length <= maximum_ticks:
        return set(range(length))
    return {round(index * (length - 1) / (maximum_ticks - 1)) for index in range(maximum_ticks)}


def _axis_ticks(
    lower: float,
    upper: float,
    target_count: int = 5,
    *,
    step_override: float | None = None,
) -> list[float]:
    if upper <= lower:
        padding = abs(lower) * 0.05 or 1.0
        lower -= padding
        upper += padding
    step = step_override or _nice_step((upper - lower) / (target_count - 1))
    first = math.floor(lower / step) * step
    last = math.ceil(upper / step) * step
    count = max(1, min(20, round((last - first) / step)))
    return [first + index * step for index in range(count + 1)]


def _numeric_axis_bounds(lower: float, upper: float) -> tuple[float, float, list[float]]:
    ticks = _axis_ticks(lower, upper)
    return ticks[0], ticks[-1], ticks


def _fixed_scale_ticks(maximum: float) -> list[float]:
    if maximum == 100:
        return [0.0, 25.0, 50.0, 75.0, 100.0]
    return _axis_ticks(0.0, maximum)


def _symmetric_ticks(maximum: float) -> list[float]:
    step = _nice_step(maximum / 2) if maximum > 0 else 1.0
    count = max(1, min(10, math.ceil(maximum / step)))
    return [index * step for index in range(-count, count + 1)]


def _horizontal_axis(
    ticks: Sequence[float],
    lower: float,
    upper: float,
    top: float,
    bottom: float,
    x_left: float,
    x_right: float,
    formatter: Callable[[float], str] | None = None,
) -> str:
    label_formatter = formatter or _format
    elements: list[str] = []
    for tick in ticks:
        y = _y(tick, lower, upper, top, bottom)
        elements.append(
            '<line class="viewer-chart-gridline" '
            f'x1="{x_left:.2f}" y1="{y:.2f}" x2="{x_right:.2f}" y2="{y:.2f}"></line>'
        )
        elements.append(
            '<text class="viewer-chart-axis-label viewer-chart-y-axis-label" '
            f'x="{x_left - 7:.2f}" y="{y + 3:.2f}">{escape(label_formatter(tick))}</text>'
        )
    return "".join(elements)


def _nice_step(raw_step: float) -> float:
    if not math.isfinite(raw_step) or raw_step <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw_step))
    fraction = raw_step / magnitude
    nice_fraction = next(
        (candidate for candidate in (1.0, 2.0, 2.5, 5.0, 10.0) if fraction <= candidate),
        10.0,
    )
    return nice_fraction * magnitude


def _nice_ceiling(value: float) -> float:
    if value <= 0:
        return 1.0
    step = _nice_step(value / 5)
    return math.ceil(value / step) * step


def _unit_suffix(unit: str) -> str:
    return f" {escape(unit)}" if unit else ""
