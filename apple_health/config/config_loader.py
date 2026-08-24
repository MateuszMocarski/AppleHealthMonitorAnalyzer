from pathlib import Path
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from apple_health.config.app_config import AppConfig
from apple_health.config.source_config import SourceConfig


class ConfigLoader:

    @staticmethod
    def load(
        path: Path | None,
    ) -> AppConfig:
        if path is None:
            return AppConfig()

        with path.open("rb") as config_file:
            data = tomllib.load(config_file)

        source_data = data.get("source", {})

        source_config = SourceConfig(
            **source_data,
        )

        return AppConfig(
            source=source_config,
        )