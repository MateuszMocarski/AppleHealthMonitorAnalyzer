import sys
from pathlib import Path
from typing import Any

from apple_health.application.run_profile import RunProfile
from apple_health.config.exceptions import ConfigurationError

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


_TOP_LEVEL_KEYS = {
    "run",
}

_RUN_KEYS = {
    "archive",
    "year",
    "month",
    "month_summary",
    "format",
    "config",
}


class RunProfileLoader:
    @staticmethod
    def load(
        path: Path,
    ) -> RunProfile:
        data = RunProfileLoader._load_toml(path)

        RunProfileLoader._validate_top_level_keys(
            data,
        )

        if "run" not in data:
            raise ConfigurationError(
                "Missing required configuration section: run"
            )

        run_data = data["run"]

        if not isinstance(run_data, dict):
            raise ConfigurationError(
                "Invalid configuration value: run. "
                "Expected a TOML section."
            )

        RunProfileLoader._validate_run_keys(
            run_data,
        )

        kwargs: dict[str, Any] = {}

        if "archive" in run_data:
            kwargs["archive_path"] = Path(
                RunProfileLoader._require_string(
                    run_data["archive"],
                    "run.archive",
                )
            )

        if "year" in run_data:
            kwargs["year"] = RunProfileLoader._coerce_int(
                run_data["year"],
                "run.year",
            )

        if "month" in run_data:
            kwargs["month"] = RunProfileLoader._coerce_int(
                run_data["month"],
                "run.month",
            )

        if "month_summary" in run_data:
            kwargs["month_summary"] = RunProfileLoader._require_bool(
                run_data["month_summary"],
                "run.month_summary",
            )

        if "format" in run_data:
            output_format = RunProfileLoader._require_string(
                run_data["format"],
                "run.format",
            ).lower()

            if output_format not in {
                "text",
                "json",
            }:
                raise ConfigurationError(
                    "Invalid configuration value: run.format. "
                    "Expected 'text' or 'json'."
                )

            kwargs["output_format"] = output_format

        if "config" in run_data:
            kwargs["config_path"] = Path(
                RunProfileLoader._require_string(
                    run_data["config"],
                    "run.config",
                )
            )

        return RunProfile(
            **kwargs,
        )

    @staticmethod
    def _load_toml(
        path: Path,
    ) -> dict[str, Any]:
        try:
            with path.open("rb") as profile_file:
                data = tomllib.load(profile_file)
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"Run profile file not found: {path}"
            ) from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(
                f"Invalid TOML run profile: {exc}"
            ) from exc
        except OSError as exc:
            raise ConfigurationError(
                f"Could not read run profile file: {path}"
            ) from exc

        return RunProfileLoader._normalize_keys(data)

    @staticmethod
    def _normalize_keys(
        value: Any,
    ) -> Any:
        if isinstance(value, dict):
            return {
                key.lower(): RunProfileLoader._normalize_keys(
                    nested_value
                )
                for key, nested_value in value.items()
            }

        if isinstance(value, list):
            return [
                RunProfileLoader._normalize_keys(item)
                for item in value
            ]

        return value

    @staticmethod
    def _validate_top_level_keys(
        data: dict[str, Any],
    ) -> None:
        for key in data:
            if key not in _TOP_LEVEL_KEYS:
                raise ConfigurationError(
                    f"Unknown run profile section: {key}"
                )

    @staticmethod
    def _validate_run_keys(
        data: dict[str, Any],
    ) -> None:
        for key in data:
            if key not in _RUN_KEYS:
                raise ConfigurationError(
                    f"Unknown run profile field: run.{key}"
                )

    @staticmethod
    def _require_string(
        value: Any,
        path: str,
    ) -> str:
        if not isinstance(value, str):
            raise ConfigurationError(
                f"Invalid configuration value: {path}. "
                "Expected string."
            )

        return value

    @staticmethod
    def _require_bool(
        value: Any,
        path: str,
    ) -> bool:
        if not isinstance(value, bool):
            raise ConfigurationError(
                f"Invalid configuration value: {path}. "
                "Expected boolean."
            )

        return value

    @staticmethod
    def _coerce_int(
        value: Any,
        path: str,
    ) -> int:
        if isinstance(value, bool):
            raise ConfigurationError(
                f"Invalid configuration value: {path}. "
                "Expected integer."
            )

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass

        raise ConfigurationError(
            f"Invalid configuration value: {path}. "
            "Expected integer."
        )
