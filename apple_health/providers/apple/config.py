from dataclasses import dataclass, field

DEFAULT_APPLE_WATCH_SOURCE = "Apple\xa0Watch"


@dataclass(slots=True)
class AppleSourceConfig:
    """Apple XML sourceName selection policy."""

    apple_watch_source: str = DEFAULT_APPLE_WATCH_SOURCE
    apple_health_app_source: str = "Zdrowie"

    def validate(self) -> None:
        if not self.apple_watch_source.strip():
            raise ValueError("Apple Watch source cannot be empty.")
        if not self.apple_health_app_source.strip():
            raise ValueError("Apple Health app source cannot be empty.")

    def matches_apple_watch_source(self, source_name: str) -> bool:
        if source_name == self.apple_watch_source:
            return True
        if self.apple_watch_source != DEFAULT_APPLE_WATCH_SOURCE:
            return False
        return source_name.startswith(f"{DEFAULT_APPLE_WATCH_SOURCE} (") and source_name.endswith(
            ")"
        )


@dataclass(slots=True)
class AppleProviderConfig:
    """Apple input-selection policy, kept above canonical HealthData."""

    source: AppleSourceConfig = field(default_factory=AppleSourceConfig)

    def validate(self) -> None:
        self.source.validate()
