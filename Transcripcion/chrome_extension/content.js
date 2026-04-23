const MODEL = "small";
const LANGUAGE = "auto";
const SUMMARY_SENTENCES = 4;
const SCAN_INTERVAL_MS = 2000;
const PROBE_EVENT_SOURCE = "wt-probe";

let panel;
let bodyContainer;
let statusEl;
let logEl;
const processedAudioSrc = new Set();
const processingAudioSrc = new Set();
let isCapturedAudioProcessing = false;
let initialized = false;
let lastDetectedMediaCount = -1;
let probeBound = false;

function createPanel() {
  if (panel) return;

  panel = document.createElement("aside");
  panel.className = "wt-panel";
  panel.innerHTML = `
    <div class="wt-panel__header">
      <h3 class="wt-panel__title">Transcripciones WhatsApp</h3>
      <div>
        <button class="wt-btn" id="wt-scan">Escanear</button>
        <button class="wt-btn" id="wt-clear">Limpiar</button>
      </div>
    </div>
    <div class="wt-panel__body">
      <div class="wt-status" id="wt-status">Esperando audios...</div>
      <div class="wt-log" id="wt-log"></div>
      <div id="wt-results"></div>
    </div>
  `;

  document.body.appendChild(panel);
  bodyContainer = panel.querySelector("#wt-results");
  statusEl = panel.querySelector("#wt-status");
  logEl = panel.querySelector("#wt-log");

  panel.querySelector("#wt-clear").addEventListener("click", () => {
    bodyContainer.innerHTML = "";
    processedAudioSrc.clear();
    processingAudioSrc.clear();
    if (logEl) {
      logEl.innerHTML = "";
    }
    setStatus("Historial de la extension limpiado.");
  });

  panel.querySelector("#wt-scan").addEventListener("click", () => {
    setStatus("Escaneo manual ejecutado...");
    scanAndProcess(document);
  });
}

function appendLog(message) {
  if (!logEl) return;
  const line = document.createElement("div");
  line.className = "wt-log__line";
  line.textContent = `${formatTime()} | ${message}`;
  logEl.prepend(line);

  while (logEl.childNodes.length > 12) {
    logEl.removeChild(logEl.lastChild);
  }
}

function setStatus(message) {
  if (statusEl) {
    statusEl.textContent = message;
  }
  appendLog(message);
}

function formatTime() {
  const now = new Date();
  return now.toLocaleString();
}

function appendResult(result) {
  const card = document.createElement("div");
  card.className = "wt-row";

  const transcript = (result.transcript || "").trim() || "(sin contenido)";
  const summary = (result.summary || "").trim() || "(sin contenido)";

  card.innerHTML = `
    <div class="wt-row__meta">${formatTime()} | Idioma detectado: ${result.language_detected}</div>
    <div class="wt-row__label">Transcripcion</div>
    <div class="wt-row__text">${escapeHtml(transcript)}</div>
    <div class="wt-row__label">Resumen</div>
    <div class="wt-row__text">${escapeHtml(summary)}</div>
  `;

  bodyContainer.prepend(card);
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function fetchAudioBlob(audioSrc) {
  const response = await fetch(audioSrc);
  if (!response.ok) {
    throw new Error(`No se pudo descargar audio (${response.status})`);
  }
  return response.blob();
}

async function captureAudioBlobFromElement(audioEl, timeoutMs = 45000) {
  if (typeof audioEl.captureStream !== "function") {
    throw new Error("El navegador no soporta captureStream para audio.");
  }

  const stream = audioEl.captureStream();
  if (!stream || stream.getAudioTracks().length === 0) {
    throw new Error("No se pudo capturar stream de audio.");
  }

  const mimeCandidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
  const mimeType = mimeCandidates.find((m) => MediaRecorder.isTypeSupported(m)) || "";
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks = [];

  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
    }, timeoutMs);

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data && event.data.size > 0) {
        chunks.push(event.data);
      }
    });

    recorder.addEventListener("stop", () => {
      window.clearTimeout(timer);
      if (chunks.length === 0) {
        reject(new Error("No se pudieron capturar datos del audio."));
        return;
      }
      const outputType = chunks[0].type || "audio/webm";
      resolve(new Blob(chunks, { type: outputType }));
    });

    recorder.addEventListener("error", () => {
      window.clearTimeout(timer);
      reject(new Error("Error al grabar audio desde el elemento."));
    });

    const stopRecorder = () => {
      if (recorder.state !== "inactive") {
        recorder.stop();
      }
      audioEl.removeEventListener("ended", stopRecorder);
      audioEl.removeEventListener("pause", stopRecorder);
    };

    audioEl.addEventListener("ended", stopRecorder, { once: true });
    audioEl.addEventListener("pause", stopRecorder, { once: true });
    recorder.start();
  });
}

function sendRuntimeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!response) {
        reject(new Error("Respuesta vacia del service worker."));
        return;
      }
      if (!response.ok) {
        reject(new Error(response.error || "Error en service worker"));
        return;
      }
      resolve(response.data);
    });
  });
}

async function sendToApi(audioBlob, filename) {
  const audioBase64 = await blobToBase64(audioBlob);
  return sendRuntimeMessage({
    type: "TRANSCRIBE",
    payload: {
      audioBase64,
      mimeType: audioBlob.type,
      filename,
      model: MODEL,
      language: LANGUAGE,
      summarySentences: SUMMARY_SENTENCES,
    },
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const commaIndex = dataUrl.indexOf(",");
      if (commaIndex === -1) {
        reject(new Error("No se pudo codificar el audio en base64."));
        return;
      }
      resolve(dataUrl.slice(commaIndex + 1));
    };
    reader.onerror = () => reject(new Error("Error al leer blob para base64."));
    reader.readAsDataURL(blob);
  });
}

function collectMediaElements(root = document) {
  const found = [];
  const visited = new Set();

  function walk(node) {
    if (!node || visited.has(node)) return;
    visited.add(node);

    if (node instanceof HTMLMediaElement) {
      found.push(node);
    }

    if (!(node instanceof Element) && node !== document && !(node instanceof ShadowRoot)) {
      return;
    }

    if (node.querySelectorAll) {
      const mediaElements = node.querySelectorAll("audio, video");
      for (const mediaEl of mediaElements) {
        found.push(mediaEl);
      }
    }

    const elements = node.querySelectorAll ? node.querySelectorAll("*") : [];
    for (const el of elements) {
      if (el.shadowRoot) {
        walk(el.shadowRoot);
      }
    }
  }

  walk(root);
  return Array.from(new Set(found));
}

function getAudioSource(audioEl) {
  return (
    audioEl.currentSrc ||
    audioEl.src ||
    audioEl.querySelector("source")?.src ||
    ""
  );
}

async function processAudioElement(audioEl) {
  const src = getAudioSource(audioEl);
  if (!src || processedAudioSrc.has(src) || processingAudioSrc.has(src)) {
    return;
  }

  processingAudioSrc.add(src);
  setStatus("Audio detectado. Transcribiendo...");

  try {
    let blob;
    try {
      blob = await fetchAudioBlob(src);
    } catch (fetchError) {
      // Fallback para URLs con restricciones CORS en WhatsApp Web.
      blob = await captureAudioBlobFromElement(audioEl);
      console.warn("Fetch bloqueado, se uso captureStream:", fetchError);
    }

    const ext = blob.type.includes("ogg") ? "ogg" : "opus";
    const filename = `audio_whatsapp_${Date.now()}.${ext}`;
    const result = await sendToApi(blob, filename);
    processedAudioSrc.add(src);
    appendResult(result);
    setStatus("Ultimo audio transcrito correctamente.");
  } catch (error) {
    console.error("Error al procesar audio:", error);
    setStatus(`Error: ${error.message}`);
  } finally {
    processingAudioSrc.delete(src);
  }
}

async function processAudioSource(src, mimeHint = "audio/ogg") {
  if (!src || processedAudioSrc.has(src) || processingAudioSrc.has(src)) {
    return;
  }

  processingAudioSrc.add(src);
  setStatus("Fuente de audio detectada. Transcribiendo...");

  try {
    const blob = await fetchAudioBlob(src);
    const ext = blob.type.includes("ogg") || mimeHint.includes("ogg") ? "ogg" : "opus";
    const filename = `audio_whatsapp_${Date.now()}.${ext}`;
    const result = await sendToApi(blob, filename);
    processedAudioSrc.add(src);
    appendResult(result);
    setStatus("Ultimo audio transcrito correctamente.");
  } catch (error) {
    console.error("Error al procesar fuente detectada:", error);
    setStatus(`Error: ${error.message}`);
  } finally {
    processingAudioSrc.delete(src);
  }
}

async function processCapturedAudioBuffer(audioBuffer, mimeType = "audio/webm") {
  if (!audioBuffer || isCapturedAudioProcessing) {
    return;
  }

  isCapturedAudioProcessing = true;
  setStatus("Audio capturado. Enviando a API...");

  try {
    const blob = new Blob([audioBuffer], { type: mimeType || "audio/webm" });
    const ext = blob.type.includes("wav")
      ? "wav"
      : blob.type.includes("ogg")
        ? "ogg"
        : blob.type.includes("webm")
          ? "webm"
          : "opus";
    const filename = `audio_whatsapp_capture_${Date.now()}.${ext}`;
    const result = await sendToApi(blob, filename);
    appendResult(result);
    setStatus("Ultimo audio transcrito correctamente.");
  } catch (error) {
    console.error("Error al procesar audio capturado:", error);
    setStatus(`Error: ${error.message}`);
  } finally {
    isCapturedAudioProcessing = false;
  }
}

