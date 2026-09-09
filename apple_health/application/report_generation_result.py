from dataclasses import dataclass

from apple_health.application.monthly_reports import MonthlyReports
from apple_health.config.app_config import AppConfig


@dataclass(frozen=True)
class ReportGenerationResult:
    reports: tuple[MonthlyReports, ...]
    effective_config: AppConfig
