from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe


@dataclass(frozen=True)
class Session:
    session_id: str
    expires_at: datetime


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
