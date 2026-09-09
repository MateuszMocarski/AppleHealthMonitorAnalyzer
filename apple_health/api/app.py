from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Cookie, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from apple_health.api.models import (
    MonthlyReportResponse,
    MultiMonthReportResponse,
)
from apple_health.application.application import AppleHealthApplication
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig
from apple_health.config.exceptions import ConfigurationError
from apple_health.exceptions import (
    ExportXmlNotFoundError,
    ExportXmlTooLargeError,
    HealthDataParseError,
    InvalidArchiveError,
    MultipleExportXmlError,
)
from apple_health.google.config_profiles import (
    ConfigProfile,
    discover_drive_config_profiles,
    load_config_profile,
    save_config_profile,
)
from apple_health.google.drive import (
    DriveAccessError,
    DriveDownloadTooLargeError,
    DriveFileMetadata,
    DriveNotFoundError,
    DriveTransientError,
    HttpGoogleDriveClient,
)
from apple_health.google.drive_structure import (
    discover_ahm_root,
    discover_config_container,
    ensure_ahm_root,
    ensure_config_container,
)
from apple_health.google.oauth import (
    GoogleOAuthError,
    GoogleOAuthService,
    GoogleOAuthStateError,
    HttpGoogleIdentityClient,
    HttpGoogleRevocationClient,
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
google_revocation_client = HttpGoogleRevocationClient()


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


def discover_config_profiles_for_session(
    session,
) -> tuple[ConfigProfile, ...]:
    if session.google_access_token is None:
        return ()

    drive_client = HttpGoogleDriveClient(
        session.google_access_token,
    )

    root = discover_ahm_root(
        drive_client,
    )

    if root is None:
        return ()

    config_container = discover_config_container(
        drive_client,
        root_id=root.file_id,
    )

    if config_container is None:
        return ()

    return discover_drive_config_profiles(
        drive_client,
        config_container_id=config_container.file_id,
    )


def load_selected_config_for_session(
    session,
) -> AppConfig | None:
    if session.selected_config_profile_id is None or session.google_access_token is None:
        return None

    drive_client = HttpGoogleDriveClient(
        session.google_access_token,
    )

    root = discover_ahm_root(
        drive_client,
    )

    if root is None:
        raise ConfigurationError("Selected configuration profile is unavailable.")

    config_container = discover_config_container(
        drive_client,
        root_id=root.file_id,
    )

    if config_container is None:
        raise ConfigurationError("Selected configuration profile is unavailable.")

    profiles = discover_drive_config_profiles(
        drive_client,
        config_container_id=config_container.file_id,
    )

    selected_profile = next(
        (profile for profile in profiles if profile.file_id == session.selected_config_profile_id),
        None,
    )

    if selected_profile is None:
        raise ConfigurationError("Selected configuration profile is unavailable.")

    return load_config_profile(
        drive_client,
        selected_profile,
    )


def save_config_profile_for_session(
    session,
    *,
    name: str,
    config: AppConfig,
) -> None:
    if session.google_access_token is None:
        raise ConfigurationError("Google Drive session is unavailable.")

    drive_client = HttpGoogleDriveClient(
        session.google_access_token,
    )

    root = ensure_ahm_root(
        drive_client,
    )

    config_container = ensure_config_container(
        drive_client,
        root_id=root.file_id,
    )

    existing_profiles = discover_drive_config_profiles(
        drive_client,
    )

    save_config_profile(
        drive_client,
        config_container_id=config_container.file_id,
        name=name,
        config=config,
        existing_profiles=existing_profiles,
    )


def verify_drive_archive(
    *,
    access_token: str,
    file_id: str,
) -> DriveFileMetadata:
    if not file_id.strip():
        raise HTTPException(
            status_code=422,
            detail="Selected Google Drive file ID is invalid.",
        )

    drive_client = HttpGoogleDriveClient(
        access_token,
    )

    try:
        metadata = drive_client.get_metadata(
            file_id,
        )
    except (
        DriveAccessError,
        DriveNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail="Selected Google Drive file is unavailable.",
        ) from exc

    if metadata.trashed:
        raise HTTPException(
            status_code=422,
            detail="Selected Google Drive file is unavailable.",
        )

    if metadata.mime_type != "application/zip":
        raise HTTPException(
            status_code=422,
            detail="Selected Google Drive file is not a ZIP archive.",
        )

    if metadata.size_bytes is None or metadata.size_bytes > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Selected Google Drive archive is too large.",
        )

    return metadata


def download_drive_archive(
    *,
    access_token: str,
    file_id: str,
    destination: Path,
) -> None:
    verify_drive_archive(
        access_token=access_token,
        file_id=file_id,
    )

    drive_client = HttpGoogleDriveClient(
        access_token,
    )

    try:
        drive_client.download_file(
            file_id,
            destination,
            MAX_UPLOAD_SIZE,
        )
    except DriveDownloadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail="Selected Google Drive archive is too large.",
        ) from exc
    except (
        DriveAccessError,
        DriveNotFoundError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail="Selected Google Drive file is unavailable.",
        ) from exc
    except DriveTransientError as exc:
        raise HTTPException(
            status_code=502,
            detail="Google Drive is temporarily unavailable.",
        ) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        WEB_DIRECTORY / "index.html",
    )


