from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, UploadFile

from apple_health.api.models import (
    MonthlyReportResponse,
    MultiMonthReportResponse,
)
from apple_health.application.application import AppleHealthApplication
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_period import ReportPeriod

app = FastAPI(
    title="Apple Health Monitor Analyzer",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports/generate", response_model=MultiMonthReportResponse)
def generate_report(
    archive: UploadFile = File(),
    periods: str = Form(),
) -> MultiMonthReportResponse:
    with NamedTemporaryFile(suffix=".zip") as temporary_archive:
        temporary_archive.write(archive.file.read())
        temporary_archive.flush()

        parsed_periods = tuple(
            ReportPeriod(
                year=int(period.split("-")[0]),
                month=int(period.split("-")[1]),
            )
            for period in periods.split(",")
        )

        options = MultiMonthRunOptions(
            archive_path=Path(temporary_archive.name),
            periods=parsed_periods,
            config_path=None,
        )

        reports = AppleHealthApplication().generate_reports(options)

    return MultiMonthReportResponse(
        reports=[
            MonthlyReportResponse(
                year=report.period.year,
                month=report.period.month,
                full_text=report.full_text,
                full_json=report.full_json,
                summary_text=report.summary_text,
                summary_json=report.summary_json,
            )
            for report in reports
        ]
    )
