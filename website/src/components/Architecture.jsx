import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { stack } from "../content";
import { SectionHeader, useTilt } from "./ui";

const POS = {
  fe: { x: 12, y: 22 },
  be: { x: 38, y: 18 },
  ai: { x: 64, y: 22 },
  db: { x: 38, y: 52 },
  ext: { x: 14, y: 72 },
  users: { x: 66, y: 72 },
};

const LINKS = [
  ["fe", "be"],
  ["be", "ai"],
  ["be", "db"],
  ["ai", "db"],
  ["db", "ext"],
  ["db", "users"],
  ["fe", "users"],
];

export default function Architecture() {
  const [hot, setHot] = useState("be");
  const active = stack.find((s) => s.id === hot) || stack[1];
  const panel = useRef(null);
  const detail = useTilt(true, 4);

  const onMove = (e) => {
    if (!panel.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (window.matchMedia("(pointer: coarse)").matches) return;
    const r = panel.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    panel.current.style.setProperty("--px", x.toFixed(3));
    panel.current.style.setProperty("--py", y.toFixed(3));
  };
  const onLeave = () => {
    if (!panel.current) return;
    panel.current.style.setProperty("--px", "0");
    panel.current.style.setProperty("--py", "0");
  };

  return (
    <section id="architecture" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeader
          kicker="Technology / Architecture"
          title="A clean network — frontend to campus users — with AI isolated where it belongs."
          body="Hover a node to see its purpose. Face/voice pipelines stay separate from the success-risk model."
        />
        <div className="mt-12 grid items-center gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div
            ref={panel}
            className="fx-arch relative overflow-hidden rounded-[28px] border border-[#d7e0ee] bg-[#F6F8FC] p-4"
            onMouseMove={onMove}
            onMouseLeave={onLeave}
          >
            <svg viewBox="0 0 100 96" className="fx-arch-svg h-auto w-full" role="img" aria-label="Classora architecture network">
              {LINKS.map(([a, b]) => (
                <line
                  key={a + b}
                  x1={POS[a].x}
                  y1={POS[a].y}
                  x2={POS[b].x}
                  y2={POS[b].y}
                  stroke={hot === a || hot === b ? "#2563EB" : "#c5d4ea"}
                  strokeWidth={hot === a || hot === b ? 0.7 : 0.4}
                />
              ))}
              {stack.map((n) => (
                <g
                  key={n.id}
                  onMouseEnter={() => setHot(n.id)}
                  onFocus={() => setHot(n.id)}
                  tabIndex={0}
                  className="cursor-pointer"
                >
                  <circle
                    cx={POS[n.id].x}
                    cy={POS[n.id].y}
                    r={hot === n.id ? 7.2 : 6.2}
                    fill={hot === n.id ? "#0B1F4A" : "#fff"}
                    stroke={hot === n.id ? "#60A5FA" : "#0B1F4A"}
                    strokeWidth="0.6"
                  />
                  <text
                    x={POS[n.id].x}
                    y={POS[n.id].y + 11}
                    textAnchor="middle"
                    fontSize="3.2"
                    fill="#0B1F4A"
                    fontFamily="Plus Jakarta Sans, sans-serif"
                    fontWeight="600"
                  >
                    {n.label}
                  </text>
                </g>
              ))}
            </svg>
          </div>
          <motion.div
            key={active.id}
            ref={detail.ref}
            onMouseMove={detail.move}
            onMouseLeave={detail.leave}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="fx-tilt rounded-2xl border border-[#d7e0ee] bg-white p-6 shadow-[0_16px_40px_rgba(11,31,74,0.06)]"
          >
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#2563EB]">{active.label}</p>
            <h3 className="mt-2 text-xl font-semibold text-[#0B1F4A]">{active.tech}</h3>
            <p className="mt-3 text-sm leading-6 text-[#5b6b82]">{active.purpose}</p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
