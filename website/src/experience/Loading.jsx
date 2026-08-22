import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

export default function Loading({ onDone }) {
  const [pct, setPct] = useState(0);
  const [phase, setPhase] = useState("Loading CLASSORA");
  const done = useRef(false);
  const canvas = useRef(null);

  useEffect(() => {
    import("./SceneMount");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      onDone();
      return;
    }

    const cvs = canvas.current;
    const ctx = cvs?.getContext("2d");
    const dots = Array.from({ length: 72 }, (_, i) => {
      const a = (i / 72) * Math.PI * 2;
      return {
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        tx: window.innerWidth / 2 + Math.cos(a) * 88,
        ty: window.innerHeight / 2 + Math.sin(a) * 88,
      };
    });

    const resize = () => {
      if (!cvs) return;
      cvs.width = window.innerWidth;
      cvs.height = window.innerHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    const t0 = performance.now();
    let id;
    const tick = (now) => {
      const p = Math.min((now - t0) / 700, 1);
      const n = Math.round(p * 100);
      setPct(n);
      if (p < 0.22) setPhase("Loading CLASSORA");
      else if (p < 0.48) setPhase("Loading Digital Twin");
      else if (p < 0.78) setPhase("Initializing risk model");
      else if (p < 0.92) setPhase(`Loading ${n}%`);
      else setPhase("Ready");

      if (ctx && cvs) {
        ctx.clearRect(0, 0, cvs.width, cvs.height);
        const e = 1 - Math.pow(1 - p, 2.4);
        ctx.fillStyle = "rgba(34,211,238,0.85)";
        dots.forEach((d, i) => {
          const x = d.x + (d.tx - d.x) * e;
          const y = d.y + (d.ty - d.y) * e;
          ctx.globalAlpha = 0.35 + e * 0.65;
          ctx.beginPath();
          ctx.arc(x, y, i % 9 === 0 ? 1.8 : 1.1, 0, Math.PI * 2);
          ctx.fill();
        });
        ctx.globalAlpha = e * 0.35;
        ctx.strokeStyle = "#22D3EE";
        ctx.beginPath();
        ctx.arc(cvs.width / 2, cvs.height / 2, 88, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (p < 1) id = requestAnimationFrame(tick);
      else if (!done.current) {
        done.current = true;
        setTimeout(onDone, 80);
      }
    };
    id = requestAnimationFrame(tick);
    const skip = (e) => {
      if (e.key === "Escape") {
        done.current = true;
        onDone();
      }
    };
    window.addEventListener("keydown", skip);
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("keydown", skip);
      window.removeEventListener("resize", resize);
    };
  }, [onDone]);

  return (
    <motion.div
      className="cine-load"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, filter: "blur(12px)" }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      <canvas ref={canvas} aria-hidden />
      <div className="cine-load-copy">
        <p className="cine-kicker">CLASSORA</p>
        <p className="mt-6 font-mono text-[13px] tracking-[0.28em] text-[#E8F1FF]">{phase}</p>
        <div className="cine-load-bar" aria-hidden>
          <i style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-8 font-mono text-[10px] tracking-[0.2em] text-[#64748B]">ESC TO SKIP</p>
      </div>
    </motion.div>
  );
}
