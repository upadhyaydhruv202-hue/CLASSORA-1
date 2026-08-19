import { useEffect, useRef, useState } from "react";

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const write = (offset, text) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export default function MicRecorder({
  onCapture,
  label = "Record classroom audio",
  hint = 'Students should say “I am present” clearly, one after another.',
}) {
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [preview, setPreview] = useState("");
  const chunksRef = useRef([]);
  const ctxRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => () => stopAll(), []);

  const stopAll = () => {
    clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    ctxRef.current?.close?.();
    streamRef.current = null;
    ctxRef.current = null;
    setRecording(false);
  };

  const start = async () => {
    setError("");
    setPreview("");
    onCapture?.(null);
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      streamRef.current = stream;
      const ctx = new AudioContext({ sampleRate: 16000 });
      ctxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (event) => {
        chunksRef.current.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(processor);
      processor.connect(ctx.destination);
      setRecording(true);
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds((n) => n + 1), 1000);
    } catch (err) {
      setError(err.message || "Microphone permission denied. Allow the mic and try again.");
    }
  };

  const stop = async () => {
    clearInterval(timerRef.current);
    const pieces = chunksRef.current;
    const total = pieces.reduce((sum, chunk) => sum + chunk.length, 0);
    const samples = new Float32Array(total);
    let offset = 0;
    for (const chunk of pieces) {
      samples.set(chunk, offset);
      offset += chunk.length;
    }
    const rate = ctxRef.current?.sampleRate || 16000;
    stopAll();
    if (!samples.length) {
      setError("No audio captured. Try again.");
      return;
    }
    const blob = encodeWav(samples, rate);
    const file = new File([blob], `voice-${Date.now()}.wav`, { type: "audio/wav" });
    setPreview(URL.createObjectURL(blob));
    onCapture?.(file);
  };

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-[#334155]">{label}</p>
      {hint && <p className="text-xs text-[#64748B]">{hint}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap items-center gap-3">
        {!recording ? (
          <button type="button" onClick={start} className="co-btn">
            Start recording
          </button>
        ) : (
          <button type="button" onClick={stop} className="co-btn" style={{ background: "#DC2626", borderColor: "#DC2626" }}>
            Stop · {seconds}s
          </button>
        )}
        {recording && <span className="text-sm text-red-600">Listening…</span>}
      </div>
      {preview && <audio controls src={preview} className="w-full" />}
    </div>
  );
}
