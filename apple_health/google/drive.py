import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx


@dataclass(frozen=True)
class DriveFileMetadata:
    file_id: str
    name: str
    mime_type: str
    size_bytes: int | None
    trashed: bool
    app_properties: Mapping[str, str]


@dataclass(frozen=True)
class DriveFilePage:
    files: tuple[DriveFileMetadata, ...]
    next_page_token: str | None


class DriveClient(Protocol):
    def get_metadata(
        self,
        file_id: str,
    ) -> DriveFileMetadata: ...

    def search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> DriveFilePage: ...

    def list_children(
        self,
        parent_id: str,
        page_token: str | None = None,
    ) -> DriveFilePage: ...

    def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        app_properties: Mapping[str, str] | None = None,
    ) -> DriveFileMetadata: ...

    def upload_file(
        self,
        name: str,
        content: bytes,
        mime_type: str,
        parent_id: str | None = None,
        app_properties: Mapping[str, str] | None = None,
    ) -> DriveFileMetadata: ...

    def update_metadata(
        self,
        file_id: str,
        *,
        name: str | None = None,
        app_properties: Mapping[str, str] | None = None,
    ) -> DriveFileMetadata: ...

    def move(
        self,
        file_id: str,
        *,
        add_parent_id: str,
        remove_parent_id: str,
    ) -> DriveFileMetadata: ...

    def trash(
        self,
        file_id: str,
    ) -> None: ...

    def download_file(
        self,
        file_id: str,
        destination: Path,
        max_bytes: int,
    ) -> int: ...


