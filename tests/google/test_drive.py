from pathlib import Path

import httpx
import pytest

from apple_health.google.drive import (
    DriveAccessError,
    DriveClient,
    DriveConflictError,
    DriveDownloadTooLargeError,
    DriveError,
    DriveFileMetadata,
    DriveFilePage,
    DriveNotFoundError,
    DriveTransientError,
    HttpGoogleDriveClient,
)

# =====================================================================
# Verifies that Google Drive adapter failures expose stable application
# errors through one common Drive error hierarchy.
# =====================================================================


def test_drive_errors_share_common_base() -> None:
    error_types = (
        DriveAccessError,
        DriveConflictError,
        DriveDownloadTooLargeError,
        DriveNotFoundError,
        DriveTransientError,
    )

    assert all(issubclass(error_type, DriveError) for error_type in error_types)


# =====================================================================
# Verifies that the Drive client contract exposes file metadata through
# a provider-specific data model without leaking raw HTTP responses.
# =====================================================================


def test_drive_client_contract_returns_file_metadata() -> None:
    class FakeDriveClient:
        def get_metadata(
            self,
            file_id: str,
        ) -> DriveFileMetadata:
            assert file_id == "file-123"

            return DriveFileMetadata(
                file_id="file-123",
                name="export.zip",
                mime_type="application/zip",
                size_bytes=123456,
                trashed=False,
                app_properties={
                    "ahm_type": "source",
                },
            )

    client: DriveClient = FakeDriveClient()

    metadata = client.get_metadata(
        "file-123",
    )

    assert metadata == DriveFileMetadata(
        file_id="file-123",
        name="export.zip",
        mime_type="application/zip",
        size_bytes=123456,
        trashed=False,
        app_properties={
            "ahm_type": "source",
        },
    )


# =====================================================================
# Verifies that the Drive client contract exposes paginated discovery
# operations without leaking Google Drive API response structures.
# =====================================================================


def test_drive_client_contract_exposes_paginated_read_operations() -> None:
    page = DriveFilePage(
        files=(),
        next_page_token="next-page",
    )

    assert page.files == ()
    assert page.next_page_token == "next-page"
    assert callable(DriveClient.search)
    assert callable(DriveClient.list_children)


# =====================================================================
# Verifies that the HTTP Drive client retrieves file metadata and maps
# the Google Drive response into the application metadata model.
# =====================================================================


def test_http_drive_client_gets_file_metadata(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "file-123",
                "name": "export.zip",
                "mimeType": "application/zip",
                "size": "123456",
                "trashed": False,
                "appProperties": {
                    "ahm_type": "source",
                },
            }

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/drive/v3/files/" "file-123")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "fields": ("id,name,mimeType,size,trashed," "appProperties"),
        }
        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    metadata = client.get_metadata(
        "file-123",
    )

    assert metadata == DriveFileMetadata(
        file_id="file-123",
        name="export.zip",
        mime_type="application/zip",
        size_bytes=123456,
        trashed=False,
        app_properties={
            "ahm_type": "source",
        },
    )


# =====================================================================
# Verifies that Google Drive HTTP failures are mapped into stable
# application errors instead of leaking raw HTTP client exceptions.
# =====================================================================


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, DriveAccessError),
        (403, DriveAccessError),
        (404, DriveNotFoundError),
        (429, DriveTransientError),
        (500, DriveTransientError),
        (503, DriveTransientError),
        (400, DriveError),
    ],
)
def test_http_drive_client_maps_http_failures(
    monkeypatch,
    status_code: int,
    expected_error: type[DriveError],
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "GET",
                "https://www.googleapis.com/drive/v3/files/file-123",
            )
            response = httpx.Response(
                status_code,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Drive request failed",
                request=request,
                response=response,
            )

    def fake_get(
        *args,
        **kwargs,
    ) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    with pytest.raises(expected_error):
        client.get_metadata(
            "file-123",
        )


# =====================================================================
# Verifies that Google Drive network failures are mapped into a stable
# transient application error instead of leaking httpx exceptions.
# =====================================================================


def test_http_drive_client_maps_network_failure(
    monkeypatch,
) -> None:
    def fake_get(
        *args,
        **kwargs,
    ):
        request = httpx.Request(
            "GET",
            "https://www.googleapis.com/drive/v3/files/file-123",
        )

        raise httpx.RequestError(
            "Network failure",
            request=request,
        )

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    with pytest.raises(DriveTransientError):
        client.get_metadata(
            "file-123",
        )


