const API_BASE_URL = "http://127.0.0.1:8000";

async function apiHealth() {
  const response = await fetch(`${API_BASE_URL}/health`, {
    method: "GET",
  });

  if (!response.ok) {
    throw new Error(`Health ${response.status}`);
  }

  return response.json();
}

async function apiTranscribe(payload) {
  const { audioBase64, mimeType, filename, model, language, summarySentences } = payload;
  if (!audioBase64 || typeof audioBase64 !== "string") {
    throw new Error("Audio base64 faltante o invalido.");
  }

  const binary = atob(audioBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: mimeType || "audio/webm" });

  const formData = new FormData();
  formData.append("audio", blob, filename || `audio_${Date.now()}.webm`);
  formData.append("model", model || "small");
  formData.append("language", language || "auto");
  formData.append("summary_sentences", String(summarySentences || 4));
  formData.append("generate_summary", "true");

  const response = await fetch(`${API_BASE_URL}/transcribe`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let details = "";
    try {
      const payload = await response.json();
      details = payload?.detail || JSON.stringify(payload);
    } catch {
      details = await response.text();
    }
    throw new Error(`API error ${response.status}: ${details || "sin detalle"}`);
  }

  return response.json();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      if (message?.type === "HEALTH") {
        const data = await apiHealth();
        sendResponse({ ok: true, data });
        return;
      }

      if (message?.type === "TRANSCRIBE") {
        const data = await apiTranscribe(message.payload || {});
        sendResponse({ ok: true, data });
        return;
      }

      sendResponse({ ok: false, error: "Tipo de mensaje no soportado" });
    } catch (error) {
      sendResponse({ ok: false, error: error?.message || "Error desconocido" });
    }
  })();

  return true;
});
