from health_analyzer.analyzers.health_analyzer import HealthAnalyzer
from health_analyzer.application.monthly_reports import MonthlyReports
from health_analyzer.application.multi_month_run_options import MultiMonthRunOptions
from health_analyzer.application.run_options import RunOptions
from health_analyzer.config.config_loader import ConfigLoader
from health_analyzer.providers.apple.importer import AppleHealthImporter
from health_analyzer.providers.apple.parser import AppleHealthParser
from health_analyzer.renderers.json_renderer import JsonRenderer
from health_analyzer.renderers.text_renderer import TextRenderer


class HealthAnalyzerApplication:
    def run(
        self,
        options: RunOptions,
    ) -> str:
        config = ConfigLoader.load(
            options.config_path,
        )

        importer = AppleHealthImporter(
            options.archive_path,
        )

        with importer.open_export() as xml_stream:
            health_data = AppleHealthParser(
                xml_stream,
                config=config,
            ).parse()

        analyzer = HealthAnalyzer(
            health_data,
            config=config,
        )

        summary = analyzer.summarize_month(
            year=options.year,
            month=options.month,
        )

        if options.output_format == "json":
            renderer = JsonRenderer(
                config=config,
            )
        else:
            renderer = TextRenderer(
                config=config,
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
    ) -> list[MonthlyReports]:
        config = ConfigLoader.load(
            options.config_path,
            apple_watch_source=options.apple_watch_source,
            health_analyzer_app_source=options.health_analyzer_app_source,
        )

        importer = AppleHealthImporter(
            options.archive_path,
        )

        with importer.open_export() as xml_stream:
            health_data = AppleHealthParser(
                xml_stream,
                config=config,
            ).parse()

        analyzer = HealthAnalyzer(
            health_data,
            config=config,
        )

        text_renderer = TextRenderer(
            config=config,
        )
        json_renderer = JsonRenderer(
            config=config,
        )

        reports = []

        for period in options.periods:
            summary = analyzer.summarize_month(
                year=period.year,
                month=period.month,
            )

            reports.append(
                MonthlyReports(
                    period=period,
                    full_text=text_renderer.render_month(
                        summary,
                    ),
                    full_json=json_renderer.render_month(
                        summary,
                    ),
                    summary_text=text_renderer.render_month_summary(
                        summary,
                    ),
                    summary_json=json_renderer.render_month_summary(
                        summary,
                    ),
                )
            )

        return reports
