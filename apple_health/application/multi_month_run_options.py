from dataclasses import dataclass
from pathlib import Path

from apple_health.application.report_period import ReportPeriod


@dataclass(frozen=True, slots=True)
class MultiMonthRunOptions:
    archive_path: Path
    periods: tuple[ReportPeriod, ...]
    config_path: Path | None
    apple_watch_source: str | None = None
    apple_health_app_source: str | None = None