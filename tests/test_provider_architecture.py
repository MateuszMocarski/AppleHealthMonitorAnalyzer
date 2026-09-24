import ast
import inspect
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.application.multi_month_run_options import MultiMonthRunOptions
from apple_health.application.report_generation_application import ReportGenerationApplication
from apple_health.application.report_outputs import ReportOutputs
from apple_health.application.report_period import ReportPeriod
from apple_health.config.analysis_config import AnalysisConfig
from apple_health.enums import SleepStage, WorkoutType
from apple_health.models import DailyMetrics, HealthData, SleepRecord, Workout
from apple_health.providers.contract import DatasetProvenance, LoadedHealthData


def test_shared_layers_do_not_import_provider_implementation_or_apple_input_code() -> None:
    shared_files = [
        *Path("apple_health/analyzers").glob("*.py"),
        *Path("apple_health/renderers").glob("*.py"),
        Path("apple_health/report_models.py"),
    ]
    forbidden = (
        "apple_health.providers.apple",
        "apple_health.parser",
        "apple_health.importer",
        "apple_health.constants",
        "apple_health.config.source_config",
    )

    for path in shared_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
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
            return LoadedHealthData(data, DatasetProvenance("fake", "Fake Health"))

    options = MultiMonthRunOptions(
        archive_path=Path("fixture"),
        periods=(ReportPeriod(2026, 8),),
        config_path=None,
        outputs=ReportOutputs(full_text=True, full_json=True),
    )
    result = ReportGenerationApplication(FakeProvider()).generate_reports(
        options,
        effective_config=type("Config", (), {"provider": object(), "analysis": AnalysisConfig()})(),
    )
    report = result.reports[0]

    assert "Fake Health Monthly Report" in report.full_text
    assert '"schema_version": "1.0"' in report.full_json
    first = FakeProvider().load(Path("fixture"), config=object()).data
    second = LoadedHealthData(first, DatasetProvenance("other", "Other Health"))
    assert HealthAnalyzer(first, AnalysisConfig()).summarize_month(2026, 8) == HealthAnalyzer(
        second.data, AnalysisConfig()
    ).summarize_month(2026, 8)
    assert "provenance" not in inspect.signature(HealthAnalyzer).parameters
