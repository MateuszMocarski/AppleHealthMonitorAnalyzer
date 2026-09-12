from datetime import datetime, timezone

from fastapi.testclient import TestClient

import apple_health.api.app as api_app_module
from apple_health.api.app import app
from apple_health.application.application import AppleHealthApplication
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_generation_metadata import ReportGenerationMetadata
from apple_health.application.report_generation_result import ReportGenerationResult
from apple_health.application.report_period import ReportPeriod
from apple_health.config.app_config import AppConfig
from apple_health.google.oauth import GoogleOAuthService
from apple_health.google.sessions import SessionStore


def _report(*, period: ReportPeriod) -> MonthlyReports:
    return MonthlyReports(
        period=period,
        full_text="full-text",
        full_json='{"kind":"full"}',
        summary_text="summary-text",
        summary_json='{"kind":"summary"}',
        metadata=ReportGenerationMetadata(
            period=period,
            generation_id="generation-id",
            generated_at=datetime(
                2026,
                9,
                12,
                20,
                0,
                tzinfo=timezone.utc,
            ),
        ),
    )


def _generation_result(*, period: ReportPeriod) -> ReportGenerationResult:
    return ReportGenerationResult(
        reports=(_report(period=period),),
        effective_config=AppConfig(),
    )


# =====================================================================
# Verifies the anonymous local flow across input, uploaded config and
# selected outputs without touching any Google Drive persistence path.
# =====================================================================


def test_anonymous_local_generation_combines_input_config_and_outputs(
    monkeypatch,
) -> None:
    period = ReportPeriod(year=2026, month=8)
    captured = {}

    def generate_reports(self, options):
        captured["periods"] = options.periods
        captured["config"] = options.config_path.read_text()
        captured["selected_drive_config"] = options.selected_drive_config
        captured["outputs"] = options.outputs
        return _generation_result(period=period)

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        generate_reports,
    )

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("anonymous generation must not access Drive")
        ),
    )

    response = TestClient(app).post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "full_text": "true",
            "full_json": "false",
            "summary_text": "false",
            "summary_json": "true",
        },
        files={
            "archive": (
                "export.zip",
                b"local archive",
                "application/zip",
            ),
            "config": (
                "config.toml",
                b"[source]\napple_watch = 'Watch'\n",
                "application/toml",
            ),
        },
    )

    assert response.status_code == 200
    assert captured["periods"] == (period,)
    assert captured["config"] == "[source]\napple_watch = 'Watch'\n"
    assert captured["selected_drive_config"] is None
    assert captured["outputs"].full_text is True
    assert captured["outputs"].full_json is False
    assert captured["outputs"].summary_text is False
    assert captured["outputs"].summary_json is True


# =====================================================================
# Verifies that a connected generation combines a local archive with a
# selected Drive config and both report/config autosave paths.
# =====================================================================


def test_connected_local_generation_uses_selected_profile_and_autosaves(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_identity(
        session_id=session_id,
        google_sub="google-sub",
        google_email="user@example.com",
    )
    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="profile-id",
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=True,
    )

    monkeypatch.setattr(api_app_module, "session_store", sessions)

    selected_config = AppConfig()
    calls = []

    monkeypatch.setattr(
        api_app_module,
        "load_selected_config_for_session",
        lambda session: calls.append("load-profile") or selected_config,
    )

    period = ReportPeriod(year=2026, month=8)

    def generate_reports(self, options):
        assert options.selected_drive_config is selected_config
        assert options.config_path is None
        calls.append("generate")
        return _generation_result(period=period)

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        generate_reports,
    )
    monkeypatch.setattr(
        api_app_module,
        "_persist_generated_reports",
        lambda **kwargs: calls.append("report-autosave"),
    )
    monkeypatch.setattr(
        api_app_module,
        "save_config_profile_for_session",
        lambda session, *, name, config: calls.append(("config-save", name)),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "full_json": "true",
        },
        files={
            "archive": (
                "export.zip",
                b"local archive",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 200
    assert calls == [
        "load-profile",
        "generate",
        "report-autosave",
        ("config-save", "Autosave"),
    ]


# =====================================================================
# Verifies precedence across uploaded config, selected Drive profile,
# explicit config save and disabled report autosave in one request.
# =====================================================================


def test_uploaded_config_and_explicit_save_override_connected_defaults(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )
    sessions.set_selected_config_profile(
        session_id=session_id,
        profile_id="profile-id",
    )
    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(api_app_module, "session_store", sessions)

    monkeypatch.setattr(
        api_app_module,
        "load_selected_config_for_session",
        lambda session: (_ for _ in ()).throw(
            AssertionError("uploaded config must override selected profile")
        ),
    )

    period = ReportPeriod(year=2026, month=8)
    calls = []

    def generate_reports(self, options):
        assert options.config_path is not None
        assert options.selected_drive_config is None
        calls.append("generate")
        return _generation_result(period=period)

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        generate_reports,
    )

    monkeypatch.setattr(
        api_app_module,
        "find_existing_report_periods",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("report autosave is disabled")
        ),
    )

    monkeypatch.setattr(
        api_app_module,
        "save_config_profile_for_session",
        lambda session, *, name, config: calls.append(("config-save", name)),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "save_config_as": "Manual profile",
        },
        files={
            "archive": (
                "export.zip",
                b"local archive",
                "application/zip",
            ),
            "config": (
                "config.toml",
                b"[source]\napple_watch = 'Watch'\n",
                "application/toml",
            ),
        },
    )

    assert response.status_code == 200
    assert calls == [
        "generate",
        ("config-save", "Manual profile"),
    ]


