import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Nav from "./Nav";
import Cursor from "./Cursor";
import Overlays from "./Overlays";
import { DEFAULTS, predict } from "./predict";
import { DEFAULT_CHARACTER_URL } from "./characterUrl";

const SceneMount = lazy(() => import("./SceneMount"));

function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function Experience({ active }) {
  const engine = useRef({
    scroll: 0,
    mouse: { x: 0, y: 0 },
    click: -10,
    hotNode: -1,
    hoverNode: -1,
    hoverStudent: -1,
    instHover: -1,
    factor: -1,
    risk: predict(DEFAULTS).score,
    factors: predict(DEFAULTS).factors,
    band: predict(DEFAULTS).band,
    metrics: {
      attendance: DEFAULTS.attendance,
      academic: DEFAULTS.academic,
      assignments: DEFAULTS.assignments,
      engagement: DEFAULTS.engagement,
      trend: DEFAULTS.trend,
    },
    sim: 0,
    analyze: 0,
    analyzeStep: -1,
    openIntervention: null,
    focusStudent: null,
    activity: "",
    reduce: false,
    mobile: false,
    cursor: "",
    lab: 0,
    characterUrl: DEFAULT_CHARACTER_URL,
    twinYaw: 0,
    twinPitch: 0,
    twinZoom: 1,
    twinPanX: 0,
    twinPanY: 0,
    characterError: "",
  });
  const [webgl, setWebgl] = useState(true);
  const [reduce, setReduce] = useState(false);
  const [characterUrl, setCharacterUrl] = useState(DEFAULT_CHARACTER_URL);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const applyReduce = (v) => {
      engine.current.reduce = v;
      setReduce(v);
    };
    applyReduce(motion.matches);
    engine.current.mobile = window.matchMedia("(max-width: 768px)").matches;
    setWebgl(hasWebGL());
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const max = Math.max(document.body.scrollHeight - window.innerHeight, 1);
        engine.current.scroll = Math.min(window.scrollY / max, 1);
      });
    };
    const onMove = (e) => {
      engine.current.mouse.x = (e.clientX / window.innerWidth - 0.5) * 2;
      engine.current.mouse.y = (e.clientY / window.innerHeight - 0.5) * -2;
    };
    const onClick = () => {
      engine.current.click = performance.now() / 1000;
    };
    const onReduce = (e) => applyReduce(Boolean(e.detail));
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onClick, { passive: true });
    window.addEventListener("cine-reduce", onReduce);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onClick);
      window.removeEventListener("cine-reduce", onReduce);
    };
  }, []);

  const onHotNode = useCallback((id) => {
    engine.current.hotNode = id;
  }, []);

  engine.current.characterUrl = characterUrl;
  engine.current.setCharacterUrl = setCharacterUrl;

  const dpr = useMemo(() => {
    if (typeof window === "undefined") return 1;
    const mobile = window.matchMedia("(max-width: 768px)").matches;
    return Math.min(window.devicePixelRatio || 1, mobile ? 1.1 : 1.7);
  }, []);

  return (
    <div className="cine-root">
      <Cursor engine={engine} />
      <Nav />
      {active && webgl && !reduce && (
        <div className="cine-canvas-wrap">
          <Suspense fallback={null}>
            <SceneMount engine={engine} dpr={dpr} characterUrl={characterUrl} />
          </Suspense>
        </div>
      )}
      {(!webgl || reduce) && <div className="cine-canvas-wrap cine-canvas-fallback" />}
      <main id="main" className="relative z-[1]">
        <Overlays engine={engine} onHotNode={onHotNode} characterUrl={characterUrl} />
      </main>
    </div>
  );
}
