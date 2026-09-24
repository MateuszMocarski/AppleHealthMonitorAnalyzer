from dataclasses import replace
from pathlib import Path

from connected_health.config.app_config import AppConfig
from connected_health.config.config_loader import ConfigLoader
from connected_health.config.exceptions import ConfigurationError
from connected_health.providers.apple.config import AppleProviderConfig


class EffectiveConfigResolver:
    @staticmethod
    def resolve(
        *,
        uploaded_config_path: Path | None = None,
        selected_drive_config: AppConfig | None = None,
        apple_watch_source: str | None = None,
        apple_health_app_source: str | None = None,
    ) -> AppConfig:
        if uploaded_config_path is not None:
            return ConfigLoader.load(
                uploaded_config_path,
                apple_watch_source=apple_watch_source,
                apple_health_app_source=apple_health_app_source,
            )

        if selected_drive_config is not None:
            return EffectiveConfigResolver._apply_source_overrides(
                selected_drive_config,
                apple_watch_source=apple_watch_source,
                apple_health_app_source=apple_health_app_source,
            )

        return ConfigLoader.load(
            None,
            apple_watch_source=apple_watch_source,
            apple_health_app_source=apple_health_app_source,
        )

    @staticmethod
    def _apply_source_overrides(
        config: AppConfig,
        *,
        apple_watch_source: str | None,
        apple_health_app_source: str | None,
    ) -> AppConfig:
        source = replace(config.source)

        if apple_watch_source is not None:
            source.apple_watch_source = apple_watch_source

        if apple_health_app_source is not None:
            source.apple_health_app_source = apple_health_app_source

        effective_config = AppConfig(
            analysis=config.analysis,
            provider=AppleProviderConfig(source=source),
        )

        try:
            effective_config.validate()
        except ValueError as exc:
            raise ConfigurationError(f"Invalid configuration: {exc}") from exc

        return effective_config
