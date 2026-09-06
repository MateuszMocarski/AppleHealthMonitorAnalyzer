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
_AHM_ROOT_NAME = "Apple Health Monitor"
_AHM_ROOT_APP_PROPERTIES = {
    "ahm_type": "root",
    "ahm_version": "1",
}
_AHM_CONFIG_CONTAINER_NAME = "config"
_AHM_CONFIG_CONTAINER_APP_PROPERTIES = {
    "ahm_type": "config_container",
}
_AHM_REPORTS_CONTAINER_NAME = "reports"
_AHM_REPORTS_CONTAINER_APP_PROPERTIES = {
    "ahm_type": "reports_container",
}
_AHM_YEAR_CONTAINER_TYPE = "year_container"


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


def ensure_ahm_root(
    drive_client: DriveClient,
) -> DriveFileMetadata:
    root = discover_ahm_root(drive_client)

    if root is not None:
        return root

    return drive_client.create_folder(
        name=_AHM_ROOT_NAME,
        app_properties=_AHM_ROOT_APP_PROPERTIES,
    )


def ensure_config_container(
    drive_client: DriveClient,
    *,
    root_id: str,
) -> DriveFileMetadata:
    query = (
        f"'{root_id}' in parents and "
        "appProperties has "
        "{ key='ahm_type' and value='config_container' } and "
        "trashed = false"
    )

    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        if page.files:
            return page.files[0]

        if page.next_page_token is None:
            break

        page_token = page.next_page_token

    return drive_client.create_folder(
        name=_AHM_CONFIG_CONTAINER_NAME,
        parent_id=root_id,
        app_properties=_AHM_CONFIG_CONTAINER_APP_PROPERTIES,
    )


def ensure_reports_container(
    drive_client: DriveClient,
    *,
    root_id: str,
) -> DriveFileMetadata:
    query = (
        f"'{root_id}' in parents and "
        "appProperties has "
        "{ key='ahm_type' and value='reports_container' } and "
        "trashed = false"
    )

    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        if page.files:
            return page.files[0]

        if page.next_page_token is None:
            break

        page_token = page.next_page_token

    return drive_client.create_folder(
        name=_AHM_REPORTS_CONTAINER_NAME,
        parent_id=root_id,
        app_properties=_AHM_REPORTS_CONTAINER_APP_PROPERTIES,
    )


def ensure_year_container(
    drive_client: DriveClient,
    *,
    reports_id: str,
    year: int,
) -> DriveFileMetadata:
    year_value = str(year)
    app_properties = {
        "ahm_type": _AHM_YEAR_CONTAINER_TYPE,
        "ahm_year": year_value,
    }
    query = (
        f"'{reports_id}' in parents and "
        "appProperties has "
        f"{{ key='ahm_type' and value='{_AHM_YEAR_CONTAINER_TYPE}' }} and "
        "appProperties has "
        f"{{ key='ahm_year' and value='{year_value}' }} and "
        "trashed = false"
    )

    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        if page.files:
            return page.files[0]

        if page.next_page_token is None:
            break

        page_token = page.next_page_token

    return drive_client.create_folder(
        name=year_value,
        parent_id=reports_id,
        app_properties=app_properties,
    )