# =====================================================================
# Verifies that malformed Google Drive metadata responses are mapped
# into a stable application error.
# =====================================================================


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "export.zip",
            "mimeType": "application/zip",
            "trashed": False,
        },
        {
            "id": "file-123",
            "name": "export.zip",
            "mimeType": "application/zip",
            "size": "not-a-number",
            "trashed": False,
        },
    ],
)
def test_http_drive_client_rejects_malformed_metadata_response(
    monkeypatch,
    payload: dict[str, object],
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return payload

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        lambda *args, **kwargs: FakeResponse(),
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    with pytest.raises(DriveError):
        client.get_metadata(
            "file-123",
        )


# =====================================================================
# Verifies that the HTTP Drive client performs paginated file searches
# and maps Google Drive results into the application page model.
# =====================================================================


def test_http_drive_client_searches_files(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "files": [
                    {
                        "id": "file-123",
                        "name": "export.zip",
                        "mimeType": "application/zip",
                        "size": "123456",
                        "trashed": False,
                        "appProperties": {
                            "ahm_type": "source",
                        },
                    },
                ],
                "nextPageToken": "next-page",
            }

    def fake_get(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/drive/v3/files")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "q": "trashed = false",
            "fields": ("nextPageToken," "files(id,name,mimeType,size,trashed," "appProperties)"),
            "pageToken": "current-page",
        }
        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    page = client.search(
        query="trashed = false",
        page_token="current-page",
    )

    assert page == DriveFilePage(
        files=(
            DriveFileMetadata(
                file_id="file-123",
                name="export.zip",
                mime_type="application/zip",
                size_bytes=123456,
                trashed=False,
                app_properties={
                    "ahm_type": "source",
                },
            ),
        ),
        next_page_token="next-page",
    )


# =====================================================================
# Verifies that listing Drive folder children reuses the paginated
# search operation with the expected parent query.
# =====================================================================


def test_http_drive_client_lists_children(
    monkeypatch,
) -> None:
    expected_page = DriveFilePage(
        files=(),
        next_page_token="next-page",
    )

    def fake_search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> DriveFilePage:
        assert query == "'folder-123' in parents"
        assert page_token == "current-page"

        return expected_page

    monkeypatch.setattr(
        HttpGoogleDriveClient,
        "search",
        fake_search,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    page = client.list_children(
        parent_id="folder-123",
        page_token="current-page",
    )

    assert page == expected_page


# =====================================================================
# Verifies that the Drive client contract exposes the write operations
# required by user-owned application persistence.
# =====================================================================


def test_drive_client_contract_exposes_write_operations() -> None:
    assert callable(DriveClient.create_folder)
    assert callable(DriveClient.upload_file)
    assert callable(DriveClient.update_metadata)
    assert callable(DriveClient.move)
    assert callable(DriveClient.trash)


# =====================================================================
# Verifies that the HTTP Drive client creates a folder with optional
# parent and appProperties and returns normalized metadata.
# =====================================================================


def test_http_drive_client_creates_folder(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "folder-123",
                "name": "Apple Health Monitor",
                "mimeType": "application/vnd.google-apps.folder",
                "trashed": False,
                "appProperties": {
                    "ahm_type": "root",
                },
            }

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/drive/v3/files")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "fields": ("id,name,mimeType,size,trashed," "appProperties"),
        }
        assert json == {
            "name": "Apple Health Monitor",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [
                "parent-123",
            ],
            "appProperties": {
                "ahm_type": "root",
            },
        }
        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.post",
        fake_post,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    metadata = client.create_folder(
        name="Apple Health Monitor",
        parent_id="parent-123",
        app_properties={
            "ahm_type": "root",
        },
    )

    assert metadata == DriveFileMetadata(
        file_id="folder-123",
        name="Apple Health Monitor",
        mime_type="application/vnd.google-apps.folder",
        size_bytes=None,
        trashed=False,
        app_properties={
            "ahm_type": "root",
        },
    )


# =====================================================================
# Verifies that the HTTP Drive client uploads file content together
# with metadata and returns normalized Drive metadata.
# =====================================================================


def test_http_drive_client_uploads_file(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "file-123",
                "name": "report.json",
                "mimeType": "application/json",
                "size": "15",
                "trashed": False,
                "appProperties": {
                    "ahm_type": "report",
                },
            }

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        files,
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/upload/drive/v3/files")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "uploadType": "multipart",
            "fields": ("id,name,mimeType,size,trashed," "appProperties"),
        }

        assert files[0][0] == "metadata"
        assert files[0][1][2] == "application/json; charset=UTF-8"

        assert files[1] == (
            "file",
            (
                "report.json",
                b'{"hello":"x"}',
                "application/json",
            ),
        )

        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.post",
        fake_post,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    metadata = client.upload_file(
        name="report.json",
        content=b'{"hello":"x"}',
        mime_type="application/json",
        parent_id="folder-123",
        app_properties={
            "ahm_type": "report",
        },
    )

    assert metadata == DriveFileMetadata(
        file_id="file-123",
        name="report.json",
        mime_type="application/json",
        size_bytes=15,
        trashed=False,
        app_properties={
            "ahm_type": "report",
        },
    )


