from dataclasses import dataclass, field

from apple_health.config.source_config import SourceConfig

AppleSourceConfig = SourceConfig


@dataclass(slots=True)
class AppleProviderConfig:
    """Apple input-selection policy, kept above canonical HealthData."""

    source: AppleSourceConfig = field(default_factory=AppleSourceConfig)

    def validate(self) -> None:
        self.source.validate()
