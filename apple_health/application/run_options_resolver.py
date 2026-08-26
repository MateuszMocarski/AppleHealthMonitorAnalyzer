from datetime import date
from pathlib import Path

from apple_health.application.run_options import RunOptions
from apple_health.application.run_profile import RunProfile


class RunOptionsResolver:
    @staticmethod
    def resolve(
        *,
        archive_path: Path | None = None,
        year: int | None = None,
        month: int | None = None,
        month_summary: bool | None = None,
        output_format: str | None = None,
        config_path: Path | None = None,
        profile: RunProfile | None = None,
    ) -> RunOptions:
        today = date.today()

        profile = profile or RunProfile()

        resolved_archive_path = archive_path if archive_path is not None else profile.archive_path

        if resolved_archive_path is None:
            raise ValueError("Archive path is required.")

        resolved_year = (
            year if year is not None else (profile.year if profile.year is not None else today.year)
        )

        resolved_month = (
            month
            if month is not None
            else (profile.month if profile.month is not None else today.month)
        )

        resolved_month_summary = (
            month_summary
            if month_summary is not None
            else (profile.month_summary if profile.month_summary is not None else False)
        )

        resolved_output_format = (
            output_format
            if output_format is not None
            else (profile.output_format if profile.output_format is not None else "text")
        )

        resolved_config_path = config_path if config_path is not None else profile.config_path

        return RunOptions(
            archive_path=resolved_archive_path,
            year=resolved_year,
            month=resolved_month,
            month_summary=resolved_month_summary,
            output_format=resolved_output_format,
            config_path=resolved_config_path,
        )
