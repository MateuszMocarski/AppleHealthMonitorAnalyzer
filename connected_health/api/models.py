from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MonthlyReportResponse(BaseModel):
    year: int
    month: int
    full_text: str | None
    full_json: str | None
    summary_text: str | None
    summary_json: str | None
    generation_id: str
    generated_at: datetime


class MultiMonthReportResponse(BaseModel):
    reports: list[MonthlyReportResponse]


class ViewerReportArtifactResponse(BaseModel):
    file_id: str
    period: str
    kind: Literal["full", "summary"]
    generation_id: str
    generated_at: str


class ViewerReportIndexResponse(BaseModel):
    artifacts: list[ViewerReportArtifactResponse]
