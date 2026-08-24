from dataclasses import dataclass, field

from apple_health.config.sleep_score_config import SleepScoreConfig


@dataclass(slots=True)
class SleepConfig:
    session_gap_threshold_minutes: int = 30

    score: SleepScoreConfig = field(default_factory=SleepScoreConfig)

    def validate(self) -> None:
        if self.session_gap_threshold_minutes < 0:
            raise ValueError("Sleep session gap threshold cannot be negative.")

        self.score.validate()