@app.get(
    "/favicon.svg",
    include_in_schema=False,
)
@app.get(
    "/favicon.ico",
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


@app.get("/config/profiles")
def get_config_profiles(
    ahm_session: str = Cookie(),
) -> dict:
    session = session_store.get(ahm_session)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Google session is unavailable.",
        )

    profiles = discover_config_profiles_for_session(session)

    return {
        "profiles": [
            {
                "file_id": profile.file_id,
                "name": profile.name,
            }
            for profile in profiles
        ],
        "selected_profile_id": session.selected_config_profile_id,
        "autosave_enabled": session.config_autosave_enabled,
    }


@app.post("/config/profiles/select")
def select_config_profile(
    profile_id: str = Form(),
    ahm_session: str = Cookie(),
) -> dict[str, str]:
    session = session_store.get(ahm_session)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Google session is unavailable.",
        )

    profiles = discover_config_profiles_for_session(session)

    if not any(profile.file_id == profile_id for profile in profiles):
        raise HTTPException(
            status_code=404,
            detail="Configuration profile not found.",
        )

    session_store.set_selected_config_profile(
        session_id=ahm_session,
        profile_id=profile_id,
    )

    return {
        "selected_profile_id": profile_id,
    }


@app.post("/config/profiles/select-none")
def clear_config_profile_selection(
    ahm_session: str = Cookie(),
) -> dict[str, str | None]:
    session = session_store.get(ahm_session)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Google session is unavailable.",
        )

    session_store.clear_selected_config_profile(
        session_id=ahm_session,
    )

    return {
        "selected_profile_id": None,
    }


@app.post("/config/autosave")
def set_config_autosave(
    enabled: bool = Form(),
    ahm_session: str = Cookie(),
) -> dict[str, bool]:
    session = session_store.get(ahm_session)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Google session is unavailable.",
        )

    session_store.set_config_autosave_enabled(
        session_id=ahm_session,
        enabled=enabled,
    )

    return {
        "autosave_enabled": enabled,
    }


@app.get(
    "/auth/google/start",
    include_in_schema=False,
)
def google_oauth_start(
    ahm_session: str | None = Cookie(default=None),
) -> RedirectResponse:
    settings = GoogleSettings.load()

    oauth = GoogleOAuthService(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
    )

    session_id = ahm_session

    if session_id is None or session_store.get(session_id) is None:
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
    state: str,
    code: str | None = None,
    error: str | None = None,
    ahm_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    if ahm_session is None:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth session is missing or has expired.",
        )

    if session_store.get(ahm_session) is None:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth session is missing or has expired.",
        )

    settings = GoogleSettings.load()

    oauth = GoogleOAuthService(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
    )

    if error == "access_denied":
        raise HTTPException(
            status_code=400,
            detail="Google authorization was denied.",
        )

    if code is None:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth callback is incomplete.",
        )

    try:
        oauth.complete(
            sessions=session_store,
            session_id=ahm_session,
            returned_state=state,
            code=code,
            token_client=google_token_client,
            identity_client=google_identity_client,
        )
    except GoogleOAuthStateError:
        raise HTTPException(status_code=400, detail="Google OAuth callback is invalid.")
    except GoogleOAuthError as exc:
        raise HTTPException(
            status_code=502,
            detail="Google OAuth connection failed.",
        ) from exc

    return {
        "status": "google_connected",
    }


