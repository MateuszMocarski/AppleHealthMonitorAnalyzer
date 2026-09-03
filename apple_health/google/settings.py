import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse


class GoogleConfigurationError(ValueError):
    pass


def _get_required_environment_value(
    environment: Mapping[str, str],
    name: str,
) -> str:
    try:
        value = environment[name]
    except KeyError as exc:
        raise GoogleConfigurationError(f"Missing required environment variable: {name}") from exc

    if not value.strip():
        raise GoogleConfigurationError(f"Environment variable must not be blank: {name}")

    return value


def _get_application_environment(environment: Mapping[str, str]) -> str:
    value = _get_required_environment_value(environment, "AHM_ENV")

    if value not in {"development", "production"}:
        raise GoogleConfigurationError("AHM_ENV must be either 'development' or 'production'")

    return value


def _validate_redirect_uri(
    application_environment: str,
    redirect_uri: str,
) -> None:
    parsed = urlparse(redirect_uri)

    if not parsed.scheme or not parsed.netloc:
        raise GoogleConfigurationError("GOOGLE_REDIRECT_URI must be a valid absolute URL")

    if parsed.scheme not in {"http", "https"}:
        raise GoogleConfigurationError("GOOGLE_REDIRECT_URI must use HTTP or HTTPS")

    if application_environment == "production":
        if parsed.scheme != "https":
            raise GoogleConfigurationError("GOOGLE_REDIRECT_URI must use HTTPS in production")
        return

    if parsed.scheme == "http" and parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise GoogleConfigurationError(
            "GOOGLE_REDIRECT_URI may use HTTP only for localhost "
            "or a loopback address in development"
        )


def _get_cloud_project_number(environment: Mapping[str, str]) -> str:
    value = _get_required_environment_value(
        environment,
        "GOOGLE_CLOUD_PROJECT_NUMBER",
    )

    if not value.isascii() or not value.isdigit():
        raise GoogleConfigurationError("GOOGLE_CLOUD_PROJECT_NUMBER must contain digits only")

    return value


@dataclass(frozen=True)
class GoogleSettings:
    environment: str
    client_id: str
    client_secret: str
    redirect_uri: str
    picker_api_key: str
    cloud_project_number: str
    session_secret: str

    @classmethod
    def load(cls) -> "GoogleSettings":
        return cls.from_environment(os.environ)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "GoogleSettings":
        application_environment = _get_application_environment(environment)
        redirect_uri = _get_required_environment_value(
            environment,
            "GOOGLE_REDIRECT_URI",
        )

        _validate_redirect_uri(
            application_environment,
            redirect_uri,
        )

        return cls(
            environment=application_environment,
            client_id=_get_required_environment_value(
                environment,
                "GOOGLE_CLIENT_ID",
            ),
            client_secret=_get_required_environment_value(
                environment,
                "GOOGLE_CLIENT_SECRET",
            ),
            redirect_uri=redirect_uri,
            picker_api_key=_get_required_environment_value(
                environment,
                "GOOGLE_PICKER_API_KEY",
            ),
            cloud_project_number=_get_cloud_project_number(environment),
            session_secret=_get_required_environment_value(
                environment,
                "AHM_SESSION_SECRET",
            ),
        )
