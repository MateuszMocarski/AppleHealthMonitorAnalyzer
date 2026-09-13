from dataclasses import dataclass, field

from apple_health.application.monthly_reports import (
    MonthlyReports,
)
from apple_health.config.app_config import AppConfig


@dataclass(frozen=True)
class ReportGenerationTimings:
    archive_open_seconds: float = 0.0
    xml_parse_seconds: float = 0.0
    report_render_seconds: float = 0.0


@dataclass(frozen=True)
class ReportGenerationResult:
    reports: tuple[MonthlyReports, ...]
    effective_config: AppConfig

    timings: ReportGenerationTimings = field(
        default_factory=ReportGenerationTimings,
    )