class HttpGoogleDriveClient:
    API_BASE_URL = "https://www.googleapis.com/drive/v3"
    REQUEST_TIMEOUT = 10.0
    DOWNLOAD_TIMEOUT = 60.0
    READ_MAX_ATTEMPTS = 3

    def __init__(
        self,
        access_token: str,
    ) -> None:
        self._access_token = access_token

    def get_metadata(
        self,
        file_id: str,
    ) -> DriveFileMetadata:
        response = self._get_with_retry(
            f"{self.API_BASE_URL}/files/{file_id}",
            params={
                "fields": ("id,name,mimeType,size,trashed," "appProperties"),
            },
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned malformed metadata") from exc

        return self._parse_metadata(
            payload,
        )

    def search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> DriveFilePage:
        params = {
            "q": query,
            "fields": ("nextPageToken," "files(id,name,mimeType,size,trashed," "appProperties)"),
        }

        if page_token is not None:
            params["pageToken"] = page_token

        response = self._get_with_retry(
            f"{self.API_BASE_URL}/files",
            params=params,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned malformed file list") from exc

        if not isinstance(payload, dict):
            raise DriveError("Google Drive returned malformed file list")

        files = payload.get(
            "files",
            [],
        )
        next_page_token = payload.get(
            "nextPageToken",
        )

        if not isinstance(files, list) or (
            next_page_token is not None
            and not isinstance(
                next_page_token,
                str,
            )
        ):
            raise DriveError("Google Drive returned malformed file list")

        return DriveFilePage(
            files=tuple(self._parse_metadata(file_payload) for file_payload in files),
            next_page_token=next_page_token,
        )

    def list_children(
        self,
        parent_id: str,
        page_token: str | None = None,
    ) -> DriveFilePage:
        return self.search(
            query=f"'{parent_id}' in parents",
            page_token=page_token,
        )

    def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        app_properties: Mapping[str, str] | None = None,
    ) -> DriveFileMetadata:
        metadata: dict[str, object] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }

        if parent_id is not None:
            metadata["parents"] = [
                parent_id,
            ]

        if app_properties is not None:
            metadata["appProperties"] = dict(
                app_properties,
            )

        try:
            response = httpx.post(
                f"{self.API_BASE_URL}/files",
                headers={
                    "Authorization": (f"Bearer {self._access_token}"),
                },
                params={
                    "fields": ("id,name,mimeType,size,trashed," "appProperties"),
                },
                json=metadata,
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise DriveTransientError("Google Drive request failed temporarily") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error(
                exc,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned malformed metadata") from exc

        return self._parse_metadata(
            payload,
        )

    def upload_file(
        self,
        name: str,
        content: bytes,
        mime_type: str,
        parent_id: str | None = None,
        app_properties: Mapping[str, str] | None = None,
    ) -> DriveFileMetadata:
        metadata: dict[str, object] = {
            "name": name,
        }

        if parent_id is not None:
            metadata["parents"] = [
                parent_id,
            ]

        if app_properties is not None:
            metadata["appProperties"] = dict(
                app_properties,
            )

        multipart = [
            (
                "metadata",
                (
                    None,
                    json.dumps(metadata),
                    "application/json; charset=UTF-8",
                ),
            ),
            (
                "file",
                (
                    name,
                    content,
                    mime_type,
                ),
            ),
        ]

        try:
            response = httpx.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                headers={
                    "Authorization": (f"Bearer {self._access_token}"),
                },
                params={
                    "uploadType": "multipart",
                    "fields": ("id,name,mimeType,size,trashed," "appProperties"),
                },
                files=multipart,
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise DriveTransientError("Google Drive request failed temporarily") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error(
                exc,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned malformed metadata") from exc

        return self._parse_metadata(
            payload,
        )

    def update_metadata(
        self,
        file_id: str,
        *,
        name: str | None = None,
        app_properties: Mapping[str, str] | None = None,
    ) -> DriveFileMetadata:
        metadata: dict[str, object] = {}

        if name is not None:
            metadata["name"] = name

        if app_properties is not None:
            metadata["appProperties"] = dict(
                app_properties,
            )

        try:
            response = httpx.patch(
                f"{self.API_BASE_URL}/files/{file_id}",
                headers={
                    "Authorization": (f"Bearer {self._access_token}"),
                },
                params={
                    "fields": ("id,name,mimeType,size,trashed," "appProperties"),
                },
                json=metadata,
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise DriveTransientError("Google Drive request failed temporarily") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error(
                exc,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned malformed metadata") from exc

        return self._parse_metadata(
            payload,
        )

    def move(
        self,
        file_id: str,
        *,
        add_parent_id: str,
        remove_parent_id: str,
    ) -> DriveFileMetadata:
        try:
            response = httpx.patch(
                f"{self.API_BASE_URL}/files/{file_id}",
                headers={
                    "Authorization": (f"Bearer {self._access_token}"),
                },
                params={
                    "addParents": add_parent_id,
                    "removeParents": remove_parent_id,
                    "fields": ("id,name,mimeType,size,trashed," "appProperties"),
                },
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise DriveTransientError("Google Drive request failed temporarily") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error(
                exc,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise DriveError("Google Drive returned malformed metadata") from exc

        return self._parse_metadata(
            payload,
        )

    def trash(
        self,
        file_id: str,
    ) -> None:
        try:
            response = httpx.patch(
                f"{self.API_BASE_URL}/files/{file_id}",
                headers={
                    "Authorization": (f"Bearer {self._access_token}"),
                },
                params={
                    "fields": ("id,name,mimeType,size,trashed," "appProperties"),
                },
                json={
                    "trashed": True,
                },
                timeout=self.REQUEST_TIMEOUT,
            )
        except httpx.RequestError as exc:
            raise DriveTransientError("Google Drive request failed temporarily") from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error(
                exc,
            )

    def download_file(
        self,
        file_id: str,
        destination: Path,
        max_bytes: int,
    ) -> int:
        downloaded_bytes = 0

        try:
            with httpx.stream(
                "GET",
                f"{self.API_BASE_URL}/files/{file_id}",
                headers={
                    "Authorization": (f"Bearer {self._access_token}"),
                },
                params={
                    "alt": "media",
                },
                timeout=self.DOWNLOAD_TIMEOUT,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    self._raise_http_error(
                        exc,
                    )

                try:
                    with destination.open("wb") as output:
                        for chunk in response.iter_bytes():
                            downloaded_bytes += len(chunk)

                            if downloaded_bytes > max_bytes:
                                raise DriveDownloadTooLargeError(
                                    "Google Drive download exceeds size limit"
                                )

                            output.write(chunk)

                except DriveDownloadTooLargeError:
                    destination.unlink(
                        missing_ok=True,
                    )
                    raise

        except httpx.RequestError as exc:
            destination.unlink(
                missing_ok=True,
            )

            raise DriveTransientError("Google Drive request failed temporarily") from exc

        return downloaded_bytes

    @staticmethod
    def _raise_http_error(
        exc: httpx.HTTPStatusError,
    ) -> None:
        status_code = exc.response.status_code

        if status_code in {
            401,
            403,
        }:
            raise DriveAccessError("Google Drive access denied") from exc

        if status_code == 404:
            raise DriveNotFoundError("Google Drive resource not found") from exc

        if status_code == 409:
            raise DriveConflictError(
                "Google Drive operation conflicts with existing state"
            ) from exc

        if status_code == 429 or status_code >= 500:
            raise DriveTransientError("Google Drive request failed temporarily") from exc

        raise DriveError("Google Drive request failed") from exc

    @staticmethod
    def _parse_metadata(
        payload: object,
    ) -> DriveFileMetadata:
        if not isinstance(
            payload,
            dict,
        ):
            raise DriveError("Google Drive returned malformed metadata")

        try:
            file_id = payload["id"]
            name = payload["name"]
            mime_type = payload["mimeType"]
            trashed = payload["trashed"]
            size = payload.get("size")
            app_properties = payload.get(
                "appProperties",
                {},
            )

            if (
                not isinstance(file_id, str)
                or not isinstance(name, str)
                or not isinstance(mime_type, str)
                or type(trashed) is not bool
                or not isinstance(app_properties, dict)
            ):
                raise ValueError

            size_bytes = int(size) if size is not None else None
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise DriveError("Google Drive returned malformed metadata") from exc

        return DriveFileMetadata(
            file_id=file_id,
            name=name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            trashed=trashed,
            app_properties=app_properties,
        )

    def _get_with_retry(
        self,
        url: str,
        *,
        params: dict[str, str],
    ):
        for attempt in range(
            self.READ_MAX_ATTEMPTS,
        ):
            try:
                response = httpx.get(
                    url,
                    headers={
                        "Authorization": (f"Bearer {self._access_token}"),
                    },
                    params=params,
                    timeout=self.REQUEST_TIMEOUT,
                )

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code

                    if status_code == 429 or status_code >= 500:
                        if attempt < self.READ_MAX_ATTEMPTS - 1:
                            continue

                    self._raise_http_error(
                        exc,
                    )

                return response

            except httpx.RequestError as exc:
                if attempt < self.READ_MAX_ATTEMPTS - 1:
                    continue

                raise DriveTransientError("Google Drive request failed temporarily") from exc

            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code

                if (
                    status_code == 429 or status_code >= 500
                ) and attempt < self.READ_MAX_ATTEMPTS - 1:
                    continue

                self._raise_http_error(
                    exc,
                )

        raise AssertionError("Unreachable Drive retry state")


class DriveError(Exception):
    """Base error for Google Drive operations."""


class DriveAccessError(DriveError):
    """Raised when access to a Drive resource is denied."""


class DriveConflictError(DriveError):
    """Raised when Drive state is ambiguous or conflicting."""


class DriveDownloadTooLargeError(DriveError):
    """Raised when a Drive download exceeds the configured size limit."""


class DriveNotFoundError(DriveError):
    """Raised when a requested Drive resource does not exist."""


class DriveTransientError(DriveError):
    """Raised for retryable transient Google Drive failures."""
