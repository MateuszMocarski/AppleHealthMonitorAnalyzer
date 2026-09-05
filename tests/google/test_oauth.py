from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apple_health.google.oauth import (
    GoogleOAuthError,
    GoogleOAuthService,
    HttpGoogleTokenClient,
)
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
# Verifies that completing Google OAuth forwards the configured client
# credentials and redirect URI to the token client.
# =====================================================================


def test_complete_oauth_uses_google_oauth_configuration() -> None:
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

    class CapturingTokenClient:
        def __init__(self) -> None:
            self.parameters: dict[str, str] | None = None

        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> str:
            self.parameters = {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            }
            return "access-token"

    token_client = CapturingTokenClient()

    oauth.complete(
        sessions=sessions,
        session_id=session_id,
        returned_state=session.oauth_state,
        code="authorization-code",
        token_client=token_client,
    )

    assert token_client.parameters == {
        "code": "authorization-code",
        "client_id": "dev-client-id",
        "client_secret": "dev-client-secret",
        "redirect_uri": "http://localhost:8000/auth/google/callback",
    }


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

    class FakeTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> str:
            return "access-token"

    oauth.complete(
        sessions=sessions,
        session_id=session_id,
        returned_state=session.oauth_state,
        code="authorization-code",
        token_client=FakeTokenClient(),
    )

    session = sessions.get(session_id)

    assert session is not None
    assert session.google_access_token == "access-token"


# =====================================================================
# Verifies that the HTTP Google token client exchanges an authorization
# code against the Google OAuth token endpoint.
# =====================================================================


def test_http_google_token_client_exchanges_authorization_code(
    monkeypatch,
) -> None:
    captured_request = None

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {
                "access_token": "access-token",
            }

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        nonlocal captured_request
        captured_request = (
            url,
            data,
            timeout,
        )
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    token_client = HttpGoogleTokenClient()

    access_token = token_client.exchange_code(
        code="authorization-code",
        client_id="dev-client-id",
        client_secret="dev-client-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    assert access_token == "access-token"
    assert captured_request == (
        "https://oauth2.googleapis.com/token",
        {
            "code": "authorization-code",
            "client_id": "dev-client-id",
            "client_secret": "dev-client-secret",
            "redirect_uri": "http://localhost:8000/auth/google/callback",
            "grant_type": "authorization_code",
        },
        10.0,
    )


# =====================================================================
# Verifies that an HTTP failure from the Google token endpoint is
# exposed as a controlled OAuth error.
# =====================================================================


def test_http_google_token_client_maps_google_http_error(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "POST",
                "https://oauth2.googleapis.com/token",
            )
            response = httpx.Response(
                400,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Google token exchange failed",
                request=request,
                response=response,
            )

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    token_client = HttpGoogleTokenClient()

    with pytest.raises(
        GoogleOAuthError,
        match="token",
    ):
        token_client.exchange_code(
            code="authorization-code",
            client_id="dev-client-id",
            client_secret="dev-client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )


# =====================================================================
# Verifies that a network failure during the Google token exchange is
# exposed as a controlled OAuth error.
# =====================================================================


def test_http_google_token_client_maps_network_error(
    monkeypatch,
) -> None:
    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> None:
        request = httpx.Request(
            "POST",
            "https://oauth2.googleapis.com/token",
        )

        raise httpx.ConnectError(
            "Connection failed",
            request=request,
        )

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    token_client = HttpGoogleTokenClient()

    with pytest.raises(
        GoogleOAuthError,
        match="token",
    ):
        token_client.exchange_code(
            code="authorization-code",
            client_id="dev-client-id",
            client_secret="dev-client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )


# =====================================================================
# Verifies that malformed JSON returned by the Google token endpoint is
# exposed as a controlled OAuth error.
# =====================================================================


def test_http_google_token_client_rejects_malformed_json(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            raise ValueError("Malformed JSON")

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    token_client = HttpGoogleTokenClient()

    with pytest.raises(
        GoogleOAuthError,
        match="token",
    ):
        token_client.exchange_code(
            code="authorization-code",
            client_id="dev-client-id",
            client_secret="dev-client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )


# =====================================================================
# Verifies that a Google token response without an access token is
# rejected as invalid.
# =====================================================================


def test_http_google_token_client_rejects_missing_access_token(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {}

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    token_client = HttpGoogleTokenClient()

    with pytest.raises(
        GoogleOAuthError,
        match="token",
    ):
        token_client.exchange_code(
            code="authorization-code",
            client_id="dev-client-id",
            client_secret="dev-client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )


# =====================================================================
# Verifies that Google token responses containing an invalid access
# token value are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "access_token",
    [
        None,
        "",
        "   ",
        123,
    ],
)
def test_http_google_token_client_rejects_invalid_access_token(
    monkeypatch,
    access_token,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "access_token": access_token,
            }

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    token_client = HttpGoogleTokenClient()

    with pytest.raises(
        GoogleOAuthError,
        match="token",
    ):
        token_client.exchange_code(
            code="authorization-code",
            client_id="dev-client-id",
            client_secret="dev-client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
        )
