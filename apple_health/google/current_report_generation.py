from collections.abc import Iterable
from dataclasses import dataclass

from apple_health.google.drive import (
    DriveClient,
    DriveFileMetadata,
)


@dataclass(frozen=True, slots=True)
class CurrentReportGeneration:
    period: str
    generation_id: str
    artifacts: tuple[DriveFileMetadata, ...]


def select_current_generation_artifacts(
    *,
    month: DriveFileMetadata,
    artifacts: Iterable[DriveFileMetadata],
) -> tuple[DriveFileMetadata, ...]:
    generation_id = month.app_properties.get("ahm_current_generation_id")
    period = month.app_properties.get("ahm_period")

    if generation_id is None or period is None:
        return ()

    return tuple(
        artifact
        for artifact in artifacts
        if (
            not artifact.trashed
            and artifact.app_properties.get("ahm_type") == "report_artifact"
            and artifact.app_properties.get("ahm_period") == period
            and artifact.app_properties.get("ahm_generation_id") == generation_id
        )
    )


def discover_current_generation_artifacts(
    drive_client: DriveClient,
    *,
    month: DriveFileMetadata,
) -> tuple[DriveFileMetadata, ...]:
    artifacts: list[DriveFileMetadata] = []
    page_token: str | None = None

    while True:
        page = drive_client.list_children(
            month.file_id,
            page_token=page_token,
        )

        artifacts.extend(
            page.files,
        )

        if page.next_page_token is None:
            break

        page_token = page.next_page_token

    return select_current_generation_artifacts(
        month=month,
        artifacts=artifacts,
    )


def resolve_current_generation(
    *,
    month: DriveFileMetadata,
    artifacts: Iterable[DriveFileMetadata],
) -> CurrentReportGeneration | None:
    generation_id = month.app_properties.get("ahm_current_generation_id")
    period = month.app_properties.get("ahm_period")

    if generation_id is None or period is None:
        return None

    current_artifacts = select_current_generation_artifacts(
        month=month,
        artifacts=artifacts,
    )

    return CurrentReportGeneration(
        period=period,
        generation_id=generation_id,
        artifacts=current_artifacts,
    )


def discover_current_generation(
    drive_client: DriveClient,
    *,
    month: DriveFileMetadata,
) -> CurrentReportGeneration | None:
    if month.app_properties.get("ahm_current_generation_id") is None:
        return None

    artifacts = discover_current_generation_artifacts(
        drive_client,
        month=month,
    )

    return resolve_current_generation(
        month=month,
        artifacts=artifacts,
    )
