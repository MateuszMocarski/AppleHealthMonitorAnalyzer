import ast
import inspect
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

from connected_health.analyzers.health_analyzer import HealthAnalyzer
from connected_health.application.multi_month_run_options import MultiMonthRunOptions
from connected_health.application.report_generation_application import ReportGenerationApplication
from connected_health.application.report_outputs import ReportOutputs
from connected_health.application.report_period import ReportPeriod
from connected_health.config.analysis_config import AnalysisConfig
from connected_health.enums import SleepStage, WorkoutType
from connected_health.models import DailyMetrics, HealthData, SleepRecord, Workout
from connected_health.providers.contract import DatasetProvenance, LoadedHealthData


def test_shared_layers_do_not_import_provider_implementation_or_apple_input_code() -> None:
    shared_files = [
        *Path("connected_health/analyzers").glob("*.py"),
        *Path("connected_health/renderers").glob("*.py"),
        Path("connected_health/report_models.py"),
        Path("connected_health/application/report_generation_application.py"),
    ]
    forbidden = (
        "connected_health.providers.apple",
        "connected_health.parser",
        "connected_health.importer",
        "connected_health.constants",
        "connected_health.config.source_config",
        "connected_health.config.app_config",
        "connected_health.config.config_loader",
    )

    for path in shared_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
                imports.extend(f"{module}.{alias.name}" for alias in node.names if module)
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
        assert not any(name.startswith(forbidden) for name in imports), path


def test_canonical_models_exclude_apple_raw_fields() -> None:
    forbidden = {"apple_activity_type", "source_name", "source_version"}
    assert not (forbidden & {field.name for field in fields(Workout)})
    assert not (forbidden & {field.name for field in fields(SleepRecord)})
    assert not any("HK" in field.name for field in fields(HealthData))


def test_fake_provider_data_reaches_neutral_workflow_independent_of_provenance() -> None:
    class FakeProvider:
        provider_id = "fake"

        def __init__(self, provenance: DatasetProvenance) -> None:
            self.provenance = provenance

        def load(self, path: Path, *, config: object) -> LoadedHealthData:
            data = HealthData(
                workouts=[
                    Workout(
                        activity_type=WorkoutType.WALKING,
                        start=datetime(2026, 8, 2, tzinfo=UTC),
                        end=datetime(2026, 8, 2, 1, tzinfo=UTC),
                        duration_minutes=60,
                    )
                ],
                daily_metrics=[DailyMetrics(date=datetime(2026, 8, 2, tzinfo=UTC).date())],
                sleep_records=[
                    SleepRecord(
                        stage=SleepStage.CORE,
                        start=datetime(2026, 8, 1, 23, tzinfo=UTC),
                        end=datetime(2026, 8, 2, 6, tzinfo=UTC),
                        duration_minutes=420,
                    )
                ],
            )
            return LoadedHealthData(data, self.provenance)

    options = MultiMonthRunOptions(
        archive_path=Path("fixture"),
        periods=(ReportPeriod(2026, 8),),
        config_path=None,
        outputs=ReportOutputs(full_text=True, full_json=True),
    )
    config = type("Config", (), {"provider": object(), "analysis": AnalysisConfig()})()
    result = ReportGenerationApplication(
        FakeProvider(DatasetProvenance("fake", "Fake Health"))
    ).generate_reports(
        options,
        effective_config=config,
    )
    report = result.reports[0]

    assert "Fake Health Monthly Report" in report.full_text
    assert '"schema_version": "1.0"' in report.full_json
    first = (
        FakeProvider(DatasetProvenance("fake", "Fake Health"))
        .load(Path("fixture"), config=object())
        .data
    )
    second = LoadedHealthData(first, DatasetProvenance("other", "Other Health"))
    assert HealthAnalyzer(first, AnalysisConfig()).summarize_month(2026, 8) == HealthAnalyzer(
        second.data, AnalysisConfig()
    ).summarize_month(2026, 8)
    other_result = ReportGenerationApplication(
        FakeProvider(DatasetProvenance("other", "Other Health"))
    ).generate_reports(options, effective_config=config)
    assert report.full_json == other_result.reports[0].full_json
    assert "provenance" not in inspect.signature(HealthAnalyzer).parameters
