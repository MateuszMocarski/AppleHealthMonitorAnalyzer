from apple_health.application.monthly_reports import MonthlyReports
from apple_health.google.drive import (
    DriveClient,
    DriveConflictError,
    DriveFileMetadata,
)
from apple_health.google.drive_structure import (
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
