from contextlib import ExitStack
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
from apple_health.config.exceptions import ConfigurationError

MAX_UPLOAD_SIZE = 1024 * 1024 * 1024  # 1 GB
MAX_CONFIG_UPLOAD_SIZE = 1024 * 1024  # 1 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_REPORT_PERIODS = 120

app = FastAPI(
    title="Apple Health Monitor Analyzer",
    version="0.1.0",
)


def _copy_upload_to_file(
    upload: UploadFile,
    destination,
    *,
    max_size: int,
    too_large_detail: str,
) -> None:
    total_size = 0

    while chunk := upload.file.read(
        UPLOAD_CHUNK_SIZE,
    ):
        total_size += len(chunk)

        if total_size > max_size:
            raise HTTPException(
                status_code=413,
                detail=too_large_detail,
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


@app.post(
    "/reports/generate",
    response_model=MultiMonthReportResponse,
)
def generate_report(
    response: Response,
    archive: UploadFile = File(),
    periods: str = Form(),
    config: UploadFile | None = File(default=None),
    apple_watch_source: str | None = Form(default=None),
    apple_health_app_source: str | None = Form(default=None),
) -> MultiMonthReportResponse:
    response.headers["Cache-Control"] = "no-store"

    try:
        try:
            parsed_periods = tuple(
                ReportPeriod.from_string(
                    period.strip(),
                )
                for period in periods.split(",")
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

        with ExitStack() as temporary_files:
            temporary_archive = temporary_files.enter_context(
                NamedTemporaryFile(
                    suffix=".zip",
                )
            )

            _copy_upload_to_file(
                archive,
                temporary_archive,
                max_size=MAX_UPLOAD_SIZE,
                too_large_detail="Uploaded archive is too large.",
            )
            temporary_archive.flush()

            config_path = None

            if config is not None:
                temporary_config = temporary_files.enter_context(
                    NamedTemporaryFile(
                        suffix=".toml",
                    )
                )

                _copy_upload_to_file(
                    config,
                    temporary_config,
                    max_size=MAX_CONFIG_UPLOAD_SIZE,
                    too_large_detail="Uploaded configuration is too large.",
                )
                temporary_config.flush()

                config_path = Path(
                    temporary_config.name,
                )

            options = MultiMonthRunOptions(
                archive_path=Path(
                    temporary_archive.name,
                ),
                periods=parsed_periods,
                config_path=config_path,
                apple_watch_source=_normalize_optional_source(
                    apple_watch_source,
                ),
                apple_health_app_source=_normalize_optional_source(
                    apple_health_app_source,
                ),
            )

            try:
                reports = AppleHealthApplication().generate_reports(
                    options,
                )
            except ConfigurationError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc),
                ) from exc
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
                        detail=("Archive contains multiple Apple Health " "export XML files."),
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

        if config is not None:
            config.file.close()


def _normalize_optional_source(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None
