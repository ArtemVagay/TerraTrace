"""Точка сборки: подключаем страницы, статические файлы и API."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routers.account import acc_router
from routers.logs import log_router

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="TerraTrace", version="0.1.0", description="Учебный анализатор логов модов")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(log_router)
app.include_router(acc_router)


@app.get("/", include_in_schema=False)
async def home():
    """HTML — каркас страницы. Данные отчёта подставит JavaScript."""
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/api/health", tags=["service"])
async def health():
    return {"status": "ok", "project": "TerraTrace", "version": "0.1.0"}

