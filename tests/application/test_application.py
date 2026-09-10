from contextlib import contextmanager
from pathlib import Path

from apple_health.application.application import AppleHealthApplication
from apple_health.application.monthly_reports import MonthlyReports
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_outputs import ReportOutputs
from apple_health.application.report_period import ReportPeriod
from apple_health.application.run_options import RunOptions
from apple_health.config.app_config import AppConfig
from apple_health.config.source_config import SourceConfig

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
        outputs=ReportOutputs(
            full_text=True,
            full_json=True,
            summary_text=True,
            summary_json=True,
        ),
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
            apple_health_app_source=None,
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
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    result = AppleHealthApplication().generate_reports(
        options,
    )

    assert result.reports == (
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
    )


# =====================================================================
# Verifies that multi-month report generation resolves the effective
# configuration from all base-source and runtime override inputs.
# =====================================================================


def test_generate_reports_resolves_effective_configuration(
    monkeypatch,
) -> None:
    selected_drive_config = AppConfig()

    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
        ),
        config_path=Path("config.toml"),
        selected_drive_config=selected_drive_config,
        apple_watch_source="Custom Watch",
        apple_health_app_source="Custom Health",
    )

    calls = {}
    effective_config = object()

    class FakeEffectiveConfigResolver:
        @staticmethod
        def resolve(
            *,
            uploaded_config_path=None,
            selected_drive_config=None,
            apple_watch_source=None,
            apple_health_app_source=None,
        ):
            calls["uploaded_config_path"] = uploaded_config_path
            calls["selected_drive_config"] = selected_drive_config
            calls["apple_watch_source"] = apple_watch_source
            calls["apple_health_app_source"] = apple_health_app_source
            return effective_config

    class FakeImporter:
        def __init__(self, path):
            pass

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            assert config is effective_config

        def parse(self):
            return "health-data"

    class FakeAnalyzer:
        def __init__(self, health_data, config):
            assert config is effective_config

        def summarize_month(self, year, month):
            return "summary"

    class FakeTextRenderer:
        def __init__(self, config):
            assert config is effective_config

        def render_month(self, summary):
            return "full-text"

        def render_month_summary(self, summary):
            return "summary-text"

    class FakeJsonRenderer:
        def __init__(self, config):
            assert config is effective_config

        def render_month(self, summary):
            return "full-json"

        def render_month_summary(self, summary):
            return "summary-json"

    monkeypatch.setattr(
        "apple_health.application.application.EffectiveConfigResolver",
        FakeEffectiveConfigResolver,
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
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    AppleHealthApplication().generate_reports(options)

    assert calls == {
        "uploaded_config_path": Path("config.toml"),
        "selected_drive_config": selected_drive_config,
        "apple_watch_source": "Custom Watch",
        "apple_health_app_source": "Custom Health",
    }


# =====================================================================
# Verifies that an uploaded configuration replaces the selected Drive
# configuration as the single base source during report generation.
# =====================================================================


def test_generate_reports_prefers_uploaded_config_over_selected_drive_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploaded_config_path = tmp_path / "config.toml"
    uploaded_config_path.write_text(
        "[sleep]\n" "session_gap_threshold_minutes = 45\n",
        encoding="utf-8",
    )

    selected_drive_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Drive Watch",
            apple_health_app_source="Drive Health",
        ),
    )

    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
        ),
        config_path=uploaded_config_path,
        selected_drive_config=selected_drive_config,
    )

    captured_config = None

    class FakeImporter:
        def __init__(self, path):
            pass

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            nonlocal captured_config
            captured_config = config

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
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    AppleHealthApplication().generate_reports(options)

    assert captured_config is not None
    assert captured_config.sleep.session_gap_threshold_minutes == 45
    assert captured_config.source == SourceConfig()


# =====================================================================
# Verifies that the selected Drive configuration is used during report
# generation when no uploaded configuration is provided.
# =====================================================================


