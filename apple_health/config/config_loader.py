from pathlib import Path
import sys

from apple_health.config.exceptions import ConfigurationError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from apple_health.config.app_config import AppConfig
from apple_health.config.source_config import SourceConfig

_TOP_LEVEL_KEYS = {
    "source",
}

_SOURCE_KEYS = {
    "apple_watch_source",
    "apple_health_app_source",
}

class ConfigLoader:

    @staticmethod
    def load(
        path: Path | None,
    ) -> AppConfig:
        if path is None:
            return AppConfig()

        try:
            with path.open("rb") as config_file:
                data = ConfigLoader._normalize_keys(tomllib.load(config_file))
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Configuration file not found: {path}"
            ) from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(
                f"Invalid TOML configuration: {exc}"
            ) from exc

        ConfigLoader._validate_keys(
            data,
            _TOP_LEVEL_KEYS,
        )

        source_data = data.get("source", {})

        ConfigLoader._validate_keys(
            source_data,
            _SOURCE_KEYS,
            path="source",
        )

        source_config = SourceConfig(
            **source_data,
        )

        return AppConfig(
            source=source_config,
        )
        
    @staticmethod
    def _normalize_keys(
        data: dict,
    ) -> dict:
        return {
            key.lower(): (
                ConfigLoader._normalize_keys(value)
                if isinstance(value, dict)
                else value
            )
            for key, value in data.items()
        }
    
    @staticmethod
    def _validate_keys(
        data: dict,
        allowed_keys: set[str],
        path: str = "",
    ) -> None:
        for key in data:
            if key not in allowed_keys:
                full_path = f"{path}.{key}" if path else key

                raise ConfigurationError(
                    f"Unknown configuration field: {full_path}"
                )