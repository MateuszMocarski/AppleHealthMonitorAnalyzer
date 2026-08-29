from pydantic import BaseModel


class MonthlyReportResponse(BaseModel):
    year: int
    month: int
    full_text: str
    full_json: str
    summary_text: str
    summary_json: str


class MultiMonthReportResponse(BaseModel):
    reports: list[MonthlyReportResponse]
