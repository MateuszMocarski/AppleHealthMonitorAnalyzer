from apple_health.google.drive import (
    DriveClient,
    DriveConflictError,
    DriveFileMetadata,
)

_AHM_ROOT_QUERY = (
    "appProperties has { key='ahm_type' and value='root' } and "
    "appProperties has { key='ahm_version' and value='1' } and "
    "trashed = false"
)


def discover_ahm_root(
    drive_client: DriveClient,
) -> DriveFileMetadata | None:
    root: DriveFileMetadata | None = None
    page_token: str | None = None

    while True:
        page = drive_client.search(
            _AHM_ROOT_QUERY,
            page_token=page_token,
        )

        for candidate in page.files:
            if root is not None:
                raise DriveConflictError("Multiple active AHM roots found")

            root = candidate

        if page.next_page_token is None:
            return root

        page_token = page.next_page_token
