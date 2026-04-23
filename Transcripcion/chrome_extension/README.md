# WhatsApp Web Transcriptor Extension (MVP)

## Que hace

- Detecta elementos de audio en `web.whatsapp.com`.
- Descarga el audio desde la pagina.
- Lo envia a la API local (`http://127.0.0.1:8000/transcribe`).
- Muestra transcripcion y resumen en un panel flotante.

## Requisitos

1. API local corriendo:

```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload
```

2. Chrome/Chromium con modo desarrollador activado.

## Cargar extension

1. Ir a `chrome://extensions`.
2. Activar `Developer mode`.
3. Click en `Load unpacked`.
4. Seleccionar esta carpeta (`chrome_extension`).
5. Abrir `https://web.whatsapp.com`.

## Notas

- Es un MVP y depende de la estructura de WhatsApp Web.
- Si WhatsApp Web cambia su HTML, puede requerir ajustes en `content.js`.
- El historial del panel de extension se puede limpiar con el boton `Limpiar`.
- Las llamadas a la API local se hacen desde `background.js` para evitar bloqueos de CORS/mixed-content del contexto de WhatsApp Web.
