"""Bounded loading of validated persisted Viewer reports."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from connected_health.google.drive import DriveClient
from connected_health.google.drive_structure import ViewerReportArtifact
from connected_health.viewer.report_contract import (
    PersistedReportValidationError,
    ReportKind,
    ViewerReport,
    parse_persisted_report,
)

# Full JSON reports contain at most one month of daily details.  Five MiB leaves
# generous room for the current JSON 1.0 contract while keeping Viewer downloads
# distinctly bounded from the 1 GiB Apple Health archive upload limit.
MAX_VIEWER_REPORT_JSON_SIZE_BYTES = 5 * 1024 * 1024


class ViewerReportLoadError(ValueError):
    """Raised when a persisted Viewer report cannot be safely opened."""


def load_viewer_report(
    drive_client: DriveClient,
    *,
    artifact: ViewerReportArtifact,
) -> ViewerReport:
    """Download and validate one already-authorized active Viewer artifact."""
    with TemporaryDirectory() as temporary_directory:
        report_path = Path(temporary_directory) / "report.json"

        drive_client.download_file(
            artifact.file_id,
            report_path,
            max_bytes=MAX_VIEWER_REPORT_JSON_SIZE_BYTES,
        )

        try:
            report = parse_persisted_report(
                report_path.read_bytes(),
                expected_kind=ReportKind(artifact.kind),
            )
        except (OSError, PersistedReportValidationError, ValueError) as error:
            raise ViewerReportLoadError("Persisted Viewer report is invalid.") from error

    report_period = f"{report.report.year}-{report.report.month:02d}"
    if report_period != artifact.period:
        raise ViewerReportLoadError("Persisted Viewer report does not match its artifact period.")

    return report
