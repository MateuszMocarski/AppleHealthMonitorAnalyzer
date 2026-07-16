from __future__ import annotations

import zipfile
from pathlib import Path
from zipfile import ZipFile
from zipfile import ZipExtFile


class AppleHealthImporter:
    def __init__(self, archive: Path) -> None:
        self.archive = archive

    def open_export(self) -> tuple[ZipFile, ZipExtFile]:
        if not self.archive.exists():
            raise FileNotFoundError(self.archive)

        archive = zipfile.ZipFile(self.archive, "r")

        xml_files = [
            file
            for file in archive.namelist()
            if file.lower().endswith(".xml")
            and "cda" not in file.lower()
        ]

        if len(xml_files) != 1:
            archive.close()

            raise RuntimeError(
                f"Expected exactly one export XML, found {len(xml_files)}."
            )

        return archive, archive.open(xml_files[0])