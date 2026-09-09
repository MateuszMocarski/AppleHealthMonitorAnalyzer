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
_AHM_REPORT_MONTH_TYPE = "report_month"


def _build_config_container_query(root_id: str) -> str:
    return (
        f"'{root_id}' in parents and "
        "appProperties has "
        "{ key='ahm_type' and value='config_container' } and "
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


def discover_config_container(
    drive_client: DriveClient,
    *,
    root_id: str,
) -> DriveFileMetadata | None:
    page_token: str | None = None

    while True:
        page = drive_client.search(
            _build_config_container_query(root_id),
            page_token=page_token,
        )

        for file in page.files:
            if not file.trashed:
                return file

        page_token = page.next_page_token

        if page_token is None:
            return None


def ensure_config_container(
    drive_client: DriveClient,
    *,
    root_id: str,
) -> DriveFileMetadata:
    config_container = discover_config_container(
        drive_client,
        root_id=root_id,
    )

    if config_container is not None:
        return config_container

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


def discover_report_month(
    drive_client: DriveClient,
    *,
    year_id: str,
    period: str,
) -> DriveFileMetadata | None:
    query = (
        f"'{year_id}' in parents and "
        "appProperties has "
        f"{{ key='ahm_type' and value='{_AHM_REPORT_MONTH_TYPE}' }} and "
        "appProperties has "
        f"{{ key='ahm_period' and value='{period}' }} and "
        "trashed = false"
    )

    month: DriveFileMetadata | None = None
    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        for candidate in page.files:
            if month is not None:
                raise DriveConflictError(f"Multiple active AHM report months found for {period}")

            month = candidate

        if page.next_page_token is None:
            return month

        page_token = page.next_page_token


def discover_report_months(
    drive_client: DriveClient,
    *,
    year_id: str,
) -> tuple[DriveFileMetadata, ...]:
    query = (
        f"'{year_id}' in parents and "
        "appProperties has "
        f"{{ key='ahm_type' and value='{_AHM_REPORT_MONTH_TYPE}' }} and "
        "trashed = false"
    )

    months: list[DriveFileMetadata] = []
    periods: set[str] = set()
    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        for month in page.files:
            period = month.app_properties.get("ahm_period")

            if period in periods:
                raise DriveConflictError(f"Multiple active AHM report months found for {period}")

            periods.add(period)
            months.append(month)

        if page.next_page_token is None:
            return tuple(months)

        page_token = page.next_page_token


def discover_report_years(
    drive_client: DriveClient,
    *,
    reports_id: str,
) -> tuple[DriveFileMetadata, ...]:
    query = (
        f"'{reports_id}' in parents and "
        "appProperties has "
        f"{{ key='ahm_type' and value='{_AHM_YEAR_CONTAINER_TYPE}' }} and "
        "trashed = false"
    )

    years: list[DriveFileMetadata] = []
    year_values: set[str] = set()
    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        for year in page.files:
            year_value = year.app_properties.get("ahm_year")

            if year_value in year_values:
                raise DriveConflictError(f"Multiple active AHM report years found for {year_value}")

            year_values.add(year_value)
            years.append(year)

        if page.next_page_token is None:
            return tuple(years)

        page_token = page.next_page_token


def discover_reports_container(
    drive_client: DriveClient,
    *,
    root_id: str,
) -> DriveFileMetadata | None:
    query = (
        f"'{root_id}' in parents and "
        "appProperties has "
        "{ key='ahm_type' and value='reports_container' } and "
        "trashed = false"
    )

    reports: DriveFileMetadata | None = None
    page_token: str | None = None

    while True:
        page = drive_client.search(
            query,
            page_token=page_token,
        )

        for candidate in page.files:
            if reports is not None:
                raise DriveConflictError("Multiple active AHM reports containers found")

            reports = candidate

        if page.next_page_token is None:
            return reports

        page_token = page.next_page_token


def discover_report_index(
    drive_client: DriveClient,
) -> dict[str, tuple[str, ...]]:
    root = discover_ahm_root(drive_client)

    if root is None:
        return {}

    reports = discover_reports_container(
        drive_client,
        root_id=root.file_id,
    )

    if reports is None:
        return {}

    index: dict[str, tuple[str, ...]] = {}

    for year in discover_report_years(
        drive_client,
        reports_id=reports.file_id,
    ):
        year_value = year.app_properties["ahm_year"]

        months = discover_report_months(
            drive_client,
            year_id=year.file_id,
        )

        index[year_value] = tuple(month.app_properties["ahm_period"] for month in months)

    return index
