import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Badge, MagneticButton } from "./ui";
import { APP_URL } from "../content";

const HeroScene = lazy(() => import("./HeroScene"));

function hasWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function Fallback() {
  return (
    <div className="relative flex h-full min-h-[360px] items-center justify-center bg-transparent">
      <div className="hero-fallback-ring absolute h-[300px] w-[300px] max-h-[52%] max-w-[52%] rounded-full border border-[#93C5FD]/50" />
      <div className="hero-fallback-ring absolute h-[200px] w-[200px] max-h-[36%] max-w-[36%] rounded-full border border-[#22D3EE]/40" style={{ animationDelay: "1.1s" }} />
      <div className="hero-fallback-core h-[158px] w-[158px] max-h-[28%] max-w-[28%] rounded-full bg-[#0B1F4A]/90 shadow-[0_0_28px_rgba(37,99,235,0.16)]" />
    </div>
  );
}

export default function Hero({ deferScene = false }) {
  const mouse = useRef({ x: 0, y: 0 });
  const scroll = useRef(0);
  const wrap = useRef(null);
  const copy = useRef(null);
  const [reduce, setReduce] = useState(false);
  const [webgl, setWebgl] = useState(true);

  useEffect(() => {
    setReduce(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    setWebgl(hasWebGL());
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    const onMove = (e) => {
      const r = wrap.current?.getBoundingClientRect();
      if (r) {
        mouse.current.x = ((e.clientX - r.left) / r.width - 0.5) * 2;
        mouse.current.y = ((e.clientY - r.top) / r.height - 0.5) * 2;
      }
      if (reduce || coarse || !copy.current) return;
      const nx = (e.clientX / window.innerWidth - 0.5) * 2;
      const ny = (e.clientY / window.innerHeight - 0.5) * 2;
      copy.current.style.setProperty("--hx", `${(nx * -8).toFixed(1)}px`);
      copy.current.style.setProperty("--hy", `${(ny * -6).toFixed(1)}px`);
    };
    const onScroll = () => {
      const max = Math.max(document.body.scrollHeight - window.innerHeight, 1);
      scroll.current = Math.min(window.scrollY / max, 1);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("scroll", onScroll);
    };
  }, [reduce]);

  return (
    <section id="home" className="relative overflow-hidden pt-28 md:pt-32">
      <div className="pointer-events-none absolute inset-0 grid-tech opacity-80" />
      <div className="pointer-events-none absolute -top-24 left-1/2 h-[520px] w-[520px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(37,99,235,0.14),transparent_68%)]" />
      <div className="mx-auto grid max-w-6xl items-center gap-8 px-5 pb-16 lg:grid-cols-[1.05fr_1fr] lg:gap-6 lg:pb-8">
        <motion.div
          ref={copy}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="hero-copy"
        >
          <Badge>SIH 2026 · Smart Education · Classora</Badge>
          <h1 className="mt-6 font-display text-[clamp(2.15rem,5vw,3.65rem)] font-medium leading-[1.08] tracking-[-0.035em] text-[#0B1F4A]">
            Know who is present.
            <br />
            Know who needs help.
          </h1>
          <p className="mt-5 max-w-lg text-[16px] leading-7 text-[#5b6b82]">
            Manual registers waste periods and miss at-risk students. Classora turns face and voice attendance into
            institution-grade records — then a human-in-the-loop Success Hub so support is timely, explainable, and never automatic.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <MagneticButton href="#solution">Explore Solution</MagneticButton>
            <MagneticButton href={APP_URL} variant="secondary">
              Launch CLASSORA
            </MagneticButton>
          </div>
          <dl className="mt-10 grid max-w-md grid-cols-3 gap-4 border-t border-[#d7e0ee] pt-6">
            {[
              ["Face + Voice", "One roster"],
              ["Human review", "Before save"],
              ["6 campus roles", "Least privilege"],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-[12px] font-semibold text-[#0B1F4A]">{k}</dt>
                <dd className="mt-1 text-[12px] text-[#5b6b82]">{v}</dd>
              </div>
            ))}
          </dl>
        </motion.div>
        <div ref={wrap} className="relative flex h-[420px] items-center justify-center overflow-hidden bg-transparent md:h-[520px] lg:h-[560px]">
          <div className="pointer-events-none absolute h-[280px] w-[280px] rounded-full bg-[radial-gradient(circle,rgba(34,211,238,0.1),transparent_70%)] md:h-[340px] md:w-[340px]" />
          {reduce || deferScene || !webgl ? (
            <Fallback />
          ) : (
            <Suspense fallback={<Fallback />}>
              <HeroScene mouse={mouse} scroll={scroll} />
            </Suspense>
          )}
        </div>
      </div>
    </section>
  );
}
