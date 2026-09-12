from datetime import datetime

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
