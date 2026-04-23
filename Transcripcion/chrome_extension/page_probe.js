(() => {
  if (window.__wtProbeInstalled) return;
  window.__wtProbeInstalled = true;

  const SOURCE = "wt-probe";
  const MAX_CAPTURE_MS = 45000;
  const recordingMedia = new WeakSet();
  const postedAudioBuffers = new WeakSet();

  const post = (payload, transfer = []) => {
    window.postMessage({ source: SOURCE, payload }, "*", transfer);
  };

  function audioBufferToWavArrayBuffer(audioBuffer) {
    const numChannels = audioBuffer.numberOfChannels;
    const sampleRate = audioBuffer.sampleRate;
    const samples = audioBuffer.length;
    const bitsPerSample = 16;
    const blockAlign = (numChannels * bitsPerSample) / 8;
    const byteRate = sampleRate * blockAlign;
    const dataSize = samples * blockAlign;
    const buffer = new ArrayBuffer(44 + dataSize);
    const view = new DataView(buffer);

    let offset = 0;
    const writeString = (str) => {
      for (let i = 0; i < str.length; i += 1) {
        view.setUint8(offset + i, str.charCodeAt(i));
      }
      offset += str.length;
    };

    writeString("RIFF");
    view.setUint32(offset, 36 + dataSize, true);
    offset += 4;
    writeString("WAVE");
    writeString("fmt ");
    view.setUint32(offset, 16, true);
    offset += 4;
    view.setUint16(offset, 1, true);
    offset += 2;
    view.setUint16(offset, numChannels, true);
    offset += 2;
    view.setUint32(offset, sampleRate, true);
    offset += 4;
    view.setUint32(offset, byteRate, true);
    offset += 4;
    view.setUint16(offset, blockAlign, true);
    offset += 2;
    view.setUint16(offset, bitsPerSample, true);
    offset += 2;
    writeString("data");
    view.setUint32(offset, dataSize, true);
    offset += 4;

    const channels = [];
    for (let ch = 0; ch < numChannels; ch += 1) {
      channels.push(audioBuffer.getChannelData(ch));
    }

    let pos = offset;
    for (let i = 0; i < samples; i += 1) {
      for (let ch = 0; ch < numChannels; ch += 1) {
        let sample = channels[ch][i];
        if (sample > 1) sample = 1;
        if (sample < -1) sample = -1;
        const intSample = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        view.setInt16(pos, intSample, true);
        pos += 2;
      }
    }

    return buffer;
  }

  function chooseMimeType() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
    return candidates.find((mime) => MediaRecorder.isTypeSupported(mime)) || "";
  }

  function stopRecorder(recorder, timerId) {
    if (timerId) {
      window.clearTimeout(timerId);
    }
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  function captureFromMedia(mediaEl, attempt = 0) {
    if (recordingMedia.has(mediaEl)) return;
    if (typeof mediaEl.captureStream !== "function") {
      post({ type: "capture-error", detail: "captureStream no soportado" });
      return;
    }

    const stream = mediaEl.captureStream();
    if (!stream || stream.getAudioTracks().length === 0) {
      if (attempt < 6) {
        const delays = [60, 120, 250, 400, 700, 1000];
        window.setTimeout(() => captureFromMedia(mediaEl, attempt + 1), delays[attempt] || 1000);
      } else {
        post({ type: "capture-error", detail: "No hay audio tracks para capturar" });
      }
      return;
    }

    const mimeType = chooseMimeType();
    let recorder;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch (error) {
      post({ type: "capture-error", detail: String(error) });
      return;
    }

    recordingMedia.add(mediaEl);
    const chunks = [];
    post({ type: "capture-started", mimeType: recorder.mimeType || mimeType || "unknown" });

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data && event.data.size > 0) {
        chunks.push(event.data);
      }
    });

    recorder.addEventListener("error", (event) => {
      recordingMedia.delete(mediaEl);
      post({ type: "capture-error", detail: String(event.error || "MediaRecorder error") });
    });

    recorder.addEventListener("stop", async () => {
      recordingMedia.delete(mediaEl);

      if (chunks.length === 0) {
        post({ type: "capture-error", detail: "No se capturaron chunks de audio" });
        return;
      }

      const blob = new Blob(chunks, { type: chunks[0].type || recorder.mimeType || "audio/webm" });
      const buffer = await blob.arrayBuffer();
      post({
        type: "captured-audio",
        mimeType: blob.type || "audio/webm",
        byteLength: buffer.byteLength,
        source: "captureStream",
        audioBuffer: buffer,
      });
    });

    let timerId = null;
    const stop = () => stopRecorder(recorder, timerId);
    mediaEl.addEventListener("pause", stop, { once: true });
    mediaEl.addEventListener("ended", stop, { once: true });

    timerId = window.setTimeout(() => {
      stopRecorder(recorder, null);
    }, MAX_CAPTURE_MS);

    recorder.start();
  }

  function mediaSnapshot(mediaEl) {
    return {
      src: mediaEl.currentSrc || mediaEl.src || "",
      tag: mediaEl.tagName || "",
      muted: Boolean(mediaEl.muted),
      volume: Number(mediaEl.volume || 0),
      isConnected: Boolean(mediaEl.isConnected),
    };
  }

  function captureFromAudioBuffer(audioBuffer) {
    if (!audioBuffer || postedAudioBuffers.has(audioBuffer)) {
      return;
    }

    if (audioBuffer.duration < 0.8) {
      return;
    }

    postedAudioBuffers.add(audioBuffer);

    try {
      const wavBuffer = audioBufferToWavArrayBuffer(audioBuffer);
      post(
        {
          type: "captured-audio",
          mimeType: "audio/wav",
          byteLength: wavBuffer.byteLength,
          source: "webaudio",
          audioBuffer: wavBuffer,
        },
        [wavBuffer],
      );
    } catch (error) {
      post({ type: "capture-error", detail: `WAV encode error: ${String(error)}` });
    }
  }


  document.addEventListener(
    "play",
    (event) => {
      const target = event.target;
      if (target instanceof HTMLMediaElement) {
        const src = target.currentSrc || target.src || "";
        post({
          type: "play",
          src,
          tag: target.tagName || "",
        });
        captureFromMedia(target);
      }
    },
    true,
  );

  const originalMediaPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function patchedMediaPlay(...args) {
    try {
      const snap = mediaSnapshot(this);
      post({ type: "media-play-hook", ...snap });
      captureFromMedia(this);
    } catch (_) {
      // noop
    }
    return originalMediaPlay.apply(this, args);
  };

  const originalSetAttribute = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function patchedSetAttribute(name, value) {
    const result = originalSetAttribute.apply(this, [name, value]);
    try {
      if (this instanceof HTMLMediaElement && String(name).toLowerCase() === "src") {
        post({
          type: "media-src-updated",
          src: this.currentSrc || this.src || String(value || ""),
          tag: this.tagName || "",
          isConnected: Boolean(this.isConnected),
        });
      }
    } catch (_) {
      // noop
    }
    return result;
  };

  const originalBufferSourceStart = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function patchedStart(...args) {
    try {
      if (this.buffer) {
        captureFromAudioBuffer(this.buffer);
      }
    } catch (_) {
      // noop
    }
    return originalBufferSourceStart.apply(this, args);
  };

  post({ type: "probe-ready" });
})();
