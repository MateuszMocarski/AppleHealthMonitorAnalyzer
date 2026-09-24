from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from apple_health.google.sessions import SessionCookieSettings, SessionStore

# =====================================================================
# Verifies that a newly created session can be retrieved from the
# in-memory session store by its generated identifier.
# =====================================================================


def test_created_session_can_be_retrieved() -> None:
    store = SessionStore()

    session_id = store.create()

    session = store.get(session_id)

    assert session is not None
    assert session.session_id == session_id


# =====================================================================
# Verifies that each newly created session receives a unique
# identifier.
# =====================================================================


def test_created_sessions_receive_unique_identifiers() -> None:
    store = SessionStore()

    first_session_id = store.create()
    second_session_id = store.create()

    assert first_session_id != second_session_id


# =====================================================================
# Verifies that a deleted session can no longer be retrieved from the
# in-memory session store.
# =====================================================================


def test_deleted_session_can_no_longer_be_retrieved() -> None:
    store = SessionStore()

    session_id = store.create()

    store.delete(session_id)

    assert store.get(session_id) is None


# =====================================================================
# Verifies that a session expires after the eight-hour absolute TTL.
# =====================================================================


def test_session_expires_after_eight_hours() -> None:
    current_time = datetime(
        2026,
        9,
        3,
        12,
        0,
        tzinfo=UTC,
    )
    store = SessionStore(clock=lambda: current_time)

    session_id = store.create()

    current_time += timedelta(hours=8, seconds=1)

    assert store.get(session_id) is None


# =====================================================================
# Verifies that retrieving a session does not extend its absolute
# expiration time.
# =====================================================================


def test_retrieving_session_does_not_extend_expiration() -> None:
    current_time = datetime(
        2026,
        9,
        3,
        12,
        0,
        tzinfo=UTC,
    )
    store = SessionStore(clock=lambda: current_time)

    session_id = store.create()

    current_time += timedelta(hours=7)
    assert store.get(session_id) is not None

    current_time += timedelta(hours=1, seconds=1)
    assert store.get(session_id) is None


# =====================================================================
# Verifies that production session cookies use the required security
# attributes.
# =====================================================================


def test_production_session_cookie_settings_are_secure() -> None:
    settings = SessionCookieSettings.for_environment("production")

    assert settings.name == "ahm_session"
    assert settings.http_only is True
    assert settings.secure is True
    assert settings.same_site == "lax"


# =====================================================================
# Verifies that development session cookies allow local HTTP usage.
# =====================================================================


def test_development_session_cookie_settings_allow_local_http() -> None:
    settings = SessionCookieSettings.for_environment("development")

    assert settings.name == "ahm_session"
    assert settings.http_only is True
    assert settings.secure is False
    assert settings.same_site == "lax"


# =====================================================================
# Verifies that a session expires exactly at the eight-hour absolute
# TTL boundary.
# =====================================================================


def test_session_expires_exactly_at_eight_hours() -> None:
    current_time = datetime(
        2026,
        9,
        3,
        12,
        0,
        tzinfo=UTC,
    )
    store = SessionStore(clock=lambda: current_time)

    session_id = store.create()

    current_time += timedelta(hours=8)

    assert store.get(session_id) is None


# =====================================================================
# Verifies that deleting an unknown session is safe and idempotent.
# =====================================================================


def test_deleting_unknown_session_does_not_fail() -> None:
    store = SessionStore()

    store.delete("unknown-session-id")
    store.delete("unknown-session-id")


# =====================================================================
# Verifies that session cookie settings reject an unsupported
# application environment.
# =====================================================================


def test_session_cookie_settings_reject_unsupported_environment() -> None:
    with pytest.raises(
        ValueError,
        match="environment",
    ):
        SessionCookieSettings.for_environment("banana")


# =====================================================================
# Verifies that verified Google identity is stored in the backend
# session using sub as the technical identity and email for display.
# =====================================================================


