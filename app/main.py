from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.routers import check_database, router


app = FastAPI(
    title="API de Mesários",
    description="Coleta rastreável de registros públicos oficiais de mesários.",
    version="0.1.0",
)
app.include_router(router)
app.add_api_route("/health", check_database, methods=["GET"], tags=["saúde"])


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(
        Path(__file__).with_name("dashboard.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )