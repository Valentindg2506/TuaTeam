from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import tempfile

import streamlit as st
import whisper

from main import summarize_text, transcribe_audio

SUPPORTED_EXTENSIONS = ["opus", "ogg", "m4a", "mp3", "wav"]
HISTORY_FILE = Path(__file__).resolve().parents[1] / "historial_transcripciones.json"
REQUIRED_HISTORY_KEYS = {
    "fecha",
    "archivo",
    "idioma_detectado",
    "caracteres_transcripcion",
    "caracteres_resumen",
    "resumen_preview",
}


def initialize_session_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = load_history_from_json()


def validate_history_rows(data: object) -> list[dict[str, str]]:
    if not isinstance(data, list):
        return []

    valid_rows: list[dict[str, str]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        if not REQUIRED_HISTORY_KEYS.issubset(row.keys()):
            continue
        valid_rows.append({key: str(row.get(key, "")) for key in REQUIRED_HISTORY_KEYS})

    return valid_rows


def load_history_from_json() -> list[dict[str, str]]:
    if not HISTORY_FILE.exists():
        return []

    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    return validate_history_rows(data)


def save_history_to_json(rows: list[dict[str, str]]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_history_csv(rows: list[dict[str, str]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "fecha",
            "archivo",
            "idioma_detectado",
            "caracteres_transcripcion",
            "caracteres_resumen",
            "resumen_preview",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


@st.cache_resource
def load_model(model_name: str) -> whisper.Whisper:
    return whisper.load_model(model_name)


def process_uploaded_file(
    model: whisper.Whisper,
    uploaded_file,
    language: str,
    summary_sentences: int,
    generate_summary: bool,
) -> tuple[str, str, str]:
    suffix = Path(uploaded_file.name).suffix or ".tmp"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp_file:
        temp_file.write(uploaded_file.getbuffer())
        temp_file.flush()

        transcript, detected_language = transcribe_audio(model, Path(temp_file.name), language)
        summary = (
            summarize_text(transcript, summary_sentences, language_code=detected_language)
            if generate_summary
            else ""
        )

    return transcript, summary, detected_language


def main() -> None:
    st.set_page_config(page_title="Transcripcion WhatsApp", page_icon="🎧", layout="wide")
    initialize_session_state()

    st.title("Transcriptor y Resumen de Audios de WhatsApp")
    st.caption("Sube audios y obten transcripcion + resumen automaticamente")

    with st.sidebar:
        st.header("Configuracion")
        model_name = st.selectbox("Modelo Whisper", ["tiny", "base", "small", "medium", "large"], index=2)
        language = st.text_input(
            "Idioma",
            value="auto",
            help="Ejemplo: auto, es, en, pt",
        )
        summary_sentences = st.slider("Frases del resumen", min_value=1, max_value=10, value=4)
        generate_summary = st.toggle("Generar resumen", value=True)

        st.divider()
        st.subheader("Respaldo historial")
        history_json = json.dumps(st.session_state.history, ensure_ascii=False, indent=2)
        st.download_button(
            label="Descargar respaldo JSON",
            data=history_json,
            file_name="historial_transcripciones_backup.json",
            mime="application/json",
        )

        uploaded_history = st.file_uploader(
            "Restaurar desde JSON",
            type=["json"],
            accept_multiple_files=False,
            key="history_restore_uploader",
        )

        if uploaded_history is not None and st.button("Restaurar historial", type="secondary"):
            try:
                loaded_data = json.loads(uploaded_history.getvalue().decode("utf-8"))
                restored_rows = validate_history_rows(loaded_data)
                st.session_state.history = restored_rows
                save_history_to_json(st.session_state.history)
                st.success(f"Historial restaurado: {len(restored_rows)} registros.")
                st.rerun()
            except (UnicodeDecodeError, json.JSONDecodeError):
                st.error("El archivo no es un JSON valido en UTF-8.")

    files = st.file_uploader(
        "Sube uno o varios audios de WhatsApp",
        type=SUPPORTED_EXTENSIONS,
        accept_multiple_files=True,
    )

    if not files:
        st.info("Esperando archivos de audio...")

    if files and st.button("Procesar audios", type="primary"):
        with st.spinner("Cargando modelo Whisper..."):
            model = load_model(model_name)

        for audio_file in files:
            st.divider()
            st.subheader(audio_file.name)
            st.audio(audio_file.getvalue())

            with st.spinner(f"Procesando {audio_file.name}..."):
                transcript, summary, detected_language = process_uploaded_file(
                    model=model,
                    uploaded_file=audio_file,
                    language=language,
                    summary_sentences=summary_sentences,
                    generate_summary=generate_summary,
                )

            st.caption(f"Idioma detectado: {detected_language}")

            history_row = {
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "archivo": audio_file.name,
                "idioma_detectado": detected_language,
                "caracteres_transcripcion": str(len(transcript)),
                "caracteres_resumen": str(len(summary)),
                "resumen_preview": summary[:140].replace("\n", " "),
            }
            st.session_state.history.append(history_row)
            save_history_to_json(st.session_state.history)

            st.markdown("**Transcripcion**")
            st.text_area(
                label=f"Transcripcion de {audio_file.name}",
                value=transcript,
                height=180,
                label_visibility="collapsed",
            )
            st.download_button(
                label="Descargar transcripcion",
                data=transcript,
                file_name=f"{Path(audio_file.name).stem}.transcripcion.txt",
                mime="text/plain",
            )

            if generate_summary:
                st.markdown("**Resumen**")
                st.text_area(
                    label=f"Resumen de {audio_file.name}",
                    value=summary,
                    height=120,
                    label_visibility="collapsed",
                )
                st.download_button(
                    label="Descargar resumen",
                    data=summary,
                    file_name=f"{Path(audio_file.name).stem}.resumen.txt",
                    mime="text/plain",
                )

    if st.session_state.history:
        st.divider()
        st.subheader("Historial de la sesion")
        st.dataframe(st.session_state.history, use_container_width=True)

        history_csv = build_history_csv(st.session_state.history)
        st.download_button(
            label="Descargar historial (CSV)",
            data=history_csv,
            file_name="historial_transcripciones.csv",
            mime="text/csv",
        )

        if st.button("Limpiar historial"):
            st.session_state.history = []
            save_history_to_json(st.session_state.history)
            st.rerun()


if __name__ == "__main__":
    main()
