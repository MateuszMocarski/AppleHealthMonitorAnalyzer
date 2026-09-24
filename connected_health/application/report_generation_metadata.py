from dataclasses import dataclass
from datetime import datetime

from connected_health.application.report_period import ReportPeriod


@dataclass(frozen=True, slots=True)
class ReportGenerationMetadata:
    period: ReportPeriod
    generation_id: str
    generated_at: datetime

    def month_app_properties(self) -> dict[str, str]:
        return {
            "ahm_type": "report_month",
            "ahm_period": self._period_value(),
        }

    def artifact_app_properties(self) -> dict[str, str]:
        return {
            "ahm_type": "report_artifact",
            "ahm_period": self._period_value(),
            "ahm_generation_id": self.generation_id,
            "ahm_generated_at": (self.generated_at.isoformat().replace("+00:00", "Z")),
        }

    def _period_value(self) -> str:
        return f"{self.period.year}-" f"{self.period.month:02d}"
