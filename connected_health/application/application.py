"""Apple compatibility facade over the provider-neutral workflow."""

from datetime import UTC, datetime
from uuid import uuid4

from connected_health.analyzers.health_analyzer import HealthAnalyzer
from connected_health.application.effective_config_resolver import EffectiveConfigResolver
from connected_health.application.report_generation_application import ReportGenerationApplication
from connected_health.config.config_loader import ConfigLoader
from connected_health.providers.apple.provider import AppleHealthProvider
from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.renderers.text_renderer import TextRenderer


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _generation_id() -> str:
    return str(uuid4())


class AppleHealthApplication:
    """Retained Apple public entry point; owns only Apple wiring and configuration."""

    def __init__(self) -> None:
        self._workflow = ReportGenerationApplication(
            AppleHealthProvider(),
            analyzer_factory=HealthAnalyzer,
            text_renderer_factory=TextRenderer,
            json_renderer_factory=JsonRenderer,
            generation_id_factory=_generation_id,
            now_factory=_utc_now,
        )

    def run(self, options):
        config = ConfigLoader.load(options.config_path)
        return self._workflow.run(
            options,
            provider_config=getattr(config, "provider", config),
            analysis_config=getattr(config, "analysis", config),
        )

    def generate_reports(self, options):
        config = EffectiveConfigResolver.resolve(
            uploaded_config_path=options.config_path,
            selected_drive_config=options.selected_drive_config,
            apple_watch_source=options.apple_watch_source,
            apple_health_app_source=options.apple_health_app_source,
        )
        return self._workflow.generate_reports(options, effective_config=config)