# =====================================================================
# Verifies that the HTTP Drive client updates file metadata and returns
# normalized Drive metadata.
# =====================================================================


def test_http_drive_client_updates_metadata(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "file-123",
                "name": "renamed.json",
                "mimeType": "application/json",
                "size": "15",
                "trashed": False,
                "appProperties": {
                    "ahm_type": "report",
                    "ahm_version": "1",
                },
            }

    def fake_patch(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/drive/v3/files/" "file-123")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "fields": ("id,name,mimeType,size,trashed," "appProperties"),
        }
        assert json == {
            "name": "renamed.json",
            "appProperties": {
                "ahm_type": "report",
                "ahm_version": "1",
            },
        }
        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.patch",
        fake_patch,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    metadata = client.update_metadata(
        "file-123",
        name="renamed.json",
        app_properties={
            "ahm_type": "report",
            "ahm_version": "1",
        },
    )

    assert metadata.name == "renamed.json"
    assert metadata.app_properties == {
        "ahm_type": "report",
        "ahm_version": "1",
    }


# =====================================================================
# Verifies that the HTTP Drive client moves a file between parents and
# returns normalized Drive metadata.
# =====================================================================


def test_http_drive_client_moves_file(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "file-123",
                "name": "report.json",
                "mimeType": "application/json",
                "size": "15",
                "trashed": False,
                "appProperties": {
                    "ahm_type": "report",
                },
            }

    def fake_patch(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/drive/v3/files/" "file-123")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "addParents": "new-parent",
            "removeParents": "old-parent",
            "fields": ("id,name,mimeType,size,trashed," "appProperties"),
        }
        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.patch",
        fake_patch,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    metadata = client.move(
        "file-123",
        add_parent_id="new-parent",
        remove_parent_id="old-parent",
    )

    assert metadata.file_id == "file-123"
    assert metadata.name == "report.json"


# =====================================================================
# Verifies that the HTTP Drive client trashes a file without requiring
# the caller to handle raw Google Drive response metadata.
# =====================================================================


def test_http_drive_client_trashes_file(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "file-123",
                "name": "report.json",
                "mimeType": "application/json",
                "size": "15",
                "trashed": True,
                "appProperties": {
                    "ahm_type": "report",
                },
            }

    def fake_patch(
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        assert url == ("https://www.googleapis.com/drive/v3/files/" "file-123")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "fields": ("id,name,mimeType,size,trashed," "appProperties"),
        }
        assert json == {
            "trashed": True,
        }
        assert timeout == 10.0

        return FakeResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.patch",
        fake_patch,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    result = client.trash(
        "file-123",
    )

    assert result is None


# =====================================================================
# Verifies that the HTTP Drive client streams file content to disk and
# returns the exact number of downloaded bytes.
# =====================================================================


def test_http_drive_client_downloads_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self):
            yield b"hello "
            yield b"world"

    class FakeStream:
        def __enter__(self) -> FakeResponse:
            return FakeResponse()

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ) -> None:
            pass

    def fake_stream(
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str],
        timeout: float,
    ) -> FakeStream:
        assert method == "GET"
        assert url == ("https://www.googleapis.com/drive/v3/files/" "file-123")
        assert headers == {
            "Authorization": "Bearer access-token",
        }
        assert params == {
            "alt": "media",
        }
        assert timeout == 10.0

        return FakeStream()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.stream",
        fake_stream,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    destination = tmp_path / "download.bin"

    downloaded_bytes = client.download_file(
        file_id="file-123",
        destination=destination,
        max_bytes=100,
    )

    assert downloaded_bytes == 11
    assert destination.read_bytes() == b"hello world"


# =====================================================================
# Verifies that Drive downloads stop immediately after exceeding the
# hard byte limit and remove the partial destination file.
# =====================================================================


