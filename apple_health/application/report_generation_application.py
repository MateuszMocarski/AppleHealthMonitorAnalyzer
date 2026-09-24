"""Provider-neutral report-generation workflow."""

from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.report_generation_metadata import ReportGenerationMetadata
from apple_health.application.report_generation_result import (
    ReportGenerationResult,
    ReportGenerationTimings,
)
from apple_health.config.analysis_config import AnalysisConfig
from apple_health.providers.contract import HealthDataProvider, ProviderLoadDiagnostics
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.renderers.presentation import PresentationContext
from apple_health.renderers.text_renderer import TextRenderer


class ReportGenerationApplication:
    """Load one provider dataset, analyze once, then render every requested period."""

    def __init__(
        self,
        provider: HealthDataProvider,
        *,
        analyzer_factory=HealthAnalyzer,
        text_renderer_factory=TextRenderer,
        json_renderer_factory=JsonRenderer,
        generation_id_factory=lambda: str(uuid4()),
        now_factory=lambda: datetime.now(UTC),
    ) -> None:
        self.provider = provider
        self._analyzer_factory = analyzer_factory
        self._text_renderer_factory = text_renderer_factory
        self._json_renderer_factory = json_renderer_factory
        self._generation_id_factory = generation_id_factory
        self._now_factory = now_factory

    def run(self, options, *, provider_config: object, analysis_config: AnalysisConfig) -> str:
        loaded = self.provider.load(options.archive_path, config=provider_config)
        summary = self._analyzer_factory(loaded.data, analysis_config).summarize_month(
            options.year, options.month
        )
        if options.output_format == "json":
            renderer = self._json_renderer_factory(analysis_config)
        else:
            renderer = self._text_renderer_factory(
                analysis_config,
                PresentationContext(f"{loaded.provenance.display_label} Monthly Report"),
            )
        return (
            renderer.render_month_summary(summary)
            if options.month_summary
            else renderer.render_month(summary)
        )

    def generate_reports(self, options, *, effective_config) -> ReportGenerationResult:
        provider_config = getattr(effective_config, "provider", effective_config)
        analysis_config = getattr(effective_config, "analysis", effective_config)
        loaded = self.provider.load(options.archive_path, config=provider_config)
        render_started = perf_counter()
        analyzer = self._analyzer_factory(loaded.data, analysis_config)
        text_renderer = self._text_renderer_factory(
            analysis_config,
            PresentationContext(f"{loaded.provenance.display_label} Monthly Report"),
        )
        json_renderer = self._json_renderer_factory(analysis_config)
        reports = []
        for period in options.periods:
            summary = analyzer.summarize_month(period.year, period.month)
            reports.append(
                MonthlyReports(
                    period=period,
                    full_text=(
                        text_renderer.render_month(summary) if options.outputs.full_text else None
                    ),
                    full_json=(
                        json_renderer.render_month(summary) if options.outputs.full_json else None
                    ),
                    summary_text=(
                        text_renderer.render_month_summary(summary)
                        if options.outputs.summary_text
                        else None
                    ),
                    summary_json=(
                        json_renderer.render_month_summary(summary)
                        if options.outputs.summary_json
                        else None
                    ),
                    metadata=ReportGenerationMetadata(
                        period=period,
                        generation_id=self._generation_id_factory(),
                        generated_at=self._now_factory(),
                    ),
                )
            )
        return ReportGenerationResult(
            reports=tuple(reports),
            effective_config=effective_config,
            timings=ReportGenerationTimings(
                archive_open_seconds=getattr(
                    loaded, "diagnostics", ProviderLoadDiagnostics()
                ).archive_open_seconds,
                xml_parse_seconds=getattr(
                    loaded, "diagnostics", ProviderLoadDiagnostics()
                ).parse_seconds,
                report_render_seconds=perf_counter() - render_started,
            ),
        )
