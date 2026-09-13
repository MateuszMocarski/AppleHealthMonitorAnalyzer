from apple_health.application.monthly_reports import MonthlyReports
from apple_health.google.current_report_generation import discover_current_generation
from apple_health.google.drive import (
    DriveClient,
    DriveConflictError,
    DriveFileMetadata,
)
from apple_health.google.drive_structure import (
    discover_report_index,
    discover_report_month,
    ensure_ahm_root,
    ensure_report_month,
    ensure_reports_container,
    ensure_year_container,
)


def upload_report_artifacts(
    drive_client: DriveClient,
    *,
    month_id: str,
    report: MonthlyReports,
) -> tuple[DriveFileMetadata, ...]:
    app_properties = report.metadata.artifact_app_properties()

    artifacts = (
        (
            "full.txt",
            report.full_text,
            "text/plain",
        ),
        (
            "full.json",
            report.full_json,
            "application/json",
        ),
        (
            "summary.txt",
            report.summary_text,
            "text/plain",
        ),
        (
            "summary.json",
            report.summary_json,
            "application/json",
        ),
    )

    uploaded = []

    for name, content, mime_type in artifacts:
        if content is None:
            continue

        uploaded.append(
            drive_client.upload_file(
                name=name,
                content=content.encode("utf-8"),
                mime_type=mime_type,
                parent_id=month_id,
                app_properties=app_properties,
            )
        )

    return tuple(uploaded)


def verify_report_artifacts(
    drive_client: DriveClient,
    *,
    report: MonthlyReports,
    uploaded: tuple[DriveFileMetadata, ...],
) -> None:
    expected_properties = report.metadata.artifact_app_properties()

    expected = {
        "full.txt": (
            report.full_text,
            "text/plain",
        ),
        "full.json": (
            report.full_json,
            "application/json",
        ),
        "summary.txt": (
            report.summary_text,
            "text/plain",
        ),
        "summary.json": (
            report.summary_json,
            "application/json",
        ),
    }

    expected = {
        name: (
            content,
            mime_type,
        )
        for name, (
            content,
            mime_type,
        ) in expected.items()
        if content is not None
    }

    if {file.name for file in uploaded} != set(expected):
        raise ValueError("Uploaded report artifact set does not match generated outputs.")

    for file in uploaded:
        metadata = drive_client.get_metadata(
            file.file_id,
        )

        content, mime_type = expected[file.name]

        if metadata.trashed:
            raise ValueError("Uploaded report artifact is trashed.")

        if metadata.name != file.name:
            raise ValueError("Uploaded report artifact name does not match.")

        if metadata.mime_type != mime_type:
            raise ValueError("Uploaded report artifact MIME type does not match.")

        if metadata.size_bytes != len(content.encode("utf-8")):
            raise ValueError("Uploaded report artifact size does not match.")

        if dict(metadata.app_properties) != expected_properties:
            raise ValueError("Uploaded report artifact metadata does not match.")


def mark_generation_current(
    drive_client: DriveClient,
    *,
    month_id: str,
    period: str,
    generation_id: str,
) -> DriveFileMetadata:
    return drive_client.update_metadata(
        month_id,
        app_properties={
            "ahm_type": "report_month",
            "ahm_period": period,
            "ahm_current_generation_id": generation_id,
        },
    )


def save_new_report_month(
    drive_client: DriveClient,
    *,
    report: MonthlyReports,
) -> DriveFileMetadata:
    period = f"{report.period.year}-" f"{report.period.month:02d}"

    root = ensure_ahm_root(
        drive_client,
    )
    reports = ensure_reports_container(
        drive_client,
        root_id=root.file_id,
    )
    year = ensure_year_container(
        drive_client,
        reports_id=reports.file_id,
        year=report.period.year,
    )
    existing_month = discover_report_month(
        drive_client,
        year_id=year.file_id,
        period=period,
    )
    if existing_month is not None:
        raise DriveConflictError(f"Report month already exists: {period}")
    month = ensure_report_month(
        drive_client,
        year_id=year.file_id,
        period=period,
    )

    uploaded = upload_report_artifacts(
        drive_client,
        month_id=month.file_id,
        report=report,
    )

    verify_report_artifacts(
        drive_client,
        report=report,
        uploaded=uploaded,
    )

    return mark_generation_current(
        drive_client,
        month_id=month.file_id,
        period=period,
        generation_id=report.metadata.generation_id,
    )


def create_report_staging_folder(
    drive_client: DriveClient,
    *,
    month_id: str,
    period: str,
    generation_id: str,
) -> DriveFileMetadata:
    return drive_client.create_folder(
        name=f"staging-{generation_id}",
        parent_id=month_id,
        app_properties={
            "ahm_type": "report_staging",
            "ahm_period": period,
            "ahm_generation_id": generation_id,
        },
    )


def stage_report_generation(
    drive_client: DriveClient,
    *,
    month_id: str,
    report: MonthlyReports,
) -> tuple[
    DriveFileMetadata,
    tuple[DriveFileMetadata, ...],
]:
    period = f"{report.period.year}-" f"{report.period.month:02d}"

    staging = create_report_staging_folder(
        drive_client,
        month_id=month_id,
        period=period,
        generation_id=report.metadata.generation_id,
    )

    try:
        uploaded = upload_report_artifacts(
            drive_client,
            month_id=staging.file_id,
            report=report,
        )
    except Exception:
        try:
            cleanup_staging_generation(
                drive_client,
                staging_id=staging.file_id,
            )
        except Exception:
            pass

        raise

    return staging, uploaded


