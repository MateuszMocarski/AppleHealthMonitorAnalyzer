import ast
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

from apple_health.analyzers.health_analyzer import HealthAnalyzer
from apple_health.application.presentation import PresentationContext
from apple_health.config.analysis_config import AnalysisConfig
from apple_health.enums import SleepStage, WorkoutType
from apple_health.models import DailyMetrics, HealthData, SleepRecord, Workout
from apple_health.providers.contract import DatasetProvenance, LoadedHealthData
from apple_health.renderers.json_renderer import JsonRenderer
from apple_health.renderers.text_renderer import TextRenderer


def test_shared_layers_do_not_import_apple_provider_implementation() -> None:
    shared_files = [
        *Path("apple_health/analyzers").glob("*.py"),
        *Path("apple_health/renderers").glob("*.py"),
        Path("apple_health/report_models.py"),
    ]
    forbidden = ("apple_health.providers.apple", "apple_health.parser", "apple_health.importer")

    for path in shared_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(name.startswith(forbidden) for name in imports), path


def test_canonical_models_exclude_apple_raw_fields() -> None:
    forbidden = {"apple_activity_type", "source_name", "source_version"}
    assert not (forbidden & {field.name for field in fields(Workout)})
    assert not (forbidden & {field.name for field in fields(SleepRecord)})
    assert not any("HK" in field.name for field in fields(HealthData))


def test_fake_provider_data_reaches_shared_pipeline_independent_of_provenance() -> None:
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

    loaded = FakeProvider().load(Path("fixture"), config=object())
    summary = HealthAnalyzer(loaded.data, AnalysisConfig()).summarize_month(2026, 8)
    text = TextRenderer(
        presentation=PresentationContext("Fake Health Monthly Report")
    ).render_month(summary)
    payload = JsonRenderer().render_month(summary)

    assert "Fake Health Monthly Report" in text
    assert '"schema_version": "1.0"' in payload
    assert summary == HealthAnalyzer(loaded.data, AnalysisConfig()).summarize_month(2026, 8)
