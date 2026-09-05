from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe


@dataclass(frozen=True)
class Session:
    session_id: str
    expires_at: datetime
    oauth_state: str | None = None
    google_access_token: str | None = None
    google_sub: str | None = None
    google_email: str | None = None
    google_granted_scopes: frozenset[str] | None = None
    google_access_token_expires_at: datetime | None = None


@dataclass(frozen=True)
class SessionCookieSettings:
    name: str
    http_only: bool
    secure: bool
    same_site: str

    @classmethod
    def for_environment(cls, environment: str) -> "SessionCookieSettings":
        if environment not in {"development", "production"}:
            raise ValueError(f"Unsupported application environment: {environment}")

        return cls(
            name="ahm_session",
            http_only=True,
            secure=environment == "production",
            same_site="lax",
        )


class SessionStore:
    SESSION_TTL = timedelta(hours=8)

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def create(self) -> str:
        session_id = token_urlsafe(32)
        expires_at = self._clock() + self.SESSION_TTL

        self._sessions[session_id] = Session(
            session_id=session_id,
            expires_at=expires_at,
        )

        return session_id

    def get(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)

        if session is None:
            return None

        if self._clock() >= session.expires_at:
            self.delete(session_id)
            return None

        return session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def set_oauth_state(
        self,
        session_id: str,
        oauth_state: str,
    ) -> None:
        session = self.get(session_id)

        if session is None:
            raise ValueError("Session does not exist or has expired")

        self._sessions[session_id] = replace(
            session,
            oauth_state=oauth_state,
        )

    def clear_oauth_state(self, session_id: str) -> None:
        session = self.get(session_id)

        if session is None:
            raise ValueError("Session does not exist or has expired")

        self._sessions[session_id] = replace(
            session,
            oauth_state=None,
        )

    def set_google_identity(
        self,
        session_id: str,
        google_sub: str,
        google_email: str,
    ) -> None:
        session = self.get(session_id)

        if session is None:
            raise ValueError("Session does not exist or has expired")

        self._sessions[session_id] = replace(
            session,
            google_sub=google_sub,
            google_email=google_email,
        )

    def set_google_access_credentials(
        self,
        session_id: str,
        access_token: str,
        granted_scopes: frozenset[str],
        expires_in_seconds: int,
    ) -> None:
        session = self.get(session_id)

        if session is None:
            raise ValueError("Session does not exist or has expired")

        self._sessions[session_id] = replace(
            session,
            google_access_token=access_token,
            google_granted_scopes=granted_scopes,
            google_access_token_expires_at=(self._clock() + timedelta(seconds=expires_in_seconds)),
        )

    def is_google_mode_ready(
        self,
        session_id: str,
        required_scopes: frozenset[str],
    ) -> bool:
        session = self.get(session_id)

        if session is None:
            return False

        if session.google_sub is None or session.google_email is None:
            return False

        if session.google_access_token is None:
            return False

        if session.google_granted_scopes is None:
            return False

        if session.google_access_token_expires_at is None:
            return False

        if not required_scopes.issubset(session.google_granted_scopes):
            return False

        if self._clock() >= session.google_access_token_expires_at:
            return False

        return True
