import pytest

from apple_health.google.settings import GoogleConfigurationError, GoogleSettings

# =====================================================================
# Verifies that Google settings are loaded from the configured
# environment values.
# =====================================================================


def test_google_settings_are_loaded_from_environment() -> None:
    settings = GoogleSettings.from_environment(
        {
            "AHM_ENV": "development",
            "GOOGLE_CLIENT_ID": "dev-client-id",
            "GOOGLE_CLIENT_SECRET": "dev-client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
            "GOOGLE_PICKER_API_KEY": "dev-picker-key",
            "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
            "AHM_SESSION_SECRET": "dev-session-secret",
        }
    )

    assert settings.environment == "development"
    assert settings.client_id == "dev-client-id"
    assert settings.client_secret == "dev-client-secret"
    assert settings.redirect_uri == "http://localhost:8000/auth/google/callback"
    assert settings.picker_api_key == "dev-picker-key"
    assert settings.cloud_project_number == "123456789"
    assert settings.session_secret == "dev-session-secret"


# =====================================================================
# Verifies that a missing required Google environment variable produces
# a controlled configuration error instead of leaking a raw KeyError.
# =====================================================================


def test_google_settings_reject_missing_required_environment_value() -> None:
    environment = {
        "AHM_ENV": "development",
        "GOOGLE_CLIENT_ID": "dev-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        # AHM_SESSION_SECRET intentionally missing.
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="AHM_SESSION_SECRET",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that a blank required Google environment value is rejected.
# =====================================================================


def test_google_settings_reject_blank_required_environment_value() -> None:
    environment = {
        "AHM_ENV": "development",
        "GOOGLE_CLIENT_ID": "   ",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "dev-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="GOOGLE_CLIENT_ID",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that an unsupported application environment is rejected.
# =====================================================================


def test_google_settings_reject_unsupported_application_environment() -> None:
    environment = {
        "AHM_ENV": "banana",
        "GOOGLE_CLIENT_ID": "dev-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "dev-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="AHM_ENV",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that production Google configuration requires an HTTPS
# redirect URI.
# =====================================================================


def test_google_settings_reject_non_https_production_redirect_uri() -> None:
    environment = {
        "AHM_ENV": "production",
        "GOOGLE_CLIENT_ID": "prod-client-id",
        "GOOGLE_CLIENT_SECRET": "prod-client-secret",
        "GOOGLE_REDIRECT_URI": "http://example.com/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "prod-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "prod-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="GOOGLE_REDIRECT_URI",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that the Google Cloud project number contains digits only.
# =====================================================================


def test_google_settings_reject_invalid_cloud_project_number() -> None:
    environment = {
        "AHM_ENV": "development",
        "GOOGLE_CLIENT_ID": "dev-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "not-a-number",
        "AHM_SESSION_SECRET": "dev-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="GOOGLE_CLOUD_PROJECT_NUMBER",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that Google settings can be loaded from the process
# environment.
# =====================================================================


def test_google_settings_load_from_process_environment(monkeypatch) -> None:
    monkeypatch.setenv("AHM_ENV", "development")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dev-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "dev-client-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )
    monkeypatch.setenv("GOOGLE_PICKER_API_KEY", "dev-picker-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_NUMBER", "123456789")
    monkeypatch.setenv("AHM_SESSION_SECRET", "dev-session-secret")

    settings = GoogleSettings.load()

    assert settings.environment == "development"
    assert settings.client_id == "dev-client-id"
    assert settings.client_secret == "dev-client-secret"
    assert settings.redirect_uri == "http://localhost:8000/auth/google/callback"
    assert settings.picker_api_key == "dev-picker-key"
    assert settings.cloud_project_number == "123456789"
    assert settings.session_secret == "dev-session-secret"


# =====================================================================
# Verifies that the Google redirect URI must be a valid absolute URL.
# =====================================================================


def test_google_settings_reject_invalid_redirect_uri() -> None:
    environment = {
        "AHM_ENV": "production",
        "GOOGLE_CLIENT_ID": "prod-client-id",
        "GOOGLE_CLIENT_SECRET": "prod-client-secret",
        "GOOGLE_REDIRECT_URI": "https://",
        "GOOGLE_PICKER_API_KEY": "prod-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "prod-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="GOOGLE_REDIRECT_URI",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that development Google configuration allows an HTTP
# localhost redirect URI.
# =====================================================================


def test_google_settings_allow_http_localhost_redirect_uri_in_development() -> None:
    environment = {
        "AHM_ENV": "development",
        "GOOGLE_CLIENT_ID": "dev-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "dev-session-secret",
    }

    settings = GoogleSettings.from_environment(environment)

    assert settings.redirect_uri == "http://localhost:8000/auth/google/callback"


# =====================================================================
# Verifies that development Google configuration rejects an HTTP
# redirect URI that does not point to localhost or a loopback address.
# =====================================================================


def test_google_settings_reject_non_local_http_redirect_uri_in_development() -> None:
    environment = {
        "AHM_ENV": "development",
        "GOOGLE_CLIENT_ID": "dev-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "http://example.com/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "dev-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="GOOGLE_REDIRECT_URI",
    ):
        GoogleSettings.from_environment(environment)


# =====================================================================
# Verifies that Google redirect URI rejects unsupported URL schemes.
# =====================================================================


def test_google_settings_reject_unsupported_redirect_uri_scheme() -> None:
    environment = {
        "AHM_ENV": "development",
        "GOOGLE_CLIENT_ID": "dev-client-id",
        "GOOGLE_CLIENT_SECRET": "dev-client-secret",
        "GOOGLE_REDIRECT_URI": "ftp://localhost/auth/google/callback",
        "GOOGLE_PICKER_API_KEY": "dev-picker-key",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "123456789",
        "AHM_SESSION_SECRET": "dev-session-secret",
    }

    with pytest.raises(
        GoogleConfigurationError,
        match="GOOGLE_REDIRECT_URI",
    ):
        GoogleSettings.from_environment(environment)
