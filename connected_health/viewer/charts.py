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


def donut_chart(title: str, values: Sequence[ChartDatum], unit: str) -> str:
    """Render a proportional donut without inventing slices for missing values."""
    drawable = [(item, _finite(item.value)) for item in values]
    drawable = [(item, value) for item, value in drawable if value is not None and value > 0]
    total = sum(value for _, value in drawable)
    if total <= 0:
        return empty_chart(title, "Unavailable: no positive values are available to chart.")

    circumference = 2 * math.pi * 36
    offset = 0.0
    slices: list[str] = []
    for index, (item, value) in enumerate(drawable):
        arc = circumference * value / total
        slices.append(
            '<circle class="viewer-chart-slice '
            f'viewer-chart-slice--{index % 6}" cx="60" cy="60" r="36" fill="none" '
            f'stroke-dasharray="{arc:.3f} {circumference - arc:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" transform="rotate(-90 60 60)">'
            f"<title>{escape(item.label)}: {_format(value)} {escape(unit)}</title></circle>"
        )
        offset += arc

    legend = "".join(
        '<li><span class="viewer-chart-swatch '
        f'viewer-chart-swatch--{index % 6}"></span>{escape(item.label)} '
        f"<span>{_format(value)} {escape(unit)}</span></li>"
        for index, (item, value) in enumerate(drawable)
    )
    description = f"{title}. Total plotted value: {_format(total)} {unit}."
    return _figure(
        title,
        "donut",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 120 120">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        '<circle class="viewer-chart-donut-track" cx="60" cy="60" r="36" fill="none"></circle>'
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
    chart_maximum = maximum if maximum is not None else max(value for _, value in plotted)
    if chart_maximum <= 0:
        chart_maximum = 1.0
    width = 220 / max(len(plotted), 1)
    bars = []
    for index, (item, value) in enumerate(plotted):
        height = max(0.0, min(value, chart_maximum)) / chart_maximum * 84
        x = 28 + index * width + 5
        y = 104 - height
        bars.append(
            f'<rect class="viewer-chart-bar viewer-chart-bar--{index % 6}" x="{x:.2f}" '
            f'y="{y:.2f}" width="{max(width - 10, 3):.2f}" height="{height:.2f}">'
            f"<title>{escape(item.label)}: {_format(value)} {escape(unit)}</title></rect>"
            '<text class="viewer-chart-axis-label" '
            f'x="{x + max(width - 10, 3) / 2:.2f}" y="124">{escape(item.label)}</text>'
        )
    scale = f"0–{_format(chart_maximum)} {unit}"
    description = f"{title}; scale {scale}."
    return _figure(
        title,
        "bar",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 260 136">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        '<line class="viewer-chart-axis" x1="28" y1="104" x2="248" y2="104"></line>'
        '<text class="viewer-chart-axis-label" x="4" y="18">%s</text>'
        '<text class="viewer-chart-axis-label" x="8" y="108">0</text>%s</svg>'
        % (escape(scale), "".join(bars)),
    )


def line_chart(
    title: str,
    values: Sequence[ChartDatum],
    unit: str,
    *,
    start_at_zero: bool = False,
    axis_label: str | None = None,
    axis_formatter: Callable[[float], str] | None = None,
) -> str:
    """Render a single series, retaining missing values as breaks in the path."""
    points = [(item.label, _finite(item.value)) for item in values]
    present = [value for _, value in points if value is not None]
    if not present:
        return ""
    lower = 0.0 if start_at_zero else min(present)
    upper = max(present)
    if upper <= lower:
        upper = lower + 1.0
    return _line_figure(
        title,
        points,
        unit,
        lower,
        upper,
        axis_label or unit,
        axis_formatter or _format,
    )


def dual_axis_line_chart(
    title: str,
    labels: Sequence[str],
    left_values: Sequence[float | None],
    right_values: Sequence[float | None],
    *,
    left_label: str,
    right_label: str,
) -> str:
    """Render two independently zero-based daily series without correlating scales."""
    left = [_finite(value) for value in left_values]
    right = [_finite(value) for value in right_values]
    if not any(value is not None for value in left + right):
        return ""
    left_maximum = max((value for value in left if value is not None), default=0.0) or 1.0
    right_maximum = max((value for value in right if value is not None), default=0.0) or 1.0
    x_positions = _x_positions(len(labels))
    left_path = _line_path(left, x_positions, 0, left_maximum)
    right_path = _line_path(right, x_positions, 0, right_maximum)
    labels_svg = _x_labels(labels, x_positions)
    description = f"{title}. Left axis: {left_label}; right axis: {right_label}."
    paths = ""
    if left_path:
        paths += f'<path class="viewer-chart-line viewer-chart-line--left" d="{left_path}"></path>'
    if right_path:
        paths += (
            f'<path class="viewer-chart-line viewer-chart-line--right" d="{right_path}"></path>'
        )
    return _figure(
        title,
        "dual-line",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 300 154">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        '<line class="viewer-chart-axis" x1="32" y1="112" x2="268" y2="112"></line>'
        f'<text class="viewer-chart-axis-label" x="2" y="18">{escape(left_label)}</text>'
        f'<text class="viewer-chart-axis-label" x="218" y="18">{escape(right_label)}</text>'
        f'<text class="viewer-chart-axis-label" x="4" y="108">0</text>'
        f'<text class="viewer-chart-axis-label" x="4" y="32">{_format(left_maximum)}</text>'
        f'<text class="viewer-chart-axis-label" x="272" y="108">0</text>'
        f'<text class="viewer-chart-axis-label" x="272" y="32">{_format(right_maximum)}</text>'
        f"{paths}{labels_svg}</svg>",
    )


def diverging_bar_chart(title: str, values: Sequence[ChartDatum], unit: str) -> str:
    """Render a zero-baseline bar chart for positive and negative persisted values."""
    plotted = [(item, _finite(item.value)) for item in values]
    if not any(value is not None for _, value in plotted):
        return ""
    maximum = max((abs(value) for _, value in plotted if value is not None), default=0.0) or 1.0
    x_positions = _x_positions(len(plotted))
    bars = []
    for index, ((item, value), x) in enumerate(zip(plotted, x_positions, strict=True)):
        if value is None:
            continue
        height = abs(value) / maximum * 46
        y = 76 - height if value >= 0 else 76
        bars.append(
            '<rect class="viewer-chart-diverging-bar '
            f'viewer-chart-diverging-bar--{"positive" if value >= 0 else "negative"}" '
            f'x="{x - 6:.2f}" y="{y:.2f}" width="12" height="{height:.2f}">'
            f"<title>{escape(item.label)}: {_format(value)} {escape(unit)}</title></rect>"
        )
    labels = _x_labels([item.label for item, _ in plotted], x_positions)
    description = f"{title}; zero baseline separates deficit and surplus."
    return _figure(
        title,
        "diverging-bar",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 300 136">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        '<line class="viewer-chart-zero-line" x1="32" y1="76" x2="268" y2="76"></line>'
        f'<text class="viewer-chart-axis-label" x="2" y="18">{escape(unit)}</text>'
        f'<text class="viewer-chart-axis-label" x="4" y="72">0</text>{"".join(bars)}{labels}</svg>',
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
) -> str:
    x_positions = _x_positions(len(points))
    path = _line_path([value for _, value in points], x_positions, lower, upper)
    dots = "".join(
        '<circle class="viewer-chart-point" '
        f'cx="{x:.2f}" cy="{_y(value, lower, upper):.2f}" r="2.5">'
        f"<title>{escape(label)}: {_format(value)} {escape(unit)}</title></circle>"
        for (label, value), x in zip(points, x_positions, strict=True)
        if value is not None
    )
    labels = _x_labels([label for label, _ in points], x_positions)
    description = f"{title}; values are shown only for days with persisted data."
    return _figure(
        title,
        "line",
        description,
        '<svg class="viewer-chart-svg" role="img" viewBox="0 0 300 154">'
        f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
        '<line class="viewer-chart-axis" x1="32" y1="112" x2="268" y2="112"></line>'
        f'<text class="viewer-chart-axis-label" x="2" y="18">{escape(axis_label)}</text>'
        '<text class="viewer-chart-axis-label" x="4" y="108">'
        f"{escape(axis_formatter(lower))}</text>"
        '<text class="viewer-chart-axis-label" x="4" y="32">'
        f"{escape(axis_formatter(upper))}</text>"
        f'<path class="viewer-chart-line" d="{path}"></path>{dots}{labels}</svg>',
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


def _x_positions(length: int) -> list[float]:
    if length <= 1:
        return [150.0] * length
    return [32 + index * 236 / (length - 1) for index in range(length)]


def _y(value: float, lower: float, upper: float) -> float:
    return 112 - (value - lower) / (upper - lower) * 84


def _line_path(
    values: Sequence[float | None], x_positions: Sequence[float], lower: float, upper: float
) -> str:
    commands: list[str] = []
    needs_move = True
    for value, x in zip(values, x_positions, strict=True):
        if value is None:
            needs_move = True
            continue
        command = "M" if needs_move else "L"
        commands.append(f"{command}{x:.2f},{_y(value, lower, upper):.2f}")
        needs_move = False
    return " ".join(commands)


def _x_labels(labels: Iterable[str], x_positions: Sequence[float]) -> str:
    return "".join(
        f'<text class="viewer-chart-axis-label" x="{x:.2f}" y="132">{escape(label)}</text>'
        for label, x in zip(labels, x_positions, strict=True)
    )
