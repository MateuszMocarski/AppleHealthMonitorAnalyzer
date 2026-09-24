from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresentationContext:
    """Immutable supplied presentation values; never calculation input."""

    report_title: str
