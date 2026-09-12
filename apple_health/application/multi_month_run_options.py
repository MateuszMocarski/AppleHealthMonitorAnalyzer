from dataclasses import dataclass
from pathlib import Path

from apple_health.application.report_outputs import ReportOutputs
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig


@dataclass(frozen=True, slots=True)
class MultiMonthRunOptions:
    archive_path: Path
    periods: tuple[ReportPeriod, ...]
    config_path: Path | None
    selected_drive_config: AppConfig | None = None
    apple_watch_source: str | None = None
    apple_health_app_source: str | None = None
    outputs: ReportOutputs = ReportOutputs()