def test_http_drive_client_rejects_oversized_download(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self):
            yield b"12345"
            yield b"67890"
            yield b"extra-data"

    class FakeStream:
        def __enter__(self) -> FakeResponse:
            return FakeResponse()

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ) -> None:
            pass

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.stream",
        lambda *args, **kwargs: FakeStream(),
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    destination = tmp_path / "download.bin"

    with pytest.raises(DriveDownloadTooLargeError):
        client.download_file(
            file_id="file-123",
            destination=destination,
            max_bytes=8,
        )

    assert not destination.exists()


# =====================================================================
# Verifies that transient Drive metadata failures are retried with a
# bounded number of attempts before returning a successful response.
# =====================================================================


def test_http_drive_client_retries_transient_metadata_failure(
    monkeypatch,
) -> None:
    attempts = 0

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "id": "file-123",
                "name": "export.zip",
                "mimeType": "application/zip",
                "size": "123456",
                "trashed": False,
                "appProperties": {},
            }

    def fake_get(
        *args,
        **kwargs,
    ):
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            request = httpx.Request(
                "GET",
                "https://www.googleapis.com/drive/v3/files/file-123",
            )
            response = httpx.Response(
                503,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Service unavailable",
                request=request,
                response=response,
            )

        return SuccessfulResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    metadata = client.get_metadata(
        "file-123",
    )

    assert attempts == 2
    assert metadata.file_id == "file-123"


# =====================================================================
# Verifies that transient Drive search failures are retried because
# search is a safe idempotent read operation.
# =====================================================================


def test_http_drive_client_retries_transient_search_failure(
    monkeypatch,
) -> None:
    attempts = 0

    class TransientResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "GET",
                "https://www.googleapis.com/drive/v3/files",
            )
            response = httpx.Response(
                503,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Service unavailable",
                request=request,
                response=response,
            )

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {
                "files": [],
            }

    def fake_get(
        *args,
        **kwargs,
    ):
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return TransientResponse()

        return SuccessfulResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    page = client.search(
        query="trashed = false",
    )

    assert attempts == 2
    assert page == DriveFilePage(
        files=(),
        next_page_token=None,
    )


# =====================================================================
# Verifies that conflicting Drive writes are not retried and are mapped
# into the stable Drive conflict error.
# =====================================================================


def test_http_drive_client_does_not_retry_conflicting_write(
    monkeypatch,
) -> None:
    attempts = 0

    class ConflictResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "POST",
                "https://www.googleapis.com/drive/v3/files",
            )
            response = httpx.Response(
                409,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Conflict",
                request=request,
                response=response,
            )

    def fake_post(
        *args,
        **kwargs,
    ) -> ConflictResponse:
        nonlocal attempts
        attempts += 1

        return ConflictResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.post",
        fake_post,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    with pytest.raises(DriveConflictError):
        client.create_folder(
            name="Apple Health Monitor",
        )

    assert attempts == 1


# =====================================================================
# Verifies that transient Drive read failures stop after the configured
# maximum number of retry attempts.
# =====================================================================


def test_http_drive_client_stops_after_max_read_attempts(
    monkeypatch,
) -> None:
    attempts = 0

    class TransientResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request(
                "GET",
                "https://www.googleapis.com/drive/v3/files/file-123",
            )
            response = httpx.Response(
                503,
                request=request,
            )

            raise httpx.HTTPStatusError(
                "Service unavailable",
                request=request,
                response=response,
            )

    def fake_get(
        *args,
        **kwargs,
    ) -> TransientResponse:
        nonlocal attempts
        attempts += 1

        return TransientResponse()

    monkeypatch.setattr(
        "apple_health.google.drive.httpx.get",
        fake_get,
    )

    client = HttpGoogleDriveClient(
        access_token="access-token",
    )

    with pytest.raises(DriveTransientError):
        client.get_metadata(
            "file-123",
        )

    assert attempts == 3


# =====================================================================
# Verifies that Drive file downloads use a longer read timeout than
# ordinary metadata requests.
# =====================================================================


def test_download_file_uses_extended_timeout(
    monkeypatch,
    tmp_path,
) -> None:
    captured_timeout = None

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            traceback,
        ):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"zip-data"

    def fake_stream(
        method,
        url,
        *,
        headers,
        params,
        timeout,
    ):
        nonlocal captured_timeout
        captured_timeout = timeout
        return FakeResponse()

    monkeypatch.setattr(
        httpx,
        "stream",
        fake_stream,
    )

    client = HttpGoogleDriveClient(
        "access-token",
    )

    client.download_file(
        "file-id",
        tmp_path / "archive.zip",
        1024,
    )

    assert captured_timeout == client.DOWNLOAD_TIMEOUT