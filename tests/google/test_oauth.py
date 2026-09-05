from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from apple_health.google.oauth import (
    GoogleOAuthError,
    GoogleOAuthService,
    GoogleTokenResponse,
    HttpGoogleIdentityClient,
    HttpGoogleRevocationClient,
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
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(GoogleOAuthService.SCOPES),
            )

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


def test_complete_oauth_stores_access_credentials_in_session() -> None:
    current_time = datetime(
        2026,
        9,
        5,
        18,
        0,
        tzinfo=timezone.utc,
    )
    sessions = SessionStore(clock=lambda: current_time)
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
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(GoogleOAuthService.SCOPES),
            )

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
    assert session.google_granted_scopes == frozenset(GoogleOAuthService.SCOPES)
    assert session.google_access_token_expires_at == current_time + timedelta(
        seconds=3600,
    )


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
                "expires_in": 3600,
                "scope": ("openid email " "https://www.googleapis.com/auth/drive.file"),
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

    token_response = token_client.exchange_code(
        code="authorization-code",
        client_id="dev-client-id",
        client_secret="dev-client-secret",
        redirect_uri="http://localhost:8000/auth/google/callback",
    )

    assert token_response.access_token == "access-token"
    assert token_response.expires_in_seconds == 3600
    assert token_response.granted_scopes == frozenset(
        {
            "openid",
            "email",
            "https://www.googleapis.com/auth/drive.file",
        }
    )
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
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(GoogleOAuthService.SCOPES),
            )

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


# =====================================================================
# Verifies that Google token responses containing an invalid token
# lifetime are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "expires_in",
    [
        None,
        0,
        -1,
        True,
        "3600",
        3600.0,
    ],
)
def test_http_google_token_client_rejects_invalid_expires_in(
    monkeypatch,
    expires_in,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "access_token": "access-token",
                "expires_in": expires_in,
                "scope": ("openid email " "https://www.googleapis.com/auth/drive.file"),
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
# Verifies that Google token responses containing invalid granted scope
# metadata are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "scope",
    [
        None,
        "",
        "   ",
        123,
        ["openid", "email"],
    ],
)
def test_http_google_token_client_rejects_invalid_scope(
    monkeypatch,
    scope,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "access_token": "access-token",
                "expires_in": 3600,
                "scope": scope,
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
# Verifies that Google token responses missing required token metadata
# are rejected.
# =====================================================================


@pytest.mark.parametrize(
    "missing_field",
    [
        "expires_in",
        "scope",
    ],
)
def test_http_google_token_client_rejects_missing_token_metadata(
    monkeypatch,
    missing_field: str,
) -> None:
    payload: dict[str, object] = {
        "access_token": "access-token",
        "expires_in": 3600,
        "scope": ("openid email " "https://www.googleapis.com/auth/drive.file"),
    }
    payload.pop(missing_field)

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return payload

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
# Verifies that OAuth completion rejects a token response when Google
# did not grant every scope required by the application.
# =====================================================================


@pytest.mark.parametrize(
    "missing_scope",
    [
        "openid",
        "email",
        "https://www.googleapis.com/auth/drive.file",
    ],
)
def test_complete_oauth_rejects_missing_required_scope(
    missing_scope: str,
) -> None:
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

    granted_scopes = frozenset(
        scope for scope in GoogleOAuthService.SCOPES if scope != missing_scope
    )

    class FakeTokenClient:
        def exchange_code(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
        ) -> GoogleTokenResponse:
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=granted_scopes,
            )

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token,
        ) -> FakeIdentity:
            return FakeIdentity()

    with pytest.raises(
        GoogleOAuthError,
        match="scope",
    ):
        oauth.complete(
            sessions=sessions,
            session_id=session_id,
            returned_state=session.oauth_state,
            code="authorization-code",
            token_client=FakeTokenClient(),
            identity_client=FakeIdentityClient(),
        )


# =====================================================================
# Verifies that a network failure during Google token revocation is
# mapped to a controlled GoogleOAuthError.
# =====================================================================


def test_google_revocation_client_maps_network_failure(
    monkeypatch,
) -> None:
    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ):
        request = httpx.Request(
            "POST",
            url,
        )

        raise httpx.RequestError(
            "Network failure",
            request=request,
        )

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    revocation_client = HttpGoogleRevocationClient()

    with pytest.raises(
        GoogleOAuthError,
        match="revocation",
    ):
        revocation_client.revoke(
            "access-token",
        )


# =====================================================================
# Verifies that an HTTP failure during Google token revocation is
# mapped to a controlled GoogleOAuthError.
# =====================================================================


def test_google_revocation_client_maps_http_failure(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "POST",
                "https://oauth2.googleapis.com/revoke",
            )
            response = httpx.Response(
                400,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Google token revocation failed",
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

    revocation_client = HttpGoogleRevocationClient()

    with pytest.raises(
        GoogleOAuthError,
        match="revocation",
    ):
        revocation_client.revoke(
            "access-token",
        )


# =====================================================================
# Verifies that Google token revocation sends the access token to the
# configured revocation endpoint using the bounded request timeout.
# =====================================================================


def test_google_revocation_client_sends_expected_request(
    monkeypatch,
) -> None:
    captured_request: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        captured_request["url"] = url
        captured_request["data"] = data
        captured_request["timeout"] = timeout

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.oauth.httpx.post",
        fake_post,
    )

    revocation_client = HttpGoogleRevocationClient()

    revocation_client.revoke(
        "access-token",
    )

    assert captured_request == {
        "url": "https://oauth2.googleapis.com/revoke",
        "data": {
            "token": "access-token",
        },
        "timeout": 10.0,
    }


# =====================================================================
# Verifies that Google OAuth accepts the canonical userinfo.email scope
# as equivalent to the requested OpenID Connect email scope.
# =====================================================================


def test_complete_oauth_accepts_canonical_google_email_scope() -> None:
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
        ) -> GoogleTokenResponse:
            return GoogleTokenResponse(
                access_token="access-token",
                expires_in_seconds=3600,
                granted_scopes=frozenset(
                    {
                        "openid",
                        "https://www.googleapis.com/auth/userinfo.email",
                        "https://www.googleapis.com/auth/drive.file",
                    }
                ),
            )

    class FakeIdentity:
        sub = "google-user-123"
        email = "user@example.com"

    class FakeIdentityClient:
        def get_identity(
            self,
            access_token: str,
        ) -> FakeIdentity:
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