def test_google_identity_can_be_stored_in_session() -> None:
    store = SessionStore()
    session_id = store.create()

    store.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )

    session = store.get(session_id)

    assert session is not None
    assert session.google_sub == "google-user-123"
    assert session.google_email == "user@example.com"


# =====================================================================
# Verifies that Google access credentials are stored together with the
# granted scopes and an absolute token expiration timestamp.
# =====================================================================


def test_google_access_credentials_can_be_stored_in_session() -> None:
    current_time = datetime(
        2026,
        9,
        5,
        18,
        0,
        tzinfo=UTC,
    )
    store = SessionStore(clock=lambda: current_time)
    session_id = store.create()

    granted_scopes = frozenset(
        {
            "openid",
            "email",
            "https://www.googleapis.com/auth/drive.file",
        }
    )

    store.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=granted_scopes,
        expires_in_seconds=3600,
    )

    session = store.get(session_id)

    assert session is not None
    assert session.google_access_token == "access-token"
    assert session.google_granted_scopes == granted_scopes
    assert session.google_access_token_expires_at == current_time + timedelta(
        seconds=3600,
    )


# =====================================================================
# Verifies that Google mode is ready only when the session contains
# complete identity, required scopes, and a non-expired access token.
# =====================================================================


def test_google_mode_ready_requires_complete_valid_google_session() -> None:
    current_time = datetime(
        2026,
        9,
        5,
        18,
        0,
        tzinfo=UTC,
    )
    store = SessionStore(clock=lambda: current_time)

    required_scopes = frozenset(
        {
            "openid",
            "email",
            "https://www.googleapis.com/auth/drive.file",
        }
    )

    session_id = store.create()

    assert (
        store.is_google_mode_ready(
            session_id=session_id,
            required_scopes=required_scopes,
        )
        is False
    )

    store.set_google_identity(
        session_id=session_id,
        google_sub="google-user-123",
        google_email="user@example.com",
    )

    assert (
        store.is_google_mode_ready(
            session_id=session_id,
            required_scopes=required_scopes,
        )
        is False
    )

    store.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=frozenset(
            {
                "openid",
                "email",
            }
        ),
        expires_in_seconds=3600,
    )

    assert (
        store.is_google_mode_ready(
            session_id=session_id,
            required_scopes=required_scopes,
        )
        is False
    )

    store.set_google_access_credentials(
        session_id=session_id,
        access_token="access-token",
        granted_scopes=required_scopes,
        expires_in_seconds=3600,
    )

    assert (
        store.is_google_mode_ready(
            session_id=session_id,
            required_scopes=required_scopes,
        )
        is True
    )

    current_time += timedelta(hours=1)

    assert (
        store.is_google_mode_ready(
            session_id=session_id,
            required_scopes=required_scopes,
        )
        is False
    )


# =====================================================================
# Verifies that a new application session starts without any selected
# Drive config profile.
# =====================================================================


def test_new_session_has_no_selected_config_profile() -> None:
    store = SessionStore()

    session_id = store.create()
    session = store.get(session_id)

    assert session is not None
    assert session.selected_config_profile_id is None


# =====================================================================
# Verifies that a Drive config profile becomes selected only after an
# explicit session update.
# =====================================================================


def test_session_can_select_config_profile() -> None:
    store = SessionStore()
    session_id = store.create()

    store.set_selected_config_profile(
        session_id,
        "config-1",
    )

    session = store.get(session_id)

    assert session is not None
    assert session.selected_config_profile_id == "config-1"


# =====================================================================
# Verifies that the selected Drive config profile can be cleared so the
# session returns to having no active Drive configuration.
# =====================================================================


def test_session_can_clear_selected_config_profile() -> None:
    store = SessionStore()
    session_id = store.create()

    store.set_selected_config_profile(
        session_id,
        "config-1",
    )
    store.clear_selected_config_profile(session_id)

    session = store.get(session_id)

    assert session is not None
    assert session.selected_config_profile_id is None


# =====================================================================
# Verifies that configuration autosave can be explicitly disabled for
# an existing session.
# =====================================================================


