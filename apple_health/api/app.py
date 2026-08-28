from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, UploadFile

from apple_health.api.models import ReportResponse
from apple_health.application.application import AppleHealthApplication
from apple_health.application.run_options import RunOptions


app = FastAPI(
    title="Apple Health Monitor Analyzer",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports/generate", response_model=ReportResponse)
def generate_report(
    archive: UploadFile = File(),
    year: int = Form(gt=0),
    month: int = Form(ge=1, le=12),
) -> ReportResponse:
    with NamedTemporaryFile(suffix=".zip") as temporary_archive:
        temporary_archive.write(archive.file.read())
        temporary_archive.flush()

        options = RunOptions(
            archive_path=Path(temporary_archive.name),
            year=year,
            month=month,
            month_summary=False,
            output_format="json",
            config_path=None,
        )

        content = AppleHealthApplication().run(options)

    return ReportResponse(
        year=year,
        month=month,
        content=content,
    )