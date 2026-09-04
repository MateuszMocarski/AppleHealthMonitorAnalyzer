import zipfile
from pathlib import Path

import pytest

from health_analyzer.exceptions import (
    ExportXmlNotFoundError,
    ExportXmlTooLargeError,
    InvalidArchiveError,
    MultipleExportXmlError,
)
from health_analyzer.providers.apple.importer import AppleHealthImporter


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
        with importer.open_export():
            pass


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
            "health_analyzer_export/export.xml": "<HealthData />",
        },
    )

    importer = AppleHealthImporter(archive_path)

    with importer.open_export() as xml_file:
        assert xml_file.read() == b"<HealthData />"


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
            "health_analyzer_export/export.xml": "<HealthData />",
            "health_analyzer_export/readme.txt": "test",
            "health_analyzer_export/data.csv": "test",
        },
    )

    importer = AppleHealthImporter(archive_path)

    with importer.open_export() as xml_file:
        assert xml_file.name == "health_analyzer_export/export.xml"


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
            "health_analyzer_export/export.xml": "<HealthData />",
            "health_analyzer_export/export_cda.xml": "<ClinicalDocument />",
        },
    )

    importer = AppleHealthImporter(archive_path)

    with importer.open_export() as xml_file:
        assert xml_file.name == "health_analyzer_export/export.xml"


# =====================================================================
# Verifies that importer rejects archives containing anything other
# than exactly one valid export XML.
# =====================================================================


@pytest.mark.parametrize(
    ("files", "expected_exception"),
    [
        (
            {},
            ExportXmlNotFoundError,
        ),
        (
            {
                "health_analyzer_export/export.xml": "<HealthData />",
                "health_analyzer_export/eksport.xml": "<HealthData />",
            },
            MultipleExportXmlError,
        ),
    ],
)
def test_open_export_rejects_invalid_xml_file_count(
    tmp_path: Path,
    files: dict[str, str],
    expected_exception: type[Exception],
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        files,
    )

    importer = AppleHealthImporter(archive_path)

    with pytest.raises(expected_exception):
        with importer.open_export():
            pass


# =====================================================================
# Verifies that a localized Apple Health export XML filename is accepted
# when it is the single non-CDA XML file in the export directory.
# =====================================================================


def test_open_export_accepts_localized_export_xml_filename(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {
            "health_analyzer_export/eksport.xml": "<HealthData />",
            "health_analyzer_export/export_cda.xml": "<ClinicalDocument />",
        },
    )

    importer = AppleHealthImporter(archive_path)

    with importer.open_export() as xml_file:
        assert xml_file.read() == b"<HealthData />"


# =====================================================================
# Verifies that the importer rejects an Apple Health export XML whose
# uncompressed size exceeds the configured safety limit.
# =====================================================================


def test_open_export_rejects_oversized_export_xml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {
            "health_analyzer_export/export.xml": "<HealthData />",
        },
    )

    monkeypatch.setattr(
        "health_analyzer.providers.apple.importer.MAX_EXPORT_XML_SIZE",
        10,
    )

    importer = AppleHealthImporter(
        archive_path,
    )

    with pytest.raises(ExportXmlTooLargeError):
        with importer.open_export():
            pass


# =====================================================================
# Verifies that an archive without an Apple Health export XML raises
# the dedicated missing-export exception.
# =====================================================================


def test_open_export_rejects_missing_export_xml(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {},
    )

    importer = AppleHealthImporter(archive_path)

    with pytest.raises(ExportXmlNotFoundError):
        with importer.open_export():
            pass


# =====================================================================
# Verifies that an archive containing multiple Apple Health export XML
# files raises the dedicated multiple-export exception.
# =====================================================================


def test_open_export_rejects_multiple_export_xml_files(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    _create_zip(
        archive_path,
        {
            "health_analyzer_export/export.xml": "<HealthData />",
            "health_analyzer_export/eksport.xml": "<HealthData />",
        },
    )

    importer = AppleHealthImporter(archive_path)

    with pytest.raises(MultipleExportXmlError):
        with importer.open_export():
            pass


# =====================================================================
# Verifies that malformed ZIP input is translated into the dedicated
# Apple Health archive exception at the importer boundary.
# =====================================================================


def test_open_export_rejects_invalid_zip_archive(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "export.zip"

    archive_path.write_bytes(
        b"this-is-not-a-zip",
    )

    importer = AppleHealthImporter(archive_path)

    with pytest.raises(InvalidArchiveError):
        with importer.open_export():
            pass
