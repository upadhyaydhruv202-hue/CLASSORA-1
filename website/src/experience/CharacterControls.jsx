import { useEffect, useRef } from "react";
import { DEFAULT_CHARACTER_URL } from "./characterUrl";

const MIN_ZOOM = 0.75;
const MAX_ZOOM = 1.6;

function clamp(n, a, b) {
  return Math.min(b, Math.max(a, n));
}

export function clampTwin(engine) {
  if (!engine?.current) return;
  engine.current.twinYaw = engine.current.twinYaw || 0;
  engine.current.twinPitch = clamp(engine.current.twinPitch || 0, -0.45, 0.45);
  engine.current.twinZoom = clamp(engine.current.twinZoom || 1, MIN_ZOOM, MAX_ZOOM);
  engine.current.twinPanX = clamp(engine.current.twinPanX || 0, -0.55, 0.55);
  engine.current.twinPanY = clamp(engine.current.twinPanY || 0, -0.35, 0.35);
}

export function resetTwin(engine) {
  if (!engine?.current) return;
  engine.current.twinYaw = 0;
  engine.current.twinPitch = 0;
  engine.current.twinZoom = 1;
  engine.current.twinPanX = 0;
  engine.current.twinPanY = 0;
}

/** Overlay HUD for the in-scene TRELLIS character. No WebGL imports. */
export default function CharacterControls({ modelUrl = DEFAULT_CHARACTER_URL, engine, compact = false }) {
  const drag = useRef({ on: false, pan: false, x: 0, y: 0 });
  const surface = useRef(null);

  useEffect(() => {
    if (!engine?.current) return;
    engine.current.characterUrl = modelUrl;
    clampTwin(engine);
  }, [engine, modelUrl]);

  useEffect(() => {
    const el = surface.current;
    if (!el || compact) return;
    const onWheel = (e) => {
      if (!engine?.current) return;
      e.preventDefault();
      engine.current.twinZoom = (engine.current.twinZoom || 1) - e.deltaY * 0.0012;
      clampTwin(engine);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [engine, compact]);

  const onPointerDown = (e) => {
    if (!engine?.current) return;
    drag.current = { on: true, pan: e.button === 2 || e.ctrlKey || e.metaKey, x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current.on || !engine?.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    drag.current.x = e.clientX;
    drag.current.y = e.clientY;
    if (drag.current.pan) {
      engine.current.twinPanX = (engine.current.twinPanX || 0) - dx * 0.0025;
      engine.current.twinPanY = (engine.current.twinPanY || 0) + dy * 0.0025;
    } else {
      engine.current.twinYaw = (engine.current.twinYaw || 0) + dx * 0.008;
      engine.current.twinPitch = (engine.current.twinPitch || 0) + dy * 0.004;
    }
    clampTwin(engine);
  };
  const onPointerUp = (e) => {
    drag.current.on = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };

  const bar = (
    <div className={`cine-twin-bar ${compact ? "is-compact" : ""}`}>
      <button type="button" className="cine-twin-btn" onClick={() => engine && ((engine.current.twinYaw = (engine.current.twinYaw || 0) + 0.45), clampTwin(engine))}>
        Rotate
      </button>
      <button type="button" className="cine-twin-btn" onClick={() => engine && ((engine.current.twinZoom = (engine.current.twinZoom || 1) + 0.12), clampTwin(engine))}>
        Zoom
      </button>
      <button type="button" className="cine-twin-btn" onClick={() => resetTwin(engine)}>
        Reset
      </button>
    </div>
  );

  if (compact) return <div className="cine-twin-hud is-compact">{bar}</div>;

  return (
    <div className="cine-twin-hud">
      <div
        ref={surface}
        className="cine-twin-drag"
        role="presentation"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onContextMenu={(e) => e.preventDefault()}
      />
      {bar}
    </div>
  );
}
