from __future__ import annotations

import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipExtFile


class AppleHealthImporter:
    def __init__(self, archive: Path) -> None:
        self.archive = archive

    @contextmanager
    def open_export(
        self,
    ) -> Generator[ZipExtFile, None, None]:
        if not self.archive.exists():
            raise FileNotFoundError(self.archive)

        with zipfile.ZipFile(self.archive, "r") as archive:
            xml_files = [
                file
                for file in archive.namelist()
                if file.lower().endswith(".xml")
                and "cda" not in Path(file).name.lower()
                and Path(file).parent.name == "apple_health_export"
            ]

            if len(xml_files) != 1:
                raise RuntimeError("Expected exactly one export XML, " f"found {len(xml_files)}.")

            with archive.open(xml_files[0]) as xml_stream:
                yield xml_stream
