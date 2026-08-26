from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunProfile:
    archive_path: Path | None = None
    year: int | None = None
    month: int | None = None
    month_summary: bool | None = None
    output_format: str | None = None
    config_path: Path | None = None
