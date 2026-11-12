"""HTTP-запросы. Сам разбор текста находится в services/."""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from schemas.log_schema import AnalysisReport, TextLogRequest
from services.log_parser import MAX_BYTES, LogInputError, analyze_log, decode_log

log_router = APIRouter(tags=["logs"])
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@log_router.get("/logs", include_in_schema=False)
async def get_logs():
    return RedirectResponse("/")


@log_router.post("/api/logs/analyze", response_model=AnalysisReport)
async def analyze_uploaded_log(file: UploadFile = File(...)):
    """К этой функции обращается кнопка «Разобрать лог»."""
    filename = (file.filename or "client.log").replace("\\", "/").rsplit("/", 1)[-1]
    try:
        if Path(filename).suffix.lower() not in {".log", ".txt"}:
            raise HTTPException(415, "Выбери текстовый файл .log или .txt.")
        data = await file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Файл больше 5 МиБ. Выбери более короткий журнал.")
        return analyze_log(decode_log(data), filename)
    except LogInputError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


@log_router.post("/api/logs/text", response_model=AnalysisReport)
async def analyze_pasted_log(payload: TextLogRequest):
    try:
        if len(payload.text.encode("utf-8")) > MAX_BYTES:
            raise HTTPException(413, "Текст больше 5 МиБ.")
        return analyze_log(payload.text, "Вставленный текст.log")
    except LogInputError as exc:
        raise HTTPException(400, str(exc)) from exc


@log_router.get("/api/logs/demo", response_model=AnalysisReport)
async def demo_report():
    """Демонстрация тоже проходит через настоящий анализатор."""
    return analyze_log((EXAMPLES / "boss_test.log").read_text(encoding="utf-8"), "boss_test.log")


@log_router.get("/api/logs/example", include_in_schema=False)
async def download_example():
    return FileResponse(EXAMPLES / "boss_test.log", filename="boss_test.log", media_type="text/plain")

