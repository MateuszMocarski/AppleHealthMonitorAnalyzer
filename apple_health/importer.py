from __future__ import annotations

import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipExtFile

from apple_health.exceptions import (
    ExportXmlNotFoundError,
    ExportXmlTooLargeError,
    InvalidArchiveError,
    MultipleExportXmlError,
)

MAX_EXPORT_XML_SIZE = 4 * 1024 * 1024 * 1024  # 4 GB


class AppleHealthImporter:
    def __init__(self, archive: Path) -> None:
        self.archive = archive

    @contextmanager
    def open_export(
        self,
    ) -> Generator[ZipExtFile, None, None]:
        if not self.archive.exists():
            raise FileNotFoundError(self.archive)

        try:
            archive = zipfile.ZipFile(
                self.archive,
                "r",
            )
        except zipfile.BadZipFile as exc:
            raise InvalidArchiveError from exc

        with archive:
            xml_files = [
                file
                for file in archive.namelist()
                if file.lower().endswith(".xml")
                and "cda" not in Path(file).name.lower()
                and Path(file).parent.name == "apple_health_export"
            ]

            if not xml_files:
                raise ExportXmlNotFoundError

            if len(xml_files) > 1:
                raise MultipleExportXmlError

            export_info = archive.getinfo(
                xml_files[0],
            )

            if export_info.file_size > MAX_EXPORT_XML_SIZE:
                raise ExportXmlTooLargeError

            with archive.open(
                xml_files[0],
            ) as xml_stream:
                yield xml_stream