function scanAndProcess(root = document) {
  const audios = collectMediaElements(root);
  if (root === document) {
    if (audios.length !== lastDetectedMediaCount) {
      lastDetectedMediaCount = audios.length;
      appendLog(`Medios detectados en DOM: ${audios.length}`);
    }
  }
  for (const audioEl of audios) {
    if (!audioEl.dataset.wtBound) {
      audioEl.dataset.wtBound = "1";
      audioEl.addEventListener("play", () => {
        appendLog("Evento play detectado en medio.");
      });
      audioEl.addEventListener("loadedmetadata", () => {
        appendLog("Evento loadedmetadata detectado en medio.");
      });
    }
  }
}

function startObserver() {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof HTMLElement)) continue;
        if (node.matches && node.matches("audio, video")) {
          processAudioElement(node);
        }
        scanAndProcess(node);
      }
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Escucha global para capturar reproducciones aunque el audio se inyecte tarde.
  document.addEventListener(
    "play",
    (event) => {
      const target = event.target;
      if (target instanceof HTMLMediaElement) {
        appendLog("Evento play global detectado.");
      }
    },
    true,
  );

  // Cuando el usuario hace click en controles del chat, WhatsApp suele crear/actualizar audio despues.
  document.addEventListener(
    "click",
    () => {
      window.setTimeout(() => scanAndProcess(document), 250);
      window.setTimeout(() => scanAndProcess(document), 900);
    },
    true,
  );

  // Respaldo para cuando WhatsApp recicla nodos sin disparar mutaciones detectables.
  window.setInterval(() => scanAndProcess(document), SCAN_INTERVAL_MS);
}

function injectPageProbe() {
  if (document.getElementById("wt-page-probe")) {
    return;
  }

  const script = document.createElement("script");
  script.id = "wt-page-probe";
  script.src = chrome.runtime.getURL("page_probe.js");
  script.async = false;
  script.onload = () => {
    appendLog("Probe inyectado desde archivo externo.");
    script.remove();
  };
  script.onerror = () => {
    appendLog("Error al inyectar probe externo (CSP o recurso no accesible).");
    script.remove();
  };

  (document.documentElement || document.head || document.body).appendChild(script);
}

function bindProbeMessages() {
  if (probeBound) return;
  probeBound = true;

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.source !== PROBE_EVENT_SOURCE || !data.payload) return;

    const payload = data.payload;
    if (payload.type === "probe-ready") {
      appendLog("Probe de pagina activo.");
      return;
    }

    if (payload.type === "capture-started") {
      appendLog("Probe inicio captura de audio.");
      return;
    }

    if (payload.type === "media-play-hook") {
      appendLog(
        `Hook play: tag=${payload.tag || "?"} connected=${payload.isConnected ? "1" : "0"} src=${payload.src ? "si" : "no"}`,
      );
      return;
    }

    if (payload.type === "media-src-updated") {
      appendLog(`Hook src actualizado en ${payload.tag || "media"}.`);
      return;
    }

    if (payload.type === "capture-error") {
      appendLog(`Probe error de captura: ${payload.detail || "sin detalle"}`);
      return;
    }

    if (payload.type === "captured-audio") {
      const source = payload.source || "desconocido";
      appendLog(`Probe envio audio capturado (${payload.byteLength || 0} bytes, source=${source}).`);

      if (source === "captureStream" || source === "webaudio") {
        processCapturedAudioBuffer(payload.audioBuffer, payload.mimeType || "audio/webm");
      } else {
        appendLog(`Captura descartada por fuente no confiable: ${source}`);
      }
      return;
    }

    if (payload.type === "play") {
      appendLog("Probe detecto reproduccion.");
      return;
    }
  });
}

async function checkApiHealth() {
  try {
    await sendRuntimeMessage({ type: "HEALTH" });
    setStatus("API conectada. Esperando audios...");
  } catch {
    setStatus("API no disponible (revisa backend local)");
  }
}

function init() {
  if (initialized) return;
  initialized = true;

  createPanel();
  bindProbeMessages();
  injectPageProbe();
  appendLog("Extension inicializada en WhatsApp Web.");
  checkApiHealth();
  scanAndProcess(document);
  startObserver();
}

if (document.readyState === "complete" || document.readyState === "interactive") {
  init();
} else {
  window.addEventListener("DOMContentLoaded", init, { once: true });
}
