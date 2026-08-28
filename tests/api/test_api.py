from fastapi.testclient import TestClient

from apple_health.api.app import app

client = TestClient(app)


# =====================================================================
# Verifies that the health endpoint confirms that the API is running.
# =====================================================================


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

# =====================================================================
# Verifies that report generation rejects an invalid reporting month.
# =====================================================================


def test_report_generation_rejects_invalid_month() -> None:
    response = client.post(
        "/reports/generate",
        data={
            "year": "2026",
            "month": "13",
        },
        files={
            "archive": (
                "export.zip",
                b"not-a-real-zip",
                "application/zip",
            ),
        },
    )

    assert response.status_code == 422