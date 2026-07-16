from __future__ import annotations

import zipfile
from pathlib import Path


class AppleHealthImporter:
    def __init__(self, archive: Path) -> None:
        self.archive = archive

    def run(self) -> None:
        if not self.archive.exists():
            raise FileNotFoundError(self.archive)

        print(f"Opening archive: {self.archive}")

        with zipfile.ZipFile(self.archive, "r") as archive:
            files = archive.namelist()

            xml_files = [
                file
                for file in files
                if file.lower().endswith(".xml")
                and "cda" not in file.lower()
            ]

            if len(xml_files) != 1:
                raise RuntimeError(
                    f"Expected exactly one export XML, found {len(xml_files)}."
                )

            export_xml = xml_files[0]
            info = archive.getinfo(export_xml)

            print("Archive OK")
            print(f"XML path : {export_xml}")
            print(f"XML size : {info.file_size / 1024 / 1024:.2f} MB")
            print(f"ZIP size : {info.compress_size / 1024 / 1024:.2f} MB")