# =====================================================================
# Verifies that a connected Drive ZIP can generate selected outputs while
# both config and report persistence are disabled for the session.
# =====================================================================


def test_drive_archive_generation_can_run_without_any_autosave(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )
    sessions.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )
    sessions.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    monkeypatch.setattr(api_app_module, "session_store", sessions)

    calls = []

    def download_drive_archive(*, access_token, file_id, destination):
        assert access_token == "access-token"
        assert file_id == "drive-file-id"
        destination.write_bytes(b"drive archive")
        calls.append("download")

    monkeypatch.setattr(
        api_app_module,
        "download_drive_archive",
        download_drive_archive,
    )

    period = ReportPeriod(year=2026, month=8)

    def generate_reports(self, options):
        assert options.archive_path.read_bytes() == b"drive archive"
        assert options.outputs.full_text is False
        assert options.outputs.full_json is False
        assert options.outputs.summary_text is True
        assert options.outputs.summary_json is False
        calls.append("generate")
        return _generation_result(period=period)

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        generate_reports,
    )

    monkeypatch.setattr(
        api_app_module,
        "HttpGoogleDriveClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("disabled autosave must not create persistence client")
        ),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
            "drive_file_id": "drive-file-id",
            "full_text": "false",
            "full_json": "false",
            "summary_text": "true",
            "summary_json": "false",
        },
    )

    assert response.status_code == 200
    assert calls == ["download", "generate"]


# =====================================================================
# Verifies that signing out really converts a previously Google-backed
# browser session into an anonymous local generation with no persistence.
# =====================================================================


def test_sign_out_then_local_generation_is_fully_anonymous(
    monkeypatch,
) -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    sessions.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(GoogleOAuthService.SCOPES),
        expires_in_seconds=3600,
    )

    monkeypatch.setattr(api_app_module, "session_store", sessions)

    period = ReportPeriod(year=2026, month=8)

    monkeypatch.setattr(
        AppleHealthApplication,
        "generate_reports",
        lambda self, options: _generation_result(period=period),
    )

    monkeypatch.setattr(
        api_app_module,
        "_persist_generated_reports",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("signed-out local generation must not persist")
        ),
    )

    auth_client = TestClient(app)
    auth_client.cookies.set("ahm_session", session_id)

    sign_out_response = auth_client.post(
        "/auth/sign-out",
    )

    assert sign_out_response.status_code == 200
    assert sessions.get(session_id) is None

    response = auth_client.post(
        "/reports/generate",
        data={
            "periods": "2026-08",
        },
        files={
            "archive": (
                "export.zip",
                b"local archive",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 200


# =====================================================================
# Verifies that choosing the local ZIP recovery path first leaves the
# Google-backed session so stale Drive state cannot affect generation.
# =====================================================================


def test_local_zip_recovery_switches_to_local_mode_before_file_picker() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200

    html = response.text

    assert "async function chooseLocalArchiveRecovery()" in html
    assert "await continueWithoutGoogle();" in html
    assert "archiveInput.click();" in html
    assert (
        "googleRecoveryLocal.addEventListener(\n"
        '            "click",\n'
        "            chooseLocalArchiveRecovery,\n"
        "        );" in html
    )
