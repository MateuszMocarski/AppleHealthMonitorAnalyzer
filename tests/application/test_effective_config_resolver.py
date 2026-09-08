from pathlib import Path

from apple_health.application.effective_config_resolver import (
    EffectiveConfigResolver,
)
from apple_health.config.app_config import AppConfig
from apple_health.config.source_config import SourceConfig


def _write_config(
    tmp_path: Path,
    content: str,
) -> Path:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        content,
        encoding="utf-8",
    )
    return config_path


# =====================================================================
# Verifies that an uploaded configuration replaces the selected Drive
# configuration as the single base source instead of layering both.
# =====================================================================


def test_uploaded_config_replaces_selected_drive_config(
    tmp_path: Path,
) -> None:
    uploaded_config_path = _write_config(
        tmp_path,
        """
        [sleep]
        session_gap_threshold_minutes = 45
        """,
    )
    selected_drive_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Drive Watch",
            apple_health_app_source="Drive Health",
        ),
    )

    config = EffectiveConfigResolver.resolve(
        uploaded_config_path=uploaded_config_path,
        selected_drive_config=selected_drive_config,
    )

    assert config.sleep.session_gap_threshold_minutes == 45
    assert config.source == SourceConfig()


# =====================================================================
# Verifies that the selected Drive configuration is used as the base
# configuration when no uploaded configuration is provided.
# =====================================================================


def test_selected_drive_config_is_used_when_upload_missing() -> None:
    selected_drive_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Drive Watch",
            apple_health_app_source="Drive Health",
        ),
    )

    config = EffectiveConfigResolver.resolve(
        selected_drive_config=selected_drive_config,
    )

    assert config == selected_drive_config


# =====================================================================
# Verifies that application defaults are used when no uploaded or
# selected Drive configuration is available.
# =====================================================================


def test_defaults_are_used_when_no_base_config_is_provided() -> None:
    config = EffectiveConfigResolver.resolve()

    assert config == AppConfig()


# =====================================================================
# Verifies that runtime source overrides take precedence over values
# loaded from an uploaded configuration.
# =====================================================================


def test_source_overrides_replace_uploaded_config_values(
    tmp_path: Path,
) -> None:
    uploaded_config_path = _write_config(
        tmp_path,
        """
        [source]
        apple_watch_source = "Uploaded Watch"
        apple_health_app_source = "Uploaded Health"
        """,
    )

    config = EffectiveConfigResolver.resolve(
        uploaded_config_path=uploaded_config_path,
        apple_watch_source="UI Watch",
        apple_health_app_source="UI Health",
    )

    assert config.source.apple_watch_source == "UI Watch"
    assert config.source.apple_health_app_source == "UI Health"


# =====================================================================
# Verifies that runtime source overrides take precedence over a selected
# Drive configuration without mutating the saved profile configuration.
# =====================================================================


def test_source_overrides_replace_selected_drive_config_without_mutation() -> None:
    selected_drive_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Drive Watch",
            apple_health_app_source="Drive Health",
        ),
    )

    config = EffectiveConfigResolver.resolve(
        selected_drive_config=selected_drive_config,
        apple_watch_source="UI Watch",
    )

    assert config.source.apple_watch_source == "UI Watch"
    assert config.source.apple_health_app_source == "Drive Health"

    assert selected_drive_config.source.apple_watch_source == "Drive Watch"
    assert selected_drive_config.source.apple_health_app_source == "Drive Health"


# =====================================================================
# Verifies that runtime source overrides take precedence over built-in
# defaults when no uploaded or Drive configuration is selected.
# =====================================================================


def test_source_overrides_replace_default_config_values() -> None:
    config = EffectiveConfigResolver.resolve(
        apple_watch_source="UI Watch",
        apple_health_app_source="UI Health",
    )

    assert config.source.apple_watch_source == "UI Watch"
    assert config.source.apple_health_app_source == "UI Health"
