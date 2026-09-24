from dataclasses import dataclass, field

from apple_health.config.sleep_config import SleepConfig


@dataclass(slots=True)
class AnalysisConfig:
    """Configuration consumed by provider-neutral analysis code."""

    sleep: SleepConfig = field(default_factory=SleepConfig)
