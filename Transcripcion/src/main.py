from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

import nltk
import whisper
from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lsa import LsaSummarizer

SUPPORTED_EXTENSIONS = {".opus", ".ogg", ".m4a", ".mp3", ".wav"}
SUMY_LANGUAGE_MAP = {
    "es": "spanish",
    "en": "english",
    "pt": "portuguese",
    "fr": "french",
    "it": "italian",
    "de": "german",
}


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe audios de WhatsApp y genera resumenes automaticamente.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Ruta a un archivo de audio o a una carpeta con audios.",
    )
    parser.add_argument(
        "--output",
        default=Path("./output"),
        type=Path,
        help="Carpeta donde guardar transcripciones y resumenes.",
    )
    parser.add_argument(
        "--model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Modelo de Whisper a utilizar.",
    )
    parser.add_argument(
        "--language",
        default="auto",
        help="Idioma del audio (ejemplo: es, en, pt) o 'auto' para detectar automaticamente.",
    )
    parser.add_argument(
        "--summary-sentences",
        type=int,
        default=4,
        help="Cantidad de frases para el resumen.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Desactiva la generacion de resumen.",
    )
    return parser.parse_args()


def collect_audio_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Archivo no soportado: {input_path.name}. "
                f"Extensiones validas: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        return [input_path]

    if input_path.is_dir():
        files = [
            p
            for p in sorted(input_path.rglob("*"))
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if not files:
            raise ValueError("No se encontraron audios compatibles en la carpeta indicada.")
        return files

    raise ValueError("La ruta de entrada no existe o no es valida.")


def ensure_nltk_resource() -> None:
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        logging.info("Descargando recurso NLTK 'punkt' por primera vez...")
        nltk.download("punkt", quiet=True)


def resolve_whisper_language(language: str) -> str | None:
    normalized = language.strip().lower()
    if normalized in {"", "auto"}:
        return None
    return normalized


def transcribe_audio(model: whisper.Whisper, audio_path: Path, language: str) -> tuple[str, str]:
    logging.info("Transcribiendo: %s", audio_path)
    whisper_language = resolve_whisper_language(language)
    result = model.transcribe(str(audio_path), language=whisper_language)
    text = (result.get("text") or "").strip()
    detected_language = (result.get("language") or "unknown").strip().lower()
    return text, detected_language


def summarize_text(text: str, sentence_count: int, language_code: str = "es") -> str:
    clean_text = text.strip()
    if not clean_text:
        return ""

    tokenizer_language = SUMY_LANGUAGE_MAP.get(language_code.lower(), "spanish")
    parser = PlaintextParser.from_string(clean_text, Tokenizer(tokenizer_language))
    summarizer = LsaSummarizer()

    sentences = list(summarizer(parser.document, sentence_count))
    summary = " ".join(str(sentence) for sentence in sentences).strip()

    if not summary:
        return clean_text
    return summary


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def process_files(
    model: whisper.Whisper,
    audio_files: Iterable[Path],
    output_dir: Path,
    language: str,
    summary_sentences: int,
    generate_summary: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for audio_file in audio_files:
        transcript, detected_language = transcribe_audio(model, audio_file, language=language)
        logging.info("Idioma detectado en %s: %s", audio_file.name, detected_language)

        transcript_file = output_dir / f"{audio_file.stem}.transcripcion.txt"
        write_text(transcript_file, transcript)
        logging.info("Transcripcion guardada en: %s", transcript_file)

        if generate_summary:
            summary = summarize_text(
                transcript,
                sentence_count=summary_sentences,
                language_code=detected_language,
            )
            summary_file = output_dir / f"{audio_file.stem}.resumen.txt"
            write_text(summary_file, summary)
            logging.info("Resumen guardado en: %s", summary_file)


def main() -> None:
    setup_logging()
    args = parse_args()

    if args.summary_sentences < 1:
        raise ValueError("--summary-sentences debe ser mayor o igual a 1.")

    audio_files = collect_audio_files(args.input)
    ensure_nltk_resource()

    logging.info("Cargando modelo Whisper '%s'...", args.model)
    model = whisper.load_model(args.model)

    process_files(
        model=model,
        audio_files=audio_files,
        output_dir=args.output,
        language=args.language,
        summary_sentences=args.summary_sentences,
        generate_summary=not args.no_summary,
    )

    logging.info("Proceso completado. Audios procesados: %s", len(audio_files))


if __name__ == "__main__":
    main()
