import sys
from datetime import time
from pathlib import Path
from typing import Any

from apple_health.config.app_config import AppConfig
from apple_health.config.exceptions import ConfigurationError
from apple_health.config.sleep_config import SleepConfig
from apple_health.config.sleep_score_config import (
    BedtimeScoreConfig,
    MonthlySleepBonusConfig,
    SleepDurationScoreConfig,
    SleepScoreConfig,
    SleepScoreWeightsConfig,
    WakeUpScoreConfig,
)
from apple_health.config.source_config import SourceConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


_TOP_LEVEL_KEYS = {"source", "sleep"}

_SOURCE_KEYS = {
    "apple_watch_source",
    "apple_health_app_source",
}

_SLEEP_KEYS = {
    "session_gap_threshold_minutes",
    "score",
}

_SLEEP_SCORE_KEYS = {
    "linear_penalties",
    "bedtime",
    "duration",
    "wake_up",
    "weights",
    "monthly_bonus",
}

_BEDTIME_KEYS = {
    "target",
    "penalty_interval_minutes",
    "penalty_points",
}

_DURATION_KEYS = {
    "target_minutes",
    "tolerance_minutes",
    "penalty_interval_minutes",
    "penalty_points",
    "oversleep_weight",
    "undersleep_weight",
}

_WAKE_UP_KEYS = {
    "target",
    "bedtime_weight",
    "duration_weight",
    "penalty_interval_minutes",
    "penalty_points",
}

_SCORE_WEIGHT_KEYS = {
    "bedtime",
    "duration",
    "wake_up",
}

_MONTHLY_BONUS_KEYS = {
    "enabled",
    "max_points",
    "average_thresholds",
    "consistency_thresholds",
}