@app.post(
    "/auth/sign-out",
    include_in_schema=False,
)
def sign_out(
    response: Response,
    ahm_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    if ahm_session is not None:
        session_store.delete(ahm_session)

    response.delete_cookie(
        key="ahm_session",
    )

    return {
        "status": "signed_out",
    }


@app.post(
    "/auth/google/disconnect",
    include_in_schema=False,
    response_model=None,
)
def disconnect_google(
    response: Response,
    ahm_session: str | None = Cookie(default=None),
) -> dict[str, str] | JSONResponse:
    if ahm_session is None:
        raise HTTPException(
            status_code=400,
            detail="Google connection is not available.",
        )

    session = session_store.get(ahm_session)

    if session is None or session.google_access_token is None:
        raise HTTPException(
            status_code=400,
            detail="Google connection is not available.",
        )

    try:
        google_revocation_client.revoke(
            session.google_access_token,
        )
    except GoogleOAuthError:
        session_store.delete(ahm_session)

        error_response = JSONResponse(
            status_code=502,
            content={
                "detail": "Google disconnect failed.",
            },
        )
        error_response.delete_cookie(
            key="ahm_session",
        )

        return error_response

    session_store.delete(ahm_session)

    response.delete_cookie(
        key="ahm_session",
    )

    return {
        "status": "google_disconnected",
    }


@app.get(
    "/auth/google/status",
    include_in_schema=False,
)
def google_status(
    ahm_session: str | None = Cookie(default=None),
) -> dict[str, str]:
    if ahm_session is None:
        return {
            "status": "disconnected",
        }

    session = session_store.get(ahm_session)

    if session is None:
        return {
            "status": "disconnected",
        }

    if not session_store.is_google_mode_ready(
        ahm_session,
        frozenset(GoogleOAuthService.SCOPES),
    ):
        if session.google_sub is not None and session.google_email is not None:
            return {
                "status": "reconnect_required",
                "email": session.google_email,
            }

        return {
            "status": "disconnected",
        }

    assert session.google_email is not None

    return {
        "status": "connected",
        "email": session.google_email,
    }


@app.get(
    "/google/picker/config",
    include_in_schema=False,
)
def google_picker_config() -> dict[str, str]:
    settings = GoogleSettings.load()

    return {
        "api_key": settings.picker_api_key,
        "app_id": settings.cloud_project_number,
    }


@app.get(
    "/google/picker/token",
    include_in_schema=False,
)
def google_picker_token(
    response: Response,
    ahm_session: str = Cookie(),
) -> dict[str, str]:
    session = session_store.get(
        ahm_session,
    )

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Google session is unavailable.",
        )

    if not session_store.is_google_mode_ready(
        ahm_session,
        frozenset(GoogleOAuthService.SCOPES),
    ):
        raise HTTPException(
            status_code=401,
            detail="Google reconnect is required.",
        )

    assert session.google_access_token is not None

    response.headers["Cache-Control"] = "no-store"

    return {
        "access_token": session.google_access_token,
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
    archive: UploadFile | None = File(default=None),
    periods: str = Form(),
    config: UploadFile | None = File(default=None),
    apple_watch_source: str | None = Form(default=None),
    apple_health_app_source: str | None = Form(default=None),
    ahm_session: str | None = Cookie(default=None),
    save_config_as: str | None = Form(default=None),
    drive_file_id: str | None = Form(default=None),
) -> MultiMonthReportResponse:
    response.headers["Cache-Control"] = "no-store"

    try:
        parsed_periods = _parse_periods(periods)

        if archive is not None and drive_file_id is not None:
            raise HTTPException(
                status_code=422,
                detail="Choose exactly one Apple Health archive source.",
            )

        with TemporaryDirectory() as temporary_directory:
            temporary_directory_path = Path(
                temporary_directory,
            )

            archive_path = temporary_directory_path / "archive.zip"

            if drive_file_id is not None:
                if ahm_session is None:
                    raise HTTPException(
                        status_code=401,
                        detail="Google session is unavailable.",
                    )

                session = session_store.get(
                    ahm_session,
                )

                if session is None or session.google_access_token is None:
                    raise HTTPException(
                        status_code=401,
                        detail="Google session is unavailable.",
                    )

                download_drive_archive(
                    access_token=session.google_access_token,
                    file_id=drive_file_id,
                    destination=archive_path,
                )

            elif archive is not None:
                _copy_upload_to_path(
                    archive,
                    archive_path,
                    max_size=MAX_UPLOAD_SIZE,
                    too_large_detail="Uploaded archive is too large.",
                )

            else:
                raise HTTPException(
                    status_code=422,
                    detail="Apple Health archive is required.",
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
            selected_drive_config = None

            if ahm_session is not None:
                session = session_store.get(ahm_session)

                if (
                    session is not None
                    and session.selected_config_profile_id is not None
                    and config_path is None
                ):
                    selected_drive_config = load_selected_config_for_session(
                        session,
                    )

            options = MultiMonthRunOptions(
                archive_path=archive_path,
                periods=parsed_periods,
                config_path=config_path,
                selected_drive_config=selected_drive_config,
                apple_watch_source=_normalize_optional_source(
                    apple_watch_source,
                ),
                apple_health_app_source=_normalize_optional_source(
                    apple_health_app_source,
                ),
            )

            try:
                generation_result = AppleHealthApplication().generate_reports(
                    options,
                )
                if (
                    save_config_as is not None
                    and save_config_as.strip()
                    and ahm_session is not None
                ):
                    session = session_store.get(ahm_session)

                    if session is not None:
                        save_config_profile_for_session(
                            session,
                            name=save_config_as.strip(),
                            config=generation_result.effective_config,
                        )

                elif ahm_session is not None:
                    session = session_store.get(ahm_session)

                    if session is not None and session.config_autosave_enabled:
                        save_config_profile_for_session(
                            session,
                            name="Autosave",
                            config=generation_result.effective_config,
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
                for report in generation_result.reports
            ]
        )

    finally:
        if archive is not None:
            archive.file.close()

        if config is not None:
            config.file.close()
