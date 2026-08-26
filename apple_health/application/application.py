from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.application.run_options import RunOptions
from apple_health.config.config_loader import ConfigLoader
from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.renderers.text_renderer import TextRenderer


class AppleHealthApplication:
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

        archive, xml_stream = importer.open_export()

        try:
            health_data = AppleHealthParser(
                xml_stream,
                config=config,
            ).parse()
        finally:
            xml_stream.close()
            archive.close()

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
