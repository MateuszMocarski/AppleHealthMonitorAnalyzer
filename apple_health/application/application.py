from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.application.effective_config_resolver import (
    EffectiveConfigResolver,
)
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.presentation import PresentationContext
from apple_health.application.report_generation_metadata import ReportGenerationMetadata
from apple_health.application.report_generation_result import (
    ReportGenerationResult,
    ReportGenerationTimings,
)
from apple_health.application.run_options import RunOptions
from apple_health.config.config_loader import ConfigLoader
from apple_health.providers.apple.provider import AppleHealthProvider
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.renderers.text_renderer import TextRenderer


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _generation_id() -> str:
    return str(uuid4())


class AppleHealthApplication:
    def run(
        self,
        options: RunOptions,
    ) -> str:
        config = ConfigLoader.load(
            options.config_path,
        )

        loaded = AppleHealthProvider().load(
            options.archive_path,
            config=getattr(config, "provider", config),
        )
        health_data = loaded.data

        analyzer = HealthAnalyzer(
            health_data,
            config=getattr(config, "analysis", config),
        )

        summary = analyzer.summarize_month(
            year=options.year,
            month=options.month,
        )

        if options.output_format == "json":
            renderer = JsonRenderer(
                config=getattr(config, "analysis", config),
            )
        else:
            renderer = TextRenderer(
                config=getattr(config, "analysis", config),
                presentation=PresentationContext(
                    report_title=f"{loaded.provenance.display_label} Monthly Report"
                ),
            )

        if options.month_summary:
            return renderer.render_month_summary(
                summary,
            )

        return renderer.render_month(
            summary,
        )

    def generate_reports(
        self,
        options: MultiMonthRunOptions,
    ) -> ReportGenerationResult:

        config = EffectiveConfigResolver.resolve(
            uploaded_config_path=options.config_path,
            selected_drive_config=options.selected_drive_config,
            apple_watch_source=options.apple_watch_source,
            apple_health_app_source=options.apple_health_app_source,
        )

        xml_parse_started = perf_counter()
        loaded = AppleHealthProvider().load(
            options.archive_path,
            config=getattr(config, "provider", config),
        )
        health_data = loaded.data
        xml_parse_seconds = perf_counter() - xml_parse_started
        # The adapter owns the concrete archive-opening operation.  The legacy
        # timing field remains for response compatibility until provider timing
        # diagnostics are intentionally redesigned.
        archive_open_seconds = 0.0

        report_render_started = perf_counter()

        analyzer = HealthAnalyzer(
            health_data,
            config=getattr(config, "analysis", config),
        )

        text_renderer = TextRenderer(
            config=getattr(config, "analysis", config),
            presentation=PresentationContext(
                report_title=f"{loaded.provenance.display_label} Monthly Report"
            ),
        )

        json_renderer = JsonRenderer(
            config=getattr(config, "analysis", config),
        )

        reports = []

        for period in options.periods:
            summary = analyzer.summarize_month(
                year=period.year,
                month=period.month,
            )

            metadata = ReportGenerationMetadata(
                period=period,
                generation_id=_generation_id(),
                generated_at=_utc_now(),
            )

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
                    metadata=metadata,
                )
            )

        report_render_seconds = perf_counter() - report_render_started

        return ReportGenerationResult(
            reports=tuple(reports),
            effective_config=config,
            timings=ReportGenerationTimings(
                archive_open_seconds=(archive_open_seconds),
                xml_parse_seconds=(xml_parse_seconds),
                report_render_seconds=(report_render_seconds),
            ),
        )
