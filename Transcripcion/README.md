# App de Transcripcion de Audios de WhatsApp

Esta app permite:

1. Transcribir audios de WhatsApp (`.opus`, `.ogg`, `.m4a`, `.mp3`, `.wav`).
2. Generar un resumen automatico del texto transcrito.

## Requisitos

- Python 3.9+
- `ffmpeg` instalado en el sistema (necesario para decodificar audio)

En Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

## Instalacion

```bash
cd Transcripcion
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso rapido

### 1) Procesar un solo audio

```bash
python src/main.py --input /ruta/audio_whatsapp.opus
```

### 2) Procesar una carpeta completa

```bash
python src/main.py --input /ruta/carpeta_audios --output ./salidas
```

### 3) Usar app web (Streamlit)

```bash
streamlit run src/app.py
```

Luego abre la URL local que te muestra Streamlit, sube uno o varios audios y presiona el boton de procesamiento.
La interfaz muestra un reproductor por cada audio, su transcripcion y su resumen.
Tambien veras un historial de la sesion en forma de tabla con opcion de descarga CSV.
Ese historial queda persistido automaticamente en `historial_transcripciones.json`.
Desde la barra lateral puedes descargar un respaldo JSON y restaurarlo en cualquier momento.

### 4) Usar extension de Chrome en WhatsApp Web

Primero levanta la API local:

```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload
```

Luego carga la extension:

1. Abre `chrome://extensions`.
2. Activa `Developer mode`.
3. Click en `Load unpacked`.
4. Selecciona la carpeta `Transcripcion/chrome_extension`.
5. Abre `https://web.whatsapp.com`.

La extension muestra un panel flotante y, al detectar audios en el chat, envia el archivo a la API local para obtener transcripcion y resumen automaticamente.

Notas de la extension:

- Requiere que la API local este corriendo en `http://127.0.0.1:8000`.
- El panel permite limpiar historial local de la extension.
- La transcripcion/resumen tambien se sigue pudiendo usar desde Streamlit.

## Parametros utiles

- `--model`: modelo Whisper (`tiny`, `base`, `small`, `medium`, `large`).
  - Default: `small`
- `--language`: idioma esperado del audio o `auto` para deteccion automatica. Default: `auto`
- `--summary-sentences`: numero de frases del resumen extractivo. Default: `4`

Ejemplo:

```bash
python src/main.py \
  --input /ruta/audios \
  --output ./salidas \
  --model small \
  --language auto \
  --summary-sentences 5
```

## Salida

Por cada audio procesado, se generan dos archivos en la carpeta de salida:

- `<nombre_audio>.transcripcion.txt`
- `<nombre_audio>.resumen.txt`

## Notas

- La primera ejecucion puede tardar mas porque Whisper descarga el modelo.
- Si no quieres resumir, agrega `--no-summary`.
