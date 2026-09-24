import hashlib
import json

from connected_health.config.app_config import AppConfig


def _render_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_float(value: float) -> str:
    return str(float(value))


class TomlRenderer:
    @staticmethod
    def render(config: AppConfig) -> str:
        linear_penalties = str(config.sleep.score.linear_penalties).lower()
        monthly_bonus_enabled = str(config.sleep.score.monthly_bonus.enabled).lower()
        average_thresholds = ", ".join(
            f"[{float(threshold)}, {float(bonus)}]"
            for threshold, bonus in config.sleep.score.monthly_bonus.average_thresholds
        )
        consistency_thresholds = ", ".join(
            f"[{float(threshold)}, {float(bonus)}]"
            for threshold, bonus in config.sleep.score.monthly_bonus.consistency_thresholds
        )

        return (
            "[source]\n"
            f"apple_watch_source = {_render_string(config.source.apple_watch_source)}\n"
            f"apple_health_app_source = "
            f"{_render_string(config.source.apple_health_app_source)}\n"
            "\n"
            "[sleep]\n"
            f"session_gap_threshold_minutes = "
            f"{config.sleep.session_gap_threshold_minutes}\n"
            "\n"
            "[sleep.score]\n"
            f"linear_penalties = {linear_penalties}\n"
            "\n"
            "[sleep.score.bedtime]\n"
            f'target = "{config.sleep.score.bedtime.target.strftime("%H:%M")}"\n'
            f"penalty_interval_minutes = "
            f"{config.sleep.score.bedtime.penalty_interval_minutes}\n"
            f"penalty_points = {_render_float(config.sleep.score.bedtime.penalty_points)}\n"
            "\n"
            "[sleep.score.duration]\n"
            f"target_minutes = {config.sleep.score.duration.target_minutes}\n"
            f"tolerance_minutes = {config.sleep.score.duration.tolerance_minutes}\n"
            f"penalty_interval_minutes = "
            f"{config.sleep.score.duration.penalty_interval_minutes}\n"
            f"penalty_points = {_render_float(config.sleep.score.duration.penalty_points)}\n"
            f"oversleep_weight = {_render_float(config.sleep.score.duration.oversleep_weight)}\n"
            f"undersleep_weight = {_render_float(config.sleep.score.duration.undersleep_weight)}\n"
            "\n"
            "[sleep.score.wake_up]\n"
            f'target = "{config.sleep.score.wake_up.target.strftime("%H:%M")}"\n'
            f"bedtime_weight = {_render_float(config.sleep.score.wake_up.bedtime_weight)}\n"
            f"duration_weight = {_render_float(config.sleep.score.wake_up.duration_weight)}\n"
            f"penalty_interval_minutes = "
            f"{config.sleep.score.wake_up.penalty_interval_minutes}\n"
            f"penalty_points = {_render_float(config.sleep.score.wake_up.penalty_points)}\n"
            "\n"
            "[sleep.score.weights]\n"
            f"bedtime = {_render_float(config.sleep.score.weights.bedtime)}\n"
            f"duration = {_render_float(config.sleep.score.weights.duration)}\n"
            f"wake_up = {_render_float(config.sleep.score.weights.wake_up)}\n"
            "\n"
            "[sleep.score.monthly_bonus]\n"
            f"enabled = {monthly_bonus_enabled}\n"
            f"max_points = {config.sleep.score.monthly_bonus.max_points}\n"
            f"average_thresholds = [{average_thresholds}]\n"
            f"consistency_thresholds = [{consistency_thresholds}]\n"
        )


def semantic_fingerprint(config: AppConfig) -> str:
    canonical_toml = TomlRenderer.render(config)

    return hashlib.sha256(canonical_toml.encode("utf-8")).hexdigest()
