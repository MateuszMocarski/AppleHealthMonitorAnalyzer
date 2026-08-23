from dataclasses import dataclass


@dataclass(slots=True)
class SourceConfig:
    apple_watch_source: str = "Apple\xa0Watch"
    apple_health_app_source: str = "Zdrowie"