def verify_staged_generation(
    drive_client: DriveClient,
    *,
    report: MonthlyReports,
    uploaded: tuple[DriveFileMetadata, ...],
) -> None:
    verify_report_artifacts(
        drive_client,
        report=report,
        uploaded=uploaded,
    )


def prepare_staged_generation_activation(
    drive_client: DriveClient,
    *,
    month_id: str,
    staging_id: str,
    artifacts: tuple[DriveFileMetadata, ...],
) -> tuple[DriveFileMetadata, ...]:
    return tuple(
        drive_client.move(
            artifact.file_id,
            add_parent_id=month_id,
            remove_parent_id=staging_id,
        )
        for artifact in artifacts
    )


def commit_staged_generation(
    drive_client: DriveClient,
    *,
    month_id: str,
    period: str,
    generation_id: str,
) -> DriveFileMetadata:
    return mark_generation_current(
        drive_client,
        month_id=month_id,
        period=period,
        generation_id=generation_id,
    )


def ensure_report_archive_container(
    drive_client: DriveClient,
    *,
    month_id: str,
) -> DriveFileMetadata:
    page_token: str | None = None

    while True:
        page = drive_client.list_children(
            month_id,
            page_token=page_token,
        )

        for child in page.files:
            if (
                not child.trashed
                and child.name == "archive"
                and child.mime_type == "application/vnd.google-apps.folder"
            ):
                return child

        if page.next_page_token is None:
            break

        page_token = page.next_page_token

    return drive_client.create_folder(
        name="archive",
        parent_id=month_id,
    )


def archive_previous_generation(
    drive_client: DriveClient,
    *,
    month_id: str,
    artifacts: tuple[DriveFileMetadata, ...],
) -> tuple[DriveFileMetadata, ...]:
    if not artifacts:
        return ()

    generated_at = artifacts[0].app_properties.get("ahm_generated_at")

    if generated_at is None:
        raise ValueError("Previous report generation is missing generated timestamp.")

    archive = ensure_report_archive_container(
        drive_client,
        month_id=month_id,
    )

    archive_name = generated_at.replace(
        ":",
        "-",
    )

    archive_generation = drive_client.create_folder(
        name=archive_name,
        parent_id=archive.file_id,
    )

    return tuple(
        drive_client.move(
            artifact.file_id,
            add_parent_id=archive_generation.file_id,
            remove_parent_id=month_id,
        )
        for artifact in artifacts
    )


def replace_report_month(
    drive_client: DriveClient,
    *,
    month: DriveFileMetadata,
    report: MonthlyReports,
) -> None:
    current = discover_current_generation(
        drive_client,
        month=month,
    )

    staging, uploaded = stage_report_generation(
        drive_client,
        month_id=month.file_id,
        report=report,
    )

    try:
        verify_staged_generation(
            drive_client,
            report=report,
            uploaded=uploaded,
        )

        prepare_staged_generation_activation(
            drive_client,
            month_id=month.file_id,
            staging_id=staging.file_id,
            artifacts=uploaded,
        )

        period = f"{report.period.year}-" f"{report.period.month:02d}"

        commit_staged_generation(
            drive_client,
            month_id=month.file_id,
            period=period,
            generation_id=report.metadata.generation_id,
        )
    except Exception:
        try:
            cleanup_staging_generation(
                drive_client,
                staging_id=staging.file_id,
            )
        except Exception:
            pass

        raise

    if current is not None:
        try:
            archive_previous_generation(
                drive_client,
                month_id=month.file_id,
                artifacts=current.artifacts,
            )
        except Exception:
            pass

    try:
        cleanup_staging_generation(
            drive_client,
            staging_id=staging.file_id,
        )
    except Exception:
        pass


def cleanup_staging_generation(
    drive_client: DriveClient,
    *,
    staging_id: str,
) -> None:
    drive_client.delete(staging_id)


def report_month_exists(
    drive_client: DriveClient,
    *,
    period: str,
) -> bool:
    report_index = discover_report_index(
        drive_client,
    )

    year = period[:4]

    return period in report_index.get(
        year,
        (),
    )


def replace_existing_report_month(
    drive_client: DriveClient,
    *,
    report: MonthlyReports,
) -> None:
    period = f"{report.period.year}-" f"{report.period.month:02d}"

    root = ensure_ahm_root(
        drive_client,
    )

    reports = ensure_reports_container(
        drive_client,
        root_id=root.file_id,
    )

    year = ensure_year_container(
        drive_client,
        reports_id=reports.file_id,
        year=report.period.year,
    )

    month = discover_report_month(
        drive_client,
        year_id=year.file_id,
        period=period,
    )

    if month is None:
        raise DriveConflictError(f"Report month does not exist: {period}")

    replace_report_month(
        drive_client,
        month=month,
        report=report,
    )


def find_existing_report_periods(
    drive_client: DriveClient,
    *,
    reports: tuple[MonthlyReports, ...],
) -> set[str]:
    report_index = discover_report_index(
        drive_client,
    )

    existing: set[str] = set()

    for report in reports:
        period = f"{report.period.year}-" f"{report.period.month:02d}"

        year = str(
            report.period.year,
        )

        if period in report_index.get(
            year,
            (),
        ):
            existing.add(period)

    return existing
