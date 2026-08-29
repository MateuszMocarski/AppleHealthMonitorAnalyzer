from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from apple_health.api.models import (
    MonthlyReportResponse,
    MultiMonthReportResponse,
)
from apple_health.application.application import AppleHealthApplication
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_period import ReportPeriod

MAX_UPLOAD_SIZE = 1024 * 1024 * 1024  # 1 GB
UPLOAD_CHUNK_SIZE = 1024 * 1024

app = FastAPI(
    title="Apple Health Monitor Analyzer",
    version="0.1.0",
)


def _copy_upload_to_file(
    archive: UploadFile,
    destination,
) -> None:
    total_size = 0

    while chunk := archive.file.read(
        UPLOAD_CHUNK_SIZE,
    ):
        total_size += len(chunk)

        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Uploaded archive is too large.",
            )

        destination.write(chunk)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "web" / "index.html",
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
        _copy_upload_to_file(
            archive,
            temporary_archive,
        )
        temporary_archive.flush()

        try:
            parsed_periods = tuple(
                ReportPeriod.from_string(period) for period in periods.split(",")
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid reporting period.",
            ) from exc

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
