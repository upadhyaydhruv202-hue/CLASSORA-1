import { useEffect, useRef, useState } from "react";

export default function CameraCapture({
  onCapture,
  onFiles,
  label = "Position your face in the center",
  hint = "Face a light source — avoid a bright window behind you.",
  facingMode = "user",
  mirrorPreview = true,
  gallery = false,
  captureLabel = "Capture",
  maxSide = 640,
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState("");
  const [shots, setShots] = useState([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode, width: { ideal: maxSide }, height: { ideal: Math.round(maxSide * 0.75) } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
          setReady(true);
        }
      } catch (err) {
        setError(err.message || "Camera permission denied. Allow the camera and reload.");
      }
    })();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [facingMode, maxSide]);

  const takeBlob = async () => {
    const video = videoRef.current;
    if (!video || !ready) return null;
    const sourceW = video.videoWidth || 640;
    const sourceH = video.videoHeight || 480;
    const scale = Math.min(1, maxSide / Math.max(sourceW, sourceH));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(sourceW * scale));
    canvas.height = Math.max(1, Math.round(sourceH * scale));
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.72));
  };

  const snap = async () => {
    const blob = await takeBlob();
    if (!blob) return;
    const file = new File([blob], `capture-${Date.now()}.jpg`, { type: "image/jpeg" });
    const url = URL.createObjectURL(blob);
    if (gallery) {
      const next = [...shots, { file, url }];
      setShots(next);
      onFiles?.(next.map((item) => item.file));
    } else {
      setPreview(url);
      onCapture?.(file);
    }
  };

  const clear = () => {
    setPreview("");
    onCapture?.(null);
  };

  const removeShot = (index) => {
    const next = shots.filter((_, i) => i !== index);
    setShots(next);
    onFiles?.(next.map((item) => item.file));
  };

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-[#334155]">{label}</p>
      {hint && <p className="text-xs text-[#64748B]">{hint}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="overflow-hidden rounded-3xl border border-[#E2E8F0] bg-black">
        {!gallery && preview ? (
          <img src={preview} alt="Captured" className="mx-auto max-h-80 w-full object-contain" />
        ) : (
          <video
            ref={videoRef}
            playsInline
            muted
            autoPlay
            className={`mx-auto max-h-80 w-full object-cover ${mirrorPreview ? "scale-x-[-1]" : ""}`}
          />
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {gallery || !preview ? (
          <button type="button" onClick={snap} disabled={!ready} className="co-btn">
            {gallery ? `${captureLabel} (${shots.length})` : captureLabel}
          </button>
        ) : (
          <button type="button" onClick={clear} className="co-btn co-btn-secondary">
            Retake
          </button>
        )}
      </div>
      {gallery && shots.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {shots.map((shot, index) => (
            <button key={shot.url} type="button" onClick={() => removeShot(index)} className="relative">
              <img src={shot.url} alt={`Shot ${index + 1}`} className="h-16 w-16 rounded-xl object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
