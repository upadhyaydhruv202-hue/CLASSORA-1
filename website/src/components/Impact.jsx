import { useEffect, useRef, useState } from "react";
import { metrics } from "../content";
import { SectionHeader, useTilt } from "./ui";

function useCount(target, start) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!start) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setN(target);
      return;
    }
    const t0 = performance.now();
    let id;
    const tick = (now) => {
      const p = Math.min((now - t0) / 1100, 1);
      setN(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [start, target]);
  return n;
}

function Metric({ item, start }) {
  const n = useCount(item.value, start);
  const tilt = useTilt(true, 4);
  return (
    <article
      ref={tilt.ref}
      onMouseMove={tilt.move}
      onMouseLeave={tilt.leave}
      className="fx-tilt rounded-2xl border border-[#d7e0ee] bg-white p-5 hover:border-[#93C5FD] hover:shadow-[0_16px_32px_rgba(11,31,74,0.07)]"
    >
      <div className="flex items-end gap-1">
        <p className="font-display text-4xl text-[#0B1F4A]">{n}</p>
        <p className="mb-1 text-sm font-semibold text-[#2563EB]">{item.suffix}</p>
      </div>
      <h3 className="mt-3 text-sm font-semibold text-[#0B1F4A]">{item.label}</h3>
      <p className="mt-1 text-[12px] leading-5 text-[#5b6b82]">{item.detail}</p>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[#E8EEF8]">
        <div
          className="h-full rounded-full bg-[#2563EB] transition-all duration-1000"
          style={{ width: start ? `${Math.min(100, 28 + (item.value % 60))}%` : "0%" }}
        />
      </div>
    </article>
  );
}

export default function Impact() {
  const ref = useRef(null);
  const [start, setStart] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setStart(true), { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section id="impact" className="py-20 md:py-28" ref={ref}>
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeader
          kicker="Impact & benefits"
          title="Measured as institutional trust — not vanity user-counts we cannot claim."
          body="Classora reports what the system actually governs today. Scale follows deployments; honesty stays first."
        />
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" style={{ perspective: "1100px" }}>
          {metrics.map((m) => (
            <Metric key={m.label} item={m} start={start} />
          ))}
        </div>
      </div>
    </section>
  );
}
