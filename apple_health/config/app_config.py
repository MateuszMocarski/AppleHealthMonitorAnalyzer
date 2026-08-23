from dataclasses import dataclass, field

from apple_health.config.sleep_score_config import SleepScoreConfig
from apple_health.config.source_config import SourceConfig


@dataclass(slots=True)
class AppConfig:
    source: SourceConfig = field(default_factory=SourceConfig)
    sleep_score: SleepScoreConfig = field(default_factory=SleepScoreConfig)
