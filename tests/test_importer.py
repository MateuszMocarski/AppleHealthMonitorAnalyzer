import zipfile
from pathlib import Path

import pytest

from apple_health.importer import AppleHealthImporter


def _create_zip(
    path: Path,
    files: dict[str, str],
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for filename, content in files.items():
            archive.writestr(
                filename,
                content,
            )


# =====================================================================
# Verifies that attempting to open an Apple Health export from a path
# that does not exist raises FileNotFoundError.
# =====================================================================


def test_open_export_raises_when_archive_does_not_exist(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "missing.zip"

    importer = AppleHealthImporter(archive_path)

    with pytest.raises(FileNotFoundError):
        importer.open_export()


# =====================================================================
# Verifies that an archive containing exactly one valid XML file is
# opened successfully and returns access to that XML export.
# =====================================================================


def test_open_export_returns_single_xml_file(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {
            "apple_health_export/export.xml": "<HealthData />",
        },
    )

    importer = AppleHealthImporter(archive_path)

    archive, xml_file = importer.open_export()

    try:
        assert xml_file.read() == b"<HealthData />"
    finally:
        xml_file.close()
        archive.close()


# =====================================================================
# Verifies that non-XML files contained in the export archive are
# ignored when locating the Apple Health XML export.
# =====================================================================


def test_open_export_ignores_non_xml_files(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {
            "apple_health_export/export.xml": "<HealthData />",
            "apple_health_export/readme.txt": "test",
            "apple_health_export/data.csv": "test",
        },
    )

    importer = AppleHealthImporter(archive_path)

    archive, xml_file = importer.open_export()

    try:
        assert xml_file.name == "apple_health_export/export.xml"
    finally:
        xml_file.close()
        archive.close()


# =====================================================================
# Verifies that CDA XML documents are ignored when locating the main
# Apple Health export XML file.
# =====================================================================


def test_open_export_ignores_cda_xml_files(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {
            "apple_health_export/export.xml": "<HealthData />",
            "apple_health_export/export_cda.xml": "<ClinicalDocument />",
        },
    )

    importer = AppleHealthImporter(archive_path)

    archive, xml_file = importer.open_export()

    try:
        assert xml_file.name == "apple_health_export/export.xml"
    finally:
        xml_file.close()
        archive.close()


# =====================================================================
# Verifies that an archive containing anything other than exactly one
# valid export XML file is rejected.
# =====================================================================


@pytest.mark.parametrize(
    "files",
    [
        {},
        {
            "first.xml": "<HealthData />",
            "second.xml": "<HealthData />",
        },
    ],
)
def test_open_export_rejects_invalid_xml_file_count(
    tmp_path: Path,
    files: dict[str, str],
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        files,
    )

    importer = AppleHealthImporter(archive_path)

    with pytest.raises(
        RuntimeError,
        match=r"Expected exactly one export XML, found \d+\.",
    ):
        importer.open_export()
