from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
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
MAX_REPORT_PERIODS = 120

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


@app.get(
    "/favicon.svg",
    include_in_schema=False,
)
def favicon() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "web" / "favicon.svg",
        media_type="image/svg+xml",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports/generate", response_model=MultiMonthReportResponse)
def generate_report(
    response: Response,
    archive: UploadFile = File(),
    periods: str = Form(),
) -> MultiMonthReportResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        with NamedTemporaryFile(suffix=".zip") as temporary_archive:
            _copy_upload_to_file(
                archive,
                temporary_archive,
            )
            temporary_archive.flush()

            try:
                parsed_periods = tuple(
                    ReportPeriod.from_string(period.strip()) for period in periods.split(",")
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid reporting period.",
                ) from exc
            if len(parsed_periods) > MAX_REPORT_PERIODS:
                raise HTTPException(
                    status_code=422,
                    detail="Too many reporting periods requested.",
                )
                
            if len(parsed_periods) != len(set(parsed_periods)):
                raise HTTPException(
                    status_code=422,
                    detail="Duplicate reporting periods are not allowed.",
                )

            options = MultiMonthRunOptions(
                archive_path=Path(temporary_archive.name),
                periods=parsed_periods,
                config_path=None,
            )

            try:
                reports = AppleHealthApplication().generate_reports(
                    options,
                )
            except BadZipFile as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid Apple Health export archive.",
                ) from exc
            except ParseError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid Apple Health export XML.",
                ) from exc
            except ValueError as exc:
                if str(exc) == "Expected Apple HealthData root element.":
                    raise HTTPException(
                        status_code=422,
                        detail="Invalid Apple Health export XML.",
                    ) from exc

                raise
            except RuntimeError as exc:
                message = str(exc)
                
                if message == "Apple Health export XML is too large.":
                    raise HTTPException(
                        status_code=413,
                        detail="Apple Health export XML is too large.",
                    ) from exc
                    
                if message == "Expected exactly one export XML, found 0.":
                    raise HTTPException(
                        status_code=422,
                        detail="Apple Health export XML not found in archive.",
                    ) from exc

                if message.startswith("Expected exactly one export XML, found "):
                    raise HTTPException(
                        status_code=422,
                        detail="Archive contains multiple Apple Health export XML files.",
                    ) from exc

                raise

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
    finally:
        archive.file.close()