class ConfigLoader:
    @staticmethod
    def load(path: Path | None) -> AppConfig:
        if path is None:
            config = AppConfig()
            ConfigLoader._validate_config(config)
            return config

        data = ConfigLoader._load_toml(path)

        ConfigLoader._validate_keys(
            data,
            _TOP_LEVEL_KEYS,
        )

        app_kwargs: dict[str, Any] = {}

        if "source" in data:
            app_kwargs["source"] = ConfigLoader._build_source_config(
                data["source"],
            )

        if "sleep" in data:
            app_kwargs["sleep"] = ConfigLoader._build_sleep_config(
                data["sleep"],
            )

        config = AppConfig(
            **app_kwargs,
        )

        ConfigLoader._validate_config(config)

        return config

    @staticmethod
    def _load_toml(path: Path) -> dict[str, Any]:
        try:
            with path.open("rb") as config_file:
                data = tomllib.load(config_file)
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Configuration file not found: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(f"Invalid TOML configuration: {exc}") from exc
        except OSError as exc:
            raise ConfigurationError(f"Could not read configuration file: {path}") from exc

        return ConfigLoader._normalize_keys(data)

    @staticmethod
    def _build_source_config(data: Any) -> SourceConfig:
        path = "source"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _SOURCE_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        if "apple_watch_source" in section:
            kwargs["apple_watch_source"] = ConfigLoader._require_string(
                section["apple_watch_source"],
                f"{path}.apple_watch_source",
            )

        if "apple_health_app_source" in section:
            kwargs["apple_health_app_source"] = ConfigLoader._require_string(
                section["apple_health_app_source"],
                f"{path}.apple_health_app_source",
            )

        return SourceConfig(
            **kwargs,
        )

    @staticmethod
    def _build_sleep_config(data: Any) -> SleepConfig:
        path = "sleep"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _SLEEP_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        if "session_gap_threshold_minutes" in section:
            kwargs["session_gap_threshold_minutes"] = ConfigLoader._coerce_int(
                section["session_gap_threshold_minutes"],
                f"{path}.session_gap_threshold_minutes",
            )

        if "score" in section:
            kwargs["score"] = ConfigLoader._build_sleep_score_config(
                section["score"],
            )

        return SleepConfig(
            **kwargs,
        )

    @staticmethod
    def _build_sleep_score_config(data: Any) -> SleepScoreConfig:
        path = "sleep.score"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _SLEEP_SCORE_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        if "linear_penalties" in section:
            kwargs["linear_penalties"] = ConfigLoader._require_bool(
                section["linear_penalties"],
                f"{path}.linear_penalties",
            )

        if "bedtime" in section:
            kwargs["bedtime"] = ConfigLoader._build_bedtime_config(
                section["bedtime"],
            )

        if "duration" in section:
            kwargs["duration"] = ConfigLoader._build_duration_config(
                section["duration"],
            )

        if "wake_up" in section:
            kwargs["wake_up"] = ConfigLoader._build_wake_up_config(
                section["wake_up"],
            )

        if "weights" in section:
            kwargs["weights"] = ConfigLoader._build_score_weights_config(
                section["weights"],
            )

        if "monthly_bonus" in section:
            kwargs["monthly_bonus"] = ConfigLoader._build_monthly_bonus_config(
                section["monthly_bonus"],
            )

        return SleepScoreConfig(
            **kwargs,
        )

    @staticmethod
    def _build_bedtime_config(data: Any) -> BedtimeScoreConfig:
        path = "sleep.score.bedtime"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _BEDTIME_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        if "target" in section:
            kwargs["target"] = ConfigLoader._parse_time(
                section["target"],
                f"{path}.target",
            )

        if "penalty_interval_minutes" in section:
            kwargs["penalty_interval_minutes"] = ConfigLoader._coerce_int(
                section["penalty_interval_minutes"],
                f"{path}.penalty_interval_minutes",
            )

        if "penalty_points" in section:
            kwargs["penalty_points"] = ConfigLoader._coerce_float(
                section["penalty_points"],
                f"{path}.penalty_points",
            )

        return BedtimeScoreConfig(
            **kwargs,
        )

    @staticmethod
    def _build_duration_config(data: Any) -> SleepDurationScoreConfig:
        path = "sleep.score.duration"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _DURATION_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        for field_name in (
            "target_minutes",
            "tolerance_minutes",
            "penalty_interval_minutes",
        ):
            if field_name in section:
                kwargs[field_name] = ConfigLoader._coerce_int(
                    section[field_name],
                    f"{path}.{field_name}",
                )

        for field_name in (
            "penalty_points",
            "oversleep_weight",
            "undersleep_weight",
        ):
            if field_name in section:
                kwargs[field_name] = ConfigLoader._coerce_float(
                    section[field_name],
                    f"{path}.{field_name}",
                )

        return SleepDurationScoreConfig(
            **kwargs,
        )

    @staticmethod
    def _build_wake_up_config(data: Any) -> WakeUpScoreConfig:
        path = "sleep.score.wake_up"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _WAKE_UP_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        if "target" in section:
            kwargs["target"] = ConfigLoader._parse_time(
                section["target"],
                f"{path}.target",
            )

        if "penalty_interval_minutes" in section:
            kwargs["penalty_interval_minutes"] = ConfigLoader._coerce_int(
                section["penalty_interval_minutes"],
                f"{path}.penalty_interval_minutes",
            )

        for field_name in (
            "bedtime_weight",
            "duration_weight",
            "penalty_points",
        ):
            if field_name in section:
                kwargs[field_name] = ConfigLoader._coerce_float(
                    section[field_name],
                    f"{path}.{field_name}",
                )

        return WakeUpScoreConfig(
            **kwargs,
        )

    @staticmethod
    def _build_score_weights_config(data: Any) -> SleepScoreWeightsConfig:
        path = "sleep.score.weights"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _SCORE_WEIGHT_KEYS,
            path=path,
        )

        kwargs = {
            field_name: ConfigLoader._coerce_float(
                value,
                f"{path}.{field_name}",
            )
            for field_name, value in section.items()
        }

        return SleepScoreWeightsConfig(
            **kwargs,
        )

    @staticmethod
    def _build_monthly_bonus_config(data: Any) -> MonthlySleepBonusConfig:
        path = "sleep.score.monthly_bonus"
        section = ConfigLoader._require_section(data, path)

        ConfigLoader._validate_keys(
            section,
            _MONTHLY_BONUS_KEYS,
            path=path,
        )

        kwargs: dict[str, Any] = {}

        if "enabled" in section:
            kwargs["enabled"] = ConfigLoader._require_bool(
                section["enabled"],
                f"{path}.enabled",
            )

        if "max_points" in section:
            kwargs["max_points"] = ConfigLoader._coerce_int(
                section["max_points"],
                f"{path}.max_points",
            )

        if "average_thresholds" in section:
            kwargs["average_thresholds"] = ConfigLoader._parse_thresholds(
                section["average_thresholds"],
                f"{path}.average_thresholds",
            )

        if "consistency_thresholds" in section:
            kwargs["consistency_thresholds"] = ConfigLoader._parse_thresholds(
                section["consistency_thresholds"],
                f"{path}.consistency_thresholds",
            )

        return MonthlySleepBonusConfig(
            **kwargs,
        )

    @staticmethod
    def _normalize_keys(value: Any) -> Any:
        if isinstance(value, dict):
            normalized: dict[str, Any] = {}

            for key, nested_value in value.items():
                normalized_key = key.lower()

                if normalized_key in normalized:
                    raise ConfigurationError(
                        "Duplicate configuration field after case normalization: "
                        f"{normalized_key}"
                    )

                normalized[normalized_key] = ConfigLoader._normalize_keys(
                    nested_value,
                )

            return normalized

        if isinstance(value, list):
            return [ConfigLoader._normalize_keys(item) for item in value]

        return value

    @staticmethod
    def _validate_keys(
        data: dict[str, Any],
        allowed_keys: set[str],
        path: str = "",
    ) -> None:
        for key in data:
            if key not in allowed_keys:
                full_path = f"{path}.{key}" if path else key

                raise ConfigurationError(f"Unknown configuration field: {full_path}")

    @staticmethod
    def _require_section(
        value: Any,
        path: str,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ConfigurationError(
                f"Invalid configuration value: {path}. Expected a TOML section."
            )

        return value

    @staticmethod
    def _require_string(
        value: Any,
        path: str,
    ) -> str:
        if not isinstance(value, str):
            raise ConfigurationError(f"Invalid configuration value: {path}. Expected string.")

        return value

    @staticmethod
    def _require_bool(
        value: Any,
        path: str,
    ) -> bool:
        if not isinstance(value, bool):
            raise ConfigurationError(f"Invalid configuration value: {path}. Expected boolean.")

        return value

    @staticmethod
    def _coerce_int(
        value: Any,
        path: str,
    ) -> int:
        if isinstance(value, bool):
            raise ConfigurationError(f"Invalid configuration value: {path}. Expected integer.")

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass

        raise ConfigurationError(f"Invalid configuration value: {path}. Expected integer.")

    @staticmethod
    def _coerce_float(
        value: Any,
        path: str,
    ) -> float:
        if isinstance(value, bool):
            raise ConfigurationError(f"Invalid configuration value: {path}. Expected number.")

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass

        raise ConfigurationError(f"Invalid configuration value: {path}. Expected number.")

    @staticmethod
    def _parse_time(
        value: Any,
        path: str,
    ) -> time:
        if not isinstance(value, str) or len(value) != 5:
            raise ConfigurationError(
                f"Invalid configuration value: {path}. " "Expected time in HH:MM format."
            )

        try:
            parsed_time = time.fromisoformat(value)
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid configuration value: {path}. " "Expected time in HH:MM format."
            ) from exc

        if parsed_time.second != 0 or parsed_time.microsecond != 0:
            raise ConfigurationError(
                f"Invalid configuration value: {path}. " "Expected time in HH:MM format."
            )

        return parsed_time

    @staticmethod
    def _parse_thresholds(
        value: Any,
        path: str,
    ) -> tuple[tuple[float, float], ...]:
        if not isinstance(value, list):
            raise ConfigurationError(
                f"Invalid configuration value: {path}. "
                "Expected an array of [threshold, bonus] pairs."
            )

        parsed: list[tuple[float, float]] = []

        for index, pair in enumerate(value):
            item_path = f"{path}[{index}]"

            if not isinstance(pair, list) or len(pair) != 2:
                raise ConfigurationError(
                    f"Invalid configuration value: {item_path}. " "Expected [threshold, bonus]."
                )

            threshold = ConfigLoader._coerce_float(
                pair[0],
                f"{item_path}[0]",
            )
            bonus = ConfigLoader._coerce_float(
                pair[1],
                f"{item_path}[1]",
            )

            parsed.append(
                (
                    threshold,
                    bonus,
                )
            )

        return tuple(parsed)

    @staticmethod
    def _validate_config(
        config: AppConfig,
    ) -> None:
        try:
            config.validate()
        except ValueError as exc:
            raise ConfigurationError(f"Invalid configuration: {exc}") from exc
