from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresentationContext:
    """Immutable supplied presentation values; never calculation input."""

    report_title: str


# Compatibility default for direct legacy renderer callers. Provider-facing
# orchestration always supplies a context from loaded provenance.
APPLE_PRESENTATION_CONTEXT = PresentationContext(report_title="Apple Health Monthly Report")
