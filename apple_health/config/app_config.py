from dataclasses import dataclass, field

from apple_health.config.analysis_config import AnalysisConfig
from apple_health.config.source_config import SourceConfig
from apple_health.providers.apple.config import AppleProviderConfig


@dataclass(slots=True)
class AppConfig:
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    provider: AppleProviderConfig = field(default_factory=AppleProviderConfig)

    def __init__(
        self,
        source: SourceConfig | None = None,
        sleep=None,
        *,
        analysis: AnalysisConfig | None = None,
        provider: AppleProviderConfig | None = None,
    ) -> None:
        self.analysis = (
            analysis or AnalysisConfig(sleep=sleep)
            if sleep is not None
            else analysis or AnalysisConfig()
        )
        self.provider = (
            provider or AppleProviderConfig(source=source)
            if source is not None
            else provider or AppleProviderConfig()
        )

    @property
    def source(self) -> SourceConfig:
        """Compatibility access to the Apple provider configuration."""
        return self.provider.source

    @property
    def sleep(self):
        """Compatibility access to the shared analysis configuration."""
        return self.analysis.sleep

    def validate(self) -> None:
        self.provider.validate()
        self.analysis.sleep.validate()
