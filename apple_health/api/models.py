from pydantic import BaseModel


class ReportResponse(BaseModel):
    year: int
    month: int
    content: str