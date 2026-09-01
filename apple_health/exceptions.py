class AppleHealthError(Exception):
    """Base exception for expected Apple Health processing errors."""


class HealthDataImportError(AppleHealthError):
    """Base exception for expected Apple Health import errors."""


class InvalidArchiveError(HealthDataImportError):
    """Raised when the uploaded archive is not a valid ZIP file."""


class ExportXmlNotFoundError(HealthDataImportError):
    """Raised when the archive does not contain an Apple Health export XML."""


class MultipleExportXmlError(HealthDataImportError):
    """Raised when the archive contains multiple Apple Health export XML files."""


class ExportXmlTooLargeError(HealthDataImportError):
    """Raised when the Apple Health export XML exceeds the size limit."""


class HealthDataParseError(AppleHealthError):
    """Raised when Apple Health XML cannot be parsed."""
