from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import whisper
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.main import ensure_nltk_resource, summarize_text, transcribe_audio

ALLOWED_EXTENSIONS = {".opus", ".ogg", ".m4a", ".mp3", ".wav", ".aac", ".webm"}

app = FastAPI(title="WhatsApp Audio Transcription API", version="1.0.0")
logger = logging.getLogger(__name__)

# Permite llamadas desde extension de Chrome (origen chrome-extension://...) y pruebas locales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_model_cache: dict[str, whisper.Whisper] = {}


def get_model(model_name: str) -> whisper.Whisper:
    if model_name not in _model_cache:
        _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


def validate_audio_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="El archivo de audio no tiene nombre.")

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Extension no soportada: {suffix}. Permitidas: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return suffix


@app.on_event("startup")
def startup_event() -> None:
    ensure_nltk_resource()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe_endpoint(
    audio: UploadFile = File(...),
    model: str = Form("small"),
    language: str = Form("auto"),
    summary_sentences: int = Form(4),
    generate_summary: bool = Form(True),
) -> dict[str, str | int]:
    if summary_sentences < 1:
        raise HTTPException(status_code=400, detail="summary_sentences debe ser >= 1")

    suffix = validate_audio_filename(audio.filename)
    audio_bytes = await audio.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Archivo de audio vacio.")

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()

            whisper_model = get_model(model)
            transcript, detected_language = transcribe_audio(
                whisper_model,
                Path(tmp.name),
                language=language,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Fallo al transcribir archivo %s", audio.filename)
        error_message = str(exc)
        if "Invalid argument" in error_message or "does not contain any stream" in error_message:
            raise HTTPException(
                status_code=415,
                detail="El contenido recibido no es un audio valido o llega cifrado desde WhatsApp.",
            ) from exc
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo transcribir el audio ({type(exc).__name__}): {exc}",
        ) from exc

    summary = ""
    if generate_summary:
        try:
            summary = summarize_text(
                transcript,
                sentence_count=summary_sentences,
                language_code=detected_language,
            )
        except Exception as exc:
            logger.exception("Fallo al resumir archivo %s", audio.filename)
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo resumir la transcripcion ({type(exc).__name__}): {exc}",
            ) from exc

    return {
        "file_name": audio.filename or "unknown",
        "model": model,
        "language_requested": language,
        "language_detected": detected_language,
        "transcript": transcript,
        "summary": summary,
        "summary_sentences": summary_sentences,
    }
