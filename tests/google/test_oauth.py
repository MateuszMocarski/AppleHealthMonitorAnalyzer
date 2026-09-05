from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apple_health.google.oauth import (
    GoogleOAuthError,
    GoogleOAuthService,
    HttpGoogleIdentityClient,
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

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
            assert access_token == "access-token"
            return FakeIdentity()

    token_client = CapturingTokenClient()

    oauth.complete(
        sessions=sessions,
        session_id=session_id,
        returned_state=session.oauth_state,
        code="authorization-code",
        token_client=token_client,
        identity_client=FakeIdentityClient(),
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

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
            assert access_token == "access-token"
            return FakeIdentity()

    oauth.complete(
        sessions=sessions,
        session_id=session_id,
        returned_state=session.oauth_state,
        code="authorization-code",
        token_client=FakeTokenClient(),
        identity_client=FakeIdentityClient(),
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
# Verifies that completing Google OAuth retrieves the Google identity
# and stores sub plus display email in the backend session.
# =====================================================================


def test_complete_oauth_stores_google_identity_in_session() -> None:
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

    @dataclass(frozen=True)
    class FakeIdentity:
        sub: str
        email: str

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
            assert access_token == "access-token"

            return FakeIdentity(
                sub="google-user-123",
                email="user@example.com",
            )

    oauth.complete(
        sessions=sessions,
        session_id=session_id,
        returned_state=session.oauth_state,
        code="authorization-code",
        token_client=FakeTokenClient(),
        identity_client=FakeIdentityClient(),
    )

    session = sessions.get(session_id)

    assert session is not None
    assert session.google_sub == "google-user-123"
    assert session.google_email == "user@example.com"


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


# =====================================================================
# Verifies that the HTTP Google identity client retrieves sub and email
# from the Google OpenID Connect UserInfo endpoint.
# =====================================================================


def test_http_google_identity_client_retrieves_google_identity(
    monkeypatch,
) -> None:
    captured_request = None

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            return {
                "sub": "google-user-123",
                "email": "user@example.com",
            }

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        nonlocal captured_request
        captured_request = (
            url,
            headers,
            timeout,
        )
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.get",
        fake_get,
    )

    identity_client = HttpGoogleIdentityClient()

    identity = identity_client.get_identity(
        access_token="access-token",
    )

    assert identity.sub == "google-user-123"
    assert identity.email == "user@example.com"

    assert captured_request == (
        "https://openidconnect.googleapis.com/v1/userinfo",
        {
            "Authorization": "Bearer access-token",
        },
        10.0,
    )


# =====================================================================
# Verifies that Google UserInfo responses with invalid identity fields
# are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"sub": "google-user-123"},
        {"email": "user@example.com"},
        {"sub": None, "email": "user@example.com"},
        {"sub": "", "email": "user@example.com"},
        {"sub": "   ", "email": "user@example.com"},
        {"sub": 123, "email": "user@example.com"},
        {"sub": "google-user-123", "email": None},
        {"sub": "google-user-123", "email": ""},
        {"sub": "google-user-123", "email": "   "},
        {"sub": "google-user-123", "email": 123},
    ],
)
def test_http_google_identity_client_rejects_invalid_identity(
    monkeypatch,
    payload,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return payload

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.get",
        fake_get,
    )

    identity_client = HttpGoogleIdentityClient()

    with pytest.raises(
        GoogleOAuthError,
        match="identity",
    ):
        identity_client.get_identity(
            access_token="access-token",
        )


# =====================================================================
# Verifies that a network failure while retrieving Google identity is
# exposed as a controlled OAuth error.
# =====================================================================


def test_http_google_identity_client_maps_network_error(
    monkeypatch,
) -> None:
    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> None:
        request = httpx.Request(
            "GET",
            "https://openidconnect.googleapis.com/v1/userinfo",
        )

        raise httpx.ConnectError(
            "Connection failed",
            request=request,
        )

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.get",
        fake_get,
    )

    identity_client = HttpGoogleIdentityClient()

    with pytest.raises(
        GoogleOAuthError,
        match="identity",
    ):
        identity_client.get_identity(
            access_token="access-token",
        )


# =====================================================================
# Verifies that an HTTP failure from the Google UserInfo endpoint is
# exposed as a controlled OAuth error.
# =====================================================================


def test_http_google_identity_client_maps_google_http_error(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "GET",
                "https://openidconnect.googleapis.com/v1/userinfo",
            )
            response = httpx.Response(
                401,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Google identity request failed",
                request=request,
                response=response,
            )

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.get",
        fake_get,
    )

    identity_client = HttpGoogleIdentityClient()

    with pytest.raises(
        GoogleOAuthError,
        match="identity",
    ):
        identity_client.get_identity(
            access_token="access-token",
        )


# =====================================================================
# Verifies that malformed JSON returned by the Google UserInfo endpoint
# is exposed as a controlled OAuth error.
# =====================================================================


def test_http_google_identity_client_rejects_malformed_json(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, str]:
            raise ValueError("Malformed JSON")

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.get",
        fake_get,
    )

    identity_client = HttpGoogleIdentityClient()

    with pytest.raises(
        GoogleOAuthError,
        match="identity",
    ):
        identity_client.get_identity(
            access_token="access-token",
        )
