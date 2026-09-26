from datetime import date
from pathlib import Path

import pytest

from connected_health.google.drive import DriveDownloadTooLargeError
from connected_health.google.drive_structure import ViewerReportArtifact
from connected_health.renderers.json_renderer import JsonRenderer
from connected_health.report_models import DailySummary, MonthlySummary
from connected_health.viewer.report_contract import FullReport, SummaryReport
from connected_health.viewer.report_loader import (
    MAX_VIEWER_REPORT_JSON_SIZE_BYTES,
    ViewerReportLoadError,
    load_viewer_report,
)


def _summary() -> MonthlySummary:
    return MonthlySummary(
        year=2026,
        month=8,
        reporting_days=1,
        days=[
            DailySummary(
                date=date(2026, 8, 1),
                activities=[],
                total_duration_minutes=0,
                total_active_energy_kcal=0,
                total_steps=None,
                total_distance_km=None,
                active_energy_kcal=None,
                basal_energy_kcal=None,
            )
        ],
        activities=[],
        activity_metrics=None,
        sleep_summary=None,
    )


def _artifact(kind: str = "summary", period: str = "2026-08") -> ViewerReportArtifact:
    return ViewerReportArtifact(
        file_id=f"{kind}-file-id",
        period=period,
        kind=kind,
        generation_id="generation-123",
        generated_at="2026-09-12T18:00:00Z",
    )


class _DriveDownloader:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.downloaded_file_ids: list[str] = []
        self.destination: Path | None = None
        self.max_bytes: int | None = None

    def download_file(self, file_id: str, destination: Path, *, max_bytes: int) -> int:
        self.downloaded_file_ids.append(file_id)
        self.destination = destination
        self.max_bytes = max_bytes
        destination.write_bytes(self.content)
        return len(self.content)


@pytest.mark.parametrize(
    ("kind", "content_type"),
    [("full", FullReport), ("summary", SummaryReport)],
)
def test_load_viewer_report_downloads_and_validates_active_json(
    kind: str, content_type: type[FullReport] | type[SummaryReport]
) -> None:
    summary = _summary()
    content = (
        JsonRenderer().render_month(summary)
        if kind == "full"
        else JsonRenderer().render_month_summary(summary)
    ).encode("utf-8")
    downloader = _DriveDownloader(content)

    report = load_viewer_report(downloader, artifact=_artifact(kind))

    assert isinstance(report, content_type)
    assert downloader.downloaded_file_ids == [f"{kind}-file-id"]
    assert downloader.max_bytes == MAX_VIEWER_REPORT_JSON_SIZE_BYTES
    assert downloader.destination is not None
    assert not downloader.destination.exists()


@pytest.mark.parametrize(
    "content",
    [b"{", b'{"schema_version":"2.0"}'],
)
def test_load_viewer_report_rejects_malformed_or_wrong_schema_json(content: bytes) -> None:
    with pytest.raises(ViewerReportLoadError):
        load_viewer_report(_DriveDownloader(content), artifact=_artifact())


def test_load_viewer_report_rejects_artifact_kind_mismatch() -> None:
    content = JsonRenderer().render_month_summary(_summary()).encode("utf-8")

    with pytest.raises(ViewerReportLoadError):
        load_viewer_report(_DriveDownloader(content), artifact=_artifact("full"))


def test_load_viewer_report_rejects_drive_period_mismatch() -> None:
    content = JsonRenderer().render_month_summary(_summary()).encode("utf-8")

    with pytest.raises(ViewerReportLoadError):
        load_viewer_report(_DriveDownloader(content), artifact=_artifact(period="2026-09"))


def test_load_viewer_report_keeps_download_bounded_and_cleans_up_on_failure() -> None:
    class TooLargeDownloader(_DriveDownloader):
        def download_file(self, file_id: str, destination: Path, *, max_bytes: int) -> int:
            self.downloaded_file_ids.append(file_id)
            self.destination = destination
            self.max_bytes = max_bytes
            destination.write_bytes(b"partial")
            raise DriveDownloadTooLargeError("too large")

    downloader = TooLargeDownloader(b"")

    with pytest.raises(DriveDownloadTooLargeError):
        load_viewer_report(downloader, artifact=_artifact())

    assert downloader.max_bytes == MAX_VIEWER_REPORT_JSON_SIZE_BYTES
    assert downloader.destination is not None
    assert not downloader.destination.exists()
