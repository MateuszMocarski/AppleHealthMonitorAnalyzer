from pathlib import Path

from apple_health.config.app_config import AppConfig
from apple_health.exceptions import (
    AppleHealthError,
    ExportXmlNotFoundError,
    ExportXmlTooLargeError,
    HealthDataParseError,
    InvalidArchiveError,
    MultipleExportXmlError,
)
from apple_health.importer import AppleHealthImporter
from apple_health.parser import AppleHealthParser
from apple_health.providers.contract import (
    DatasetProvenance,
    HealthDataProviderError,
    LoadedHealthData,
)


class AppleHealthProvider:
    """Apple ZIP/XML adapter that emits canonical health data."""

    provider_id = "apple_health"
    _DISPLAY_LABEL = "Apple Health"

    def load(self, path: Path, *, config: object) -> LoadedHealthData:
        if not isinstance(config, AppConfig):
            raise TypeError("AppleHealthProvider requires AppConfig.")

        try:
            with AppleHealthImporter(path).open_export() as xml_stream:
                data = AppleHealthParser(xml_stream, config=config).parse()
        except AppleHealthError as exc:
            raise HealthDataProviderError(self._error_category(exc)) from exc

        return LoadedHealthData(
            data=data,
            provenance=DatasetProvenance(
                provider_id=self.provider_id,
                display_label=self._DISPLAY_LABEL,
            ),
        )

    @staticmethod
    def _error_category(error: AppleHealthError) -> str:
        if isinstance(error, InvalidArchiveError):
            return "invalid_archive"
        if isinstance(error, ExportXmlTooLargeError):
            return "input_too_large"
        if isinstance(error, ExportXmlNotFoundError):
            return "missing_export_xml"
        if isinstance(error, MultipleExportXmlError):
            return "multiple_export_xml"
        if isinstance(error, HealthDataParseError):
            return "malformed_data"
        return "invalid_input"
