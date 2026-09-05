from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Cookie, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from apple_health.api.models import (
    MonthlyReportResponse,
    MultiMonthReportResponse,
)
from apple_health.application.application import AppleHealthApplication
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_period import ReportPeriod
from apple_health.config.exceptions import ConfigurationError
from apple_health.exceptions import (
    ExportXmlNotFoundError,
    ExportXmlTooLargeError,
    HealthDataParseError,
    InvalidArchiveError,
    MultipleExportXmlError,
)
from apple_health.google.oauth import (
    GoogleOAuthService,
    HttpGoogleIdentityClient,
    HttpGoogleTokenClient,
)
from apple_health.google.sessions import SessionCookieSettings, SessionStore
from apple_health.google.settings import GoogleSettings

MAX_UPLOAD_SIZE = 1024 * 1024 * 1024  # 1 GB
MAX_CONFIG_UPLOAD_SIZE = 1024 * 1024  # 1 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_REPORT_PERIODS = 120

API_DIRECTORY = Path(__file__).parent
WEB_DIRECTORY = API_DIRECTORY / "web"
EXAMPLE_CONFIG_PATH = API_DIRECTORY.parent / "config" / "examples" / "config.example.toml"

app = FastAPI(
    title="Apple Health Monitor Analyzer",
    version="0.1.0",
)

session_store = SessionStore()
google_token_client = HttpGoogleTokenClient()
google_identity_client = HttpGoogleIdentityClient()


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


def _copy_upload_to_path(
    upload: UploadFile,
    destination_path: Path,
    *,
    max_size: int,
    too_large_detail: str,
) -> None:
    with destination_path.open("wb") as destination:
        _copy_upload_to_file(
            upload,
            destination,
            max_size=max_size,
            too_large_detail=too_large_detail,
        )


def _parse_periods(periods: str) -> tuple[ReportPeriod, ...]:
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

    return parsed_periods


def _normalize_optional_source(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        WEB_DIRECTORY / "index.html",
    )


@app.get(
    "/favicon.svg",
    include_in_schema=False,
)
def favicon() -> FileResponse:
    return FileResponse(
        WEB_DIRECTORY / "favicon.svg",
        media_type="image/svg+xml",
    )


@app.get(
    "/config.example.toml",
    include_in_schema=False,
)
def example_config() -> FileResponse:
    return FileResponse(
        EXAMPLE_CONFIG_PATH,
        media_type="application/toml",
        filename="config.example.toml",
    )


@app.get(
    "/auth/google/start",
    include_in_schema=False,
)
def google_oauth_start() -> RedirectResponse:
    settings = GoogleSettings.load()

    oauth = GoogleOAuthService(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
    )

    session_id = session_store.create()

    authorization_url = oauth.start(
        sessions=session_store,
        session_id=session_id,
    )

    cookie_settings = SessionCookieSettings.for_environment(
        settings.environment,
    )

    response = RedirectResponse(
        authorization_url,
        status_code=302,
    )

    response.set_cookie(
        key=cookie_settings.name,
        value=session_id,
        httponly=cookie_settings.http_only,
        secure=cookie_settings.secure,
        samesite=cookie_settings.same_site,
    )

    return response


@app.get(
    "/auth/google/callback",
    include_in_schema=False,
)
def google_oauth_callback(
    code: str,
    state: str,
    ahm_session: str = Cookie(),
) -> dict[str, str]:
    settings = GoogleSettings.load()

    oauth = GoogleOAuthService(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
    )

    oauth.complete(
        sessions=session_store,
        session_id=ahm_session,
        returned_state=state,
        code=code,
        token_client=google_token_client,
        identity_client=google_identity_client,
    )

    return {
        "status": "google_connected",
    }


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
        parsed_periods = _parse_periods(periods)

        with TemporaryDirectory() as temporary_directory:
            temporary_directory_path = Path(temporary_directory)
            archive_path = temporary_directory_path / "export.zip"

            _copy_upload_to_path(
                archive,
                archive_path,
                max_size=MAX_UPLOAD_SIZE,
                too_large_detail="Uploaded archive is too large.",
            )

            config_path: Path | None = None

            if config is not None:
                config_path = temporary_directory_path / "config.toml"

                _copy_upload_to_path(
                    config,
                    config_path,
                    max_size=MAX_CONFIG_UPLOAD_SIZE,
                    too_large_detail="Uploaded configuration is too large.",
                )

            options = MultiMonthRunOptions(
                archive_path=archive_path,
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
            except InvalidArchiveError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid Apple Health export archive.",
                ) from exc
            except ExportXmlNotFoundError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Apple Health export XML not found in archive.",
                ) from exc
            except MultipleExportXmlError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=("Archive contains multiple Apple Health " "export XML files."),
                ) from exc
            except ExportXmlTooLargeError as exc:
                raise HTTPException(
                    status_code=413,
                    detail="Apple Health export XML is too large.",
                ) from exc
            except HealthDataParseError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid Apple Health export XML.",
                ) from exc

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
