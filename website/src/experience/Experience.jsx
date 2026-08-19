import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Nav from "./Nav";
import Cursor from "./Cursor";
import Overlays from "./Overlays";
import { DEFAULTS, predict } from "./predict";

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
    sim: 0,
    reduce: false,
    mobile: false,
  });
  const [webgl, setWebgl] = useState(true);
  const [reduce, setReduce] = useState(false);

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

  const dpr = useMemo(() => {
    if (typeof window === "undefined") return 1;
    const mobile = window.matchMedia("(max-width: 768px)").matches;
    return Math.min(window.devicePixelRatio || 1, mobile ? 1.05 : 1.45);
  }, []);

  return (
    <div className="cine-root">
      <Cursor />
      <Nav />
      {active && webgl && !reduce && (
        <div className="pointer-events-none fixed inset-0 z-0">
          <Suspense fallback={null}>
            <SceneMount engine={engine} dpr={dpr} />
          </Suspense>
        </div>
      )}
      {(!webgl || reduce) && (
        <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(ellipse_at_70%_40%,rgba(37,99,235,0.10),#F8FAFC_62%)]" />
      )}
      <main id="main" className="relative z-[1]">
        <Overlays engine={engine} onHotNode={onHotNode} />
      </main>
    </div>
  );
}