def test_generate_reports_uses_selected_drive_config_when_upload_missing(
    monkeypatch,
) -> None:
    selected_drive_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Drive Watch",
            apple_health_app_source="Drive Health",
        ),
    )

    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
        ),
        config_path=None,
        selected_drive_config=selected_drive_config,
    )

    captured_config = None

    class FakeImporter:
        def __init__(self, path):
            pass

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            nonlocal captured_config
            captured_config = config

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
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    AppleHealthApplication().generate_reports(options)

    assert captured_config is not None
    assert captured_config.source.apple_watch_source == "Drive Watch"
    assert captured_config.source.apple_health_app_source == "Drive Health"


# =====================================================================
# Verifies that runtime source overrides take precedence over the
# selected Drive configuration during report generation.
# =====================================================================


def test_generate_reports_applies_source_overrides_to_selected_drive_config(
    monkeypatch,
) -> None:
    selected_drive_config = AppConfig(
        source=SourceConfig(
            apple_watch_source="Drive Watch",
            apple_health_app_source="Drive Health",
        ),
    )

    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(
            ReportPeriod(
                year=2026,
                month=8,
            ),
        ),
        config_path=None,
        selected_drive_config=selected_drive_config,
        apple_watch_source="UI Watch",
    )

    captured_config = None

    class FakeImporter:
        def __init__(self, path):
            pass

        @contextmanager
        def open_export(self):
            yield object()

    class FakeParser:
        def __init__(self, xml_stream, config):
            nonlocal captured_config
            captured_config = config

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
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    AppleHealthApplication().generate_reports(options)

    assert captured_config is not None
    assert captured_config.source.apple_watch_source == "UI Watch"
    assert captured_config.source.apple_health_app_source == "Drive Health"

    assert selected_drive_config.source.apple_watch_source == "Drive Watch"


# =====================================================================
# Verifies that multi-month generation exposes the effective
# configuration that was actually used for the report run.
# =====================================================================


def test_generate_reports_exposes_effective_config(
    monkeypatch,
) -> None:
    expected_config = AppConfig()

    options = MultiMonthRunOptions(
        archive_path=Path("export.zip"),
        periods=(),
        config_path=None,
    )

    monkeypatch.setattr(
        "apple_health.application.application.EffectiveConfigResolver.resolve",
        lambda **kwargs: expected_config,
    )

    class FakeImporter:
        def __init__(
            self,
            path,
        ):
            pass

        @contextmanager
        def open_export(
            self,
        ):
            yield object()

    class FakeParser:
        def __init__(
            self,
            xml_stream,
            config,
        ):
            assert config == expected_config

        def parse(
            self,
        ):
            return "health-data"

    class FakeAnalyzer:
        def __init__(
            self,
            health_data,
            config,
        ):
            assert config == expected_config

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

    result = AppleHealthApplication().generate_reports(
        options,
    )

    assert result.effective_config == expected_config


# =====================================================================
# Verifies that multi-month report generation renders only the report
# outputs selected in the run options.
# =====================================================================


def test_generate_reports_renders_only_selected_outputs(
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
    )

    calls = {
        "full_text": 0,
        "full_json": 0,
        "summary_text": 0,
        "summary_json": 0,
    }

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
            return f"summary-{year}-{month}"

    class FakeTextRenderer:
        def __init__(self, config):
            pass

        def render_month(self, summary):
            calls["full_text"] += 1
            return f"text-full:{summary}"

        def render_month_summary(self, summary):
            calls["summary_text"] += 1
            return f"text-summary:{summary}"

    class FakeJsonRenderer:
        def __init__(self, config):
            pass

        def render_month(self, summary):
            calls["full_json"] += 1
            return f"json-full:{summary}"

        def render_month_summary(self, summary):
            calls["summary_json"] += 1
            return f"json-summary:{summary}"

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
    monkeypatch.setattr(
        "apple_health.application.application.JsonRenderer",
        FakeJsonRenderer,
    )

    result = AppleHealthApplication().generate_reports(
        options,
    )

    report = result.reports[0]

    assert report.full_text is None
    assert report.full_json == "json-full:summary-2026-8"
    assert report.summary_text is None
    assert report.summary_json is None

    assert calls == {
        "full_text": 0,
        "full_json": 1,
        "summary_text": 0,
        "summary_json": 0,
    }
