from dataclasses import dataclass

from health_analyzer.application.report_period import ReportPeriod


@dataclass(frozen=True, slots=True)
class MonthlyReports:
    period: ReportPeriod
    full_text: str
    full_json: str
    summary_text: str
    summary_json: str
