from dataclasses import dataclass

from connected_health.application.report_generation_metadata import (
    ReportGenerationMetadata,
)
from connected_health.application.report_period import ReportPeriod


@dataclass(frozen=True, slots=True)
class MonthlyReports:
    period: ReportPeriod
    full_text: str | None
    full_json: str | None
    summary_text: str | None
    summary_json: str | None
    metadata: ReportGenerationMetadata
