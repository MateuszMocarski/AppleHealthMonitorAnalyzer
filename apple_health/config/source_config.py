from dataclasses import dataclass


@dataclass(slots=True)
class SourceConfig:
    apple_watch_source: str = "Apple\xa0Watch"
    apple_health_app_source: str = "Zdrowie"

    def validate(self) -> None:
        if not self.apple_watch_source.strip():
            raise ValueError(
                "Apple Watch source cannot be empty.",
            )

        if not self.apple_health_app_source.strip():
            raise ValueError(
                "Apple Health app source cannot be empty.",
            )
