from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunOptions:
    archive_path: Path
    year: int
    month: int
    month_summary: bool
    output_format: str
    config_path: Path | None
