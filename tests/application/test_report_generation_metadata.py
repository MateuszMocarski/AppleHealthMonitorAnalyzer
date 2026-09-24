from datetime import UTC, datetime

from apple_health.application.report_generation_metadata import (
    ReportGenerationMetadata,
)
from apple_health.application.report_period import ReportPeriod

# =====================================================================
# Verifies that monthly report generation metadata exposes canonical
# app properties for the month container and its report artifacts.
# =====================================================================


def test_report_generation_metadata_builds_drive_app_properties() -> None:
    metadata = ReportGenerationMetadata(
        period=ReportPeriod(
            year=2026,
            month=8,
        ),
        generation_id="generation-123",
        generated_at=datetime(
            2026,
            9,
            10,
            20,
            30,
            tzinfo=UTC,
        ),
    )

    assert metadata.month_app_properties() == {
        "ahm_type": "report_month",
        "ahm_period": "2026-08",
    }

    assert metadata.artifact_app_properties() == {
        "ahm_type": "report_artifact",
        "ahm_period": "2026-08",
        "ahm_generation_id": "generation-123",
        "ahm_generated_at": "2026-09-10T20:30:00Z",
    }
