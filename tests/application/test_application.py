from contextlib import contextmanager
from pathlib import Path

from health_analyzer.application.application import HealthAnalyzerApplication
from health_analyzer.application.monthly_reports import MonthlyReports
from health_analyzer.application.multi_month_run_options import MultiMonthRunOptions
from health_analyzer.application.report_period import ReportPeriod
from health_analyzer.application.run_options import RunOptions

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
        "health_analyzer.application.application.ConfigLoader",
        FakeConfigLoader,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthParser",
        FakeParser,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.HealthAnalyzer",
        FakeAnalyzer,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.TextRenderer",
        FakeTextRenderer,
    )

    output = HealthAnalyzerApplication().run(
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
        "health_analyzer.application.application.ConfigLoader",
        FakeConfigLoader,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthParser",
        FakeParser,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.HealthAnalyzer",
        FakeAnalyzer,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    output = HealthAnalyzerApplication().run(
        options,
    )

    assert output == "json-summary"
    assert calls["config_path"] == Path("config.toml")
    assert calls["archive_path"] == Path("export.zip")
    assert calls["json_renderer"] is True
    assert calls["month_summary"] == "summary"


# =====================================================================
# Verifies that the application renders all four report variants for
# every requested reporting period.
# =====================================================================


def test_application_generates_all_report_variants_for_multiple_months(
    monkeypatch,
) -> None:
    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
            ReportPeriod(
                year=2026,
                month=9,
            ),
        ),
        config_path=None,
    )

    calls = {
        "parse_count": 0,
    }

    class FakeConfigLoader:
        @staticmethod
        def load(
            path,
            *,
            apple_watch_source=None,
            health_analyzer_app_source=None,
        ):
            return object()

    class FakeImporter:
        def __init__(self, path):
            pass

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            pass

        def parse(self):
            calls["parse_count"] += 1
            return "health-data"

    class FakeAnalyzer:
        def __init__(self, health_data, config):
            pass

        def summarize_month(self, year, month):
            return f"summary-{year}-{month}"

    class FakeTextRenderer:
        def __init__(self, config):
            pass

        def render_month(self, summary):
            return f"text-full:{summary}"

        def render_month_summary(self, summary):
            return f"text-summary:{summary}"

    class FakeJsonRenderer:
        def __init__(self, config):
            pass

        def render_month(self, summary):
            return f"json-full:{summary}"

        def render_month_summary(self, summary):
            return f"json-summary:{summary}"

    monkeypatch.setattr(
        "health_analyzer.application.application.ConfigLoader",
        FakeConfigLoader,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthParser",
        FakeParser,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.HealthAnalyzer",
        FakeAnalyzer,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.TextRenderer",
        FakeTextRenderer,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    reports = HealthAnalyzerApplication().generate_reports(
        options,
    )

    assert reports == [
        MonthlyReports(
            period=ReportPeriod(
                year=2026,
                month=8,
            ),
            full_text="text-full:summary-2026-8",
            full_json="json-full:summary-2026-8",
            summary_text="text-summary:summary-2026-8",
            summary_json="json-summary:summary-2026-8",
        ),
        MonthlyReports(
            period=ReportPeriod(
                year=2026,
                month=9,
            ),
            full_text="text-full:summary-2026-9",
            full_json="json-full:summary-2026-9",
            summary_text="text-summary:summary-2026-9",
            summary_json="json-summary:summary-2026-9",
        ),
    ]
    assert calls["parse_count"] == 1


# =====================================================================
# Verifies that multi-month report generation forwards runtime source
# overrides to configuration resolution before parsing the archive.
# =====================================================================


def test_generate_reports_forwards_source_overrides_to_config_loader(
    monkeypatch,
) -> None:
    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
        ),
        config_path=None,
        apple_watch_source="Custom Watch",
        health_analyzer_app_source="Custom Health",
    )

    calls = {}

    class FakeConfigLoader:
        @staticmethod
        def load(
            path,
            *,
            apple_watch_source=None,
            health_analyzer_app_source=None,
        ):
            calls["config_path"] = path
            calls["apple_watch_source"] = apple_watch_source
            calls["health_analyzer_app_source"] = health_analyzer_app_source
            return object()

    class FakeImporter:
        def __init__(self, path):
            pass

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

    class FakeTextRenderer:
        def __init__(self, config):
            pass

        def render_month(self, summary):
            return "full-text"

        def render_month_summary(self, summary):
            return "summary-text"

    class FakeJsonRenderer:
        def __init__(self, config):
            pass

        def render_month(self, summary):
            return "full-json"

        def render_month_summary(self, summary):
            return "summary-json"

    monkeypatch.setattr(
        "health_analyzer.application.application.ConfigLoader",
        FakeConfigLoader,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthImporter",
        FakeImporter,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.AppleHealthParser",
        FakeParser,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.HealthAnalyzer",
        FakeAnalyzer,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.TextRenderer",
        FakeTextRenderer,
    )
    monkeypatch.setattr(
        "health_analyzer.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    HealthAnalyzerApplication().generate_reports(options)

    assert calls == {
        "config_path": None,
        "apple_watch_source": "Custom Watch",
        "health_analyzer_app_source": "Custom Health",
    }
