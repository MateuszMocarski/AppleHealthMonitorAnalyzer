from urllib.parse import parse_qs, urlparse

import pytest

from apple_health.google.oauth import GoogleOAuthError, GoogleOAuthService
from apple_health.google.sessions import SessionStore

# =====================================================================
# Verifies that starting Google OAuth creates a state value stored in
# the backend session and included in the authorization URL.
# =====================================================================


def test_start_oauth_stores_state_and_includes_it_in_authorization_url() -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    authorization_url = oauth.start(
        sessions=sessions,
        session_id=session_id,
    )

    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is not None
    assert f"state={session.oauth_state}" in authorization_url


# =====================================================================
# Verifies that Google OAuth requests exactly the identity and
# application-specific Drive scopes required by the application.
# =====================================================================


def test_start_oauth_requests_required_scopes() -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    authorization_url = oauth.start(
        sessions=sessions,
        session_id=session_id,
    )

    query = parse_qs(urlparse(authorization_url).query)

    assert set(query["scope"][0].split()) == {
        "openid",
        "email",
        "https://www.googleapis.com/auth/drive.file",
    }


# =====================================================================
# Verifies that an OAuth callback with a mismatched state value is
# rejected.
# =====================================================================


def test_oauth_callback_rejects_mismatched_state() -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    oauth.start(
        sessions=sessions,
        session_id=session_id,
    )

    with pytest.raises(
        GoogleOAuthError,
        match="state",
    ):
        oauth.validate_callback_state(
            sessions=sessions,
            session_id=session_id,
            returned_state="different-state",
        )


# =====================================================================
# Verifies that a valid OAuth state value is consumed after successful
# validation and cannot be reused.
# =====================================================================


def test_oauth_callback_state_cannot_be_reused() -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    oauth.start(
        sessions=sessions,
        session_id=session_id,
    )

    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is not None

    returned_state = session.oauth_state

    oauth.validate_callback_state(
        sessions=sessions,
        session_id=session_id,
        returned_state=returned_state,
    )

    with pytest.raises(
        GoogleOAuthError,
        match="state",
    ):
        oauth.validate_callback_state(
            sessions=sessions,
            session_id=session_id,
            returned_state=returned_state,
        )


# =====================================================================
# Verifies that an authorization code is exchanged using the configured
# Google OAuth client credentials and redirect URI.
# =====================================================================


def test_exchange_code_uses_google_oauth_configuration() -> None:
    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        client_secret="dev-client-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    exchanged_parameters = None

    def exchange_token(endpoint, **parameters):
        nonlocal exchanged_parameters
        exchanged_parameters = parameters
        return "access-token"

    access_token = oauth.exchange_code(
        code="authorization-code",
        exchange_token=exchange_token,
    )

    assert access_token == "access-token"
    assert exchanged_parameters["code"] == "authorization-code"
    assert exchanged_parameters["client_id"] == "dev-client-id"
    assert exchanged_parameters["client_secret"] == "dev-client-secret"
    assert exchanged_parameters["redirect_uri"] == "http://localhost:8000/auth/google/callback"


# =====================================================================
# Verifies that exchanging an authorization code uses the Google token
# endpoint and authorization_code grant type.
# =====================================================================


def test_exchange_code_uses_google_token_endpoint_and_grant_type() -> None:
    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        client_secret="dev-client-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    exchange_request = None

    def exchange_token(endpoint, **parameters):
        nonlocal exchange_request
        exchange_request = (endpoint, parameters)
        return "access-token"

    oauth.exchange_code(
        code="authorization-code",
        exchange_token=exchange_token,
    )

    assert exchange_request == (
        "https://oauth2.googleapis.com/token",
        {
            "code": "authorization-code",
            "client_id": "dev-client-id",
            "client_secret": "dev-client-secret",
            "redirect_uri": "http://localhost:8000/auth/google/callback",
            "grant_type": "authorization_code",
        },
    )


# =====================================================================
# Verifies that a successfully exchanged Google access token is stored
# only in the backend session.
# =====================================================================


def test_complete_oauth_stores_access_token_in_session() -> None:
    sessions = SessionStore()
    session_id = sessions.create()

    oauth = GoogleOAuthService(
        client_id="dev-client-id",
        client_secret="dev-client-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    oauth.start(
        sessions=sessions,
        session_id=session_id,
    )

    session = sessions.get(session_id)

    assert session is not None
    assert session.oauth_state is not None

    oauth.complete(
        sessions=sessions,
        session_id=session_id,
        returned_state=session.oauth_state,
        code="authorization-code",
        exchange_token=lambda endpoint, **parameters: "access-token",
    )

    session = sessions.get(session_id)

    assert session is not None
    assert session.google_access_token == "access-token"
