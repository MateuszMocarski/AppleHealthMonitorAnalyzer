from contextlib import contextmanager
from pathlib import Path

from apple_health.application.application import AppleHealthApplication
from apple_health.application.run_options import RunOptions

# =====================================================================
# Verifies that the application orchestrates a complete monthly text
# report using resolved run options and the shared application config.
# =====================================================================


def test_application_runs_monthly_text_report(
    monkeypatch,
) -> None:
    options = RunOptions(
        archive_path=Path("export.zip"),
        year=2026,
        month=8,
        month_summary=False,
        output_format="text",
        config_path=None,
    )

    calls = {}

    class FakeConfigLoader:
        @staticmethod
        def load(path):
            calls["config_path"] = path
            return object()

    class FakeImporter:
        def __init__(self, path):
            calls["archive_path"] = path

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            calls["parser_config"] = config

        def parse(self):
            return "health-data"

    class FakeAnalyzer:
        def __init__(self, health_data, config):
            calls["health_data"] = health_data
            calls["analyzer_config"] = config

        def summarize_month(self, year, month):
            calls["year"] = year
            calls["month"] = month
            return "summary"

    class FakeTextRenderer:
        def __init__(self, config):
            calls["renderer_config"] = config

        def render_month(self, summary):
            calls["summary"] = summary
            return "rendered-report"

    monkeypatch.setattr(
        "apple_health.application.application.ConfigLoader",
        FakeConfigLoader,
    )
    monkeypatch.setattr(
        "apple_health.application.application.AppleHealthImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "apple_health.application.application.AppleHealthParser",
        FakeParser,
    )
    monkeypatch.setattr(
        "apple_health.application.application.HealthAnalyzer",
        FakeAnalyzer,
    )
    monkeypatch.setattr(
        "apple_health.application.application.TextRenderer",
        FakeTextRenderer,
    )

    output = AppleHealthApplication().run(
        options,
    )

    assert output == "rendered-report"
    assert calls["config_path"] is None
    assert calls["archive_path"] == Path("export.zip")
    assert calls["health_data"] == "health-data"
    assert calls["year"] == 2026
    assert calls["month"] == 8
    assert calls["summary"] == "summary"


# =====================================================================
# Verifies that the application selects JsonRenderer and renders only
# the monthly summary when resolved run options request that behavior.
# =====================================================================


def test_application_runs_json_month_summary(
    monkeypatch,
) -> None:
    options = RunOptions(
        archive_path=Path("export.zip"),
        year=2026,
        month=8,
        month_summary=True,
        output_format="json",
        config_path=Path("config.toml"),
    )

    calls = {}

    class FakeConfigLoader:
        @staticmethod
        def load(path):
            calls["config_path"] = path
            return object()

    class FakeImporter:
        def __init__(self, path):
            calls["archive_path"] = path

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            pass

        def parse(self):
            return "health-data"

    class FakeAnalyzer:
        def __init__(self, health_data, config):
            pass

        def summarize_month(self, year, month):
            return "summary"

    class FakeJsonRenderer:
        def __init__(self, config):
            calls["json_renderer"] = True

        def render_month_summary(self, summary):
            calls["month_summary"] = summary
            return "json-summary"

        def render_month(self, summary):
            raise AssertionError("render_month should not be called")

    monkeypatch.setattr(
        "apple_health.application.application.ConfigLoader",
        FakeConfigLoader,
    )
    monkeypatch.setattr(
        "apple_health.application.application.AppleHealthImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "apple_health.application.application.AppleHealthParser",
        FakeParser,
    )
    monkeypatch.setattr(
        "apple_health.application.application.HealthAnalyzer",
        FakeAnalyzer,
    )
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    output = AppleHealthApplication().run(
        options,
    )

    assert output == "json-summary"
    assert calls["config_path"] == Path("config.toml")
    assert calls["archive_path"] == Path("export.zip")
    assert calls["json_renderer"] is True
    assert calls["month_summary"] == "summary"