def test_config_autosave_can_be_disabled() -> None:
    store = SessionStore()
    session_id = store.create()

    store.set_config_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    session = store.get(session_id)

    assert session is not None
    assert session.config_autosave_enabled is False


# =====================================================================
# Verifies that report autosave is enabled by default for a new
# session and can be explicitly disabled.
# =====================================================================


def test_report_autosave_defaults_to_enabled_and_can_be_disabled() -> None:
    store = SessionStore()
    session_id = store.create()

    session = store.get(session_id)

    assert session is not None
    assert session.report_autosave_enabled is True

    store.set_report_autosave_enabled(
        session_id=session_id,
        enabled=False,
    )

    session = store.get(session_id)

    assert session is not None
    assert session.report_autosave_enabled is False


# =====================================================================
# Verifies that opaque session credentials and OAuth credentials are
# redacted from the session representation used by diagnostics/logging.
# =====================================================================


def test_session_repr_redacts_session_and_oauth_credentials() -> None:
    store = SessionStore()
    session_id = store.create()

    store.set_oauth_state(
        session_id,
        "oauth-state-secret",
    )

    store.set_google_access_credentials(
        session_id=session_id,
        access_token="google-access-token-secret",
        granted_scopes=frozenset(),
        expires_in_seconds=3600,
    )

    session = store.get(session_id)

    assert session is not None

    rendered = repr(session)

    assert session_id not in rendered
    assert "oauth-state-secret" not in rendered
    assert "google-access-token-secret" not in rendered


# =====================================================================
# Verifies that new sessions disable configuration autosave by default
# while report autosave remains enabled.
# =====================================================================


def test_new_session_uses_expected_autosave_defaults() -> None:
    store = SessionStore()

    session_id = store.create()

    session = store.get(session_id)

    assert session is not None
    assert session.config_autosave_enabled is False
    assert session.report_autosave_enabled is True


# =====================================================================
# Verifies that session mutators reject missing or expired sessions
# instead of silently creating partial state.
# =====================================================================


@pytest.mark.parametrize(
    "operation",
    [
        lambda store: store.set_oauth_state("missing", "state"),
        lambda store: store.clear_oauth_state("missing"),
        lambda store: store.set_google_identity(
            session_id="missing",
            google_sub="sub",
            google_email="user@example.com",
        ),
        lambda store: store.set_google_access_credentials(
            session_id="missing",
            access_token="token",
            granted_scopes=frozenset(),
            expires_in_seconds=3600,
        ),
        lambda store: store.set_selected_config_profile(
            session_id="missing",
            profile_id="profile",
        ),
        lambda store: store.clear_selected_config_profile("missing"),
        lambda store: store.set_config_autosave_enabled(
            session_id="missing",
            enabled=True,
        ),
        lambda store: store.set_report_autosave_enabled(
            session_id="missing",
            enabled=False,
        ),
    ],
)
def test_session_mutators_reject_missing_session(operation) -> None:
    store = SessionStore()

    with pytest.raises(
        ValueError,
        match="Session does not exist or has expired",
    ):
        operation(store)


# =====================================================================
# Verifies Google mode is not ready until scope and token-expiry state
# are both present in addition to identity and access token data.
# =====================================================================


def test_google_mode_ready_requires_scope_and_expiry_state() -> None:
    now = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    store = SessionStore(clock=lambda: now)
    session_id = store.create()

    store.set_google_identity(
        session_id=session_id,
        google_sub="sub",
        google_email="user@example.com",
    )

    session = store.get(session_id)
    assert session is not None

    store._sessions[session_id] = replace(
        session,
        google_access_token="token",
        google_granted_scopes=None,
        google_access_token_expires_at=None,
    )

    assert store.is_google_mode_ready(session_id, frozenset()) is False

    session = store.get(session_id)
    assert session is not None
    store._sessions[session_id] = replace(
        session,
        google_granted_scopes=frozenset(),
    )

    assert store.is_google_mode_ready(session_id, frozenset()) is False
