from dataclasses import dataclass, field

from apple_health.config.sleep_config import SleepConfig
from apple_health.config.source_config import SourceConfig


@dataclass(slots=True)
class AppConfig:
    source: SourceConfig = field(default_factory=SourceConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)

    def validate(self) -> None:
        self.source.validate()
        self.sleep.validate()
