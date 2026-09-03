from secrets import token_urlsafe
from urllib.parse import urlencode

from apple_health.google.sessions import SessionStore


class GoogleOAuthError(ValueError):
    pass


class GoogleOAuthService:
    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

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
            raise GoogleOAuthError("OAuth state does not match")

        sessions.clear_oauth_state(session_id)

    def exchange_code(
        self,
        code: str,
        exchange_token,
    ) -> str:
        if self._client_secret is None:
            raise GoogleOAuthError("Google OAuth client secret is not configured")

        return exchange_token(
            self.TOKEN_ENDPOINT,
            code=code,
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=self._redirect_uri,
            grant_type="authorization_code",
        )

    def complete(
        self,
        sessions: SessionStore,
        session_id: str,
        returned_state: str,
        code: str,
        exchange_token,
    ) -> None:
        self.validate_callback_state(
            sessions=sessions,
            session_id=session_id,
            returned_state=returned_state,
        )

        access_token = self.exchange_code(
            code=code,
            exchange_token=exchange_token,
        )

        sessions.set_google_access_token(
            session_id,
            access_token,
        )
