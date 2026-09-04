from dataclasses import dataclass, field

from health_analyzer.config.sleep_config import SleepConfig
from health_analyzer.config.source_config import SourceConfig


@dataclass(slots=True)
class AppConfig:
    source: SourceConfig = field(default_factory=SourceConfig)
    sleep: SleepConfig = field(default_factory=SleepConfig)

    def validate(self) -> None:
        self.source.validate()
        self.sleep.validate()
