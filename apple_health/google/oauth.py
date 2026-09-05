from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Protocol
from urllib.parse import urlencode

import httpx

from apple_health.google.sessions import SessionStore


class GoogleOAuthError(ValueError):
    pass


class GoogleOAuthStateError(GoogleOAuthError):
    pass


@dataclass(frozen=True)
class GoogleTokenResponse:
    access_token: str
    expires_in_seconds: int
    granted_scopes: frozenset[str]


class GoogleTokenClient(Protocol):
    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> GoogleTokenResponse: ...


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str


class GoogleIdentityClient(Protocol):
    def get_identity(
        self,
        access_token: str,
    ) -> GoogleIdentity: ...


class HttpGoogleIdentityClient:
    USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
    REQUEST_TIMEOUT = 10.0

    def get_identity(
        self,
        access_token: str,
    ) -> GoogleIdentity:
        try:
            response = httpx.get(
                self.USERINFO_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise GoogleOAuthError("Google identity request failed") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GoogleOAuthError("Google identity request failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleOAuthError("Google identity response is invalid") from exc

        if not isinstance(payload, dict):
            raise GoogleOAuthError("Google identity response is invalid")

        sub = payload.get("sub")
        email = payload.get("email")

        if not isinstance(sub, str) or not sub.strip():
            raise GoogleOAuthError("Google identity response is invalid")

        if not isinstance(email, str) or not email.strip():
            raise GoogleOAuthError("Google identity response is invalid")

        return GoogleIdentity(
            sub=sub,
            email=email,
        )


class HttpGoogleTokenClient:
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    REQUEST_TIMEOUT = 10.0

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> GoogleTokenResponse:
        try:
            response = httpx.post(
                self.TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise GoogleOAuthError("Google token exchange failed") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GoogleOAuthError("Google token exchange failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise GoogleOAuthError("Google token response is invalid") from exc

        if not isinstance(payload, dict):
            raise GoogleOAuthError("Google token response is invalid")

        access_token = payload.get("access_token")
        expires_in_seconds = payload.get("expires_in")
        scope = payload.get("scope")

        if not isinstance(access_token, str) or not access_token.strip():
            raise GoogleOAuthError("Google token response is invalid")

        if type(expires_in_seconds) is not int or expires_in_seconds <= 0:
            raise GoogleOAuthError("Google token response is invalid")

        if not isinstance(scope, str) or not scope.strip():
            raise GoogleOAuthError("Google token response is invalid")

        return GoogleTokenResponse(
            access_token=access_token,
            expires_in_seconds=expires_in_seconds,
            granted_scopes=frozenset(scope.split()),
        )


class GoogleOAuthService:
    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"

    SCOPES = (
        "openid",
        "email",
        "https://www.googleapis.com/auth/drive.file",
    )

    def __init__(
        self,
        client_id: str,
        redirect_uri: str,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def start(
        self,
        sessions: SessionStore,
        session_id: str,
    ) -> str:
        oauth_state = token_urlsafe(32)

        sessions.set_oauth_state(
            session_id,
            oauth_state,
        )

        parameters = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": " ".join(self.SCOPES),
                "state": oauth_state,
            }
        )

        return f"{self.AUTHORIZATION_ENDPOINT}?{parameters}"

    def validate_callback_state(
        self,
        sessions: SessionStore,
        session_id: str,
        returned_state: str,
    ) -> None:
        session = sessions.get(session_id)

        if session is None:
            raise GoogleOAuthError("OAuth session does not exist or has expired")

        if session.oauth_state != returned_state:
            raise GoogleOAuthStateError("OAuth state does not match")

        sessions.clear_oauth_state(session_id)

    def complete(
        self,
        sessions: SessionStore,
        session_id: str,
        returned_state: str,
        code: str,
        token_client: GoogleTokenClient,
        identity_client: GoogleIdentityClient,
    ) -> None:
        self.validate_callback_state(
            sessions=sessions,
            session_id=session_id,
            returned_state=returned_state,
        )

        if self._client_secret is None:
            raise GoogleOAuthError("Google OAuth client secret is not configured")

        token_response = token_client.exchange_code(
            code=code,
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=self._redirect_uri,
        )

        required_scopes = frozenset(self.SCOPES)

        if not required_scopes.issubset(token_response.granted_scopes):
            raise GoogleOAuthError("Google OAuth required scope was not granted")

        identity = identity_client.get_identity(
            token_response.access_token,
        )

        sessions.set_google_identity(
            session_id=session_id,
            google_sub=identity.sub,
            google_email=identity.email,
        )

        sessions.set_google_access_credentials(
            session_id=session_id,
            access_token=token_response.access_token,
            granted_scopes=token_response.granted_scopes,
            expires_in_seconds=token_response.expires_in_seconds,
        )
