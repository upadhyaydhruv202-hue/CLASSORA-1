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

function pickMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return types.find((type) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) || "";
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
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => () => stopTracks(), []);

  const stopTracks = () => {
    clearInterval(timerRef.current);
    recorderRef.current?.state === "recording" && recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
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
      const mimeType = pickMime();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data?.size) chunksRef.current.push(event.data);
      };
      recorder.start(200);
      setRecording(true);
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds((n) => n + 1), 1000);
    } catch (err) {
      setError(err.message || "Microphone permission denied. Allow the mic and try again.");
    }
  };

  const stop = async () => {
    const recorder = recorderRef.current;
    clearInterval(timerRef.current);
    if (!recorder || recorder.state === "inactive") {
      stopTracks();
      return;
    }
    const blob = await new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }));
      recorder.stop();
    });
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    setRecording(false);
    try {
      const ctx = new AudioContext();
      const buffer = await ctx.decodeAudioData(await blob.arrayBuffer());
      await ctx.close();
      const samples = buffer.getChannelData(0);
      if (!samples.length || samples.length < buffer.sampleRate * 0.8) {
        setError("Clip was too short. Record 2–4 seconds, then stop.");
        return;
      }
      const wav = encodeWav(samples, buffer.sampleRate);
      const file = new File([wav], `voice-${Date.now()}.wav`, { type: "audio/wav" });
      setPreview(URL.createObjectURL(wav));
      onCapture?.(file);
    } catch (err) {
      setError(err.message || "Could not read that recording. Try again, and speak for 2–4 seconds.");
    }
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
