import { useRef } from "react";
import { motion } from "framer-motion";

export function Logo({ compact = false }) {
  return (
    <a href="#home" className="flex items-center gap-2.5 no-underline text-inherit">
      <svg width={compact ? 28 : 32} height={compact ? 28 : 32} viewBox="0 0 64 64" fill="none" aria-hidden>
        <rect width="64" height="64" rx="16" fill="#0B1F4A" />
        <path d="M44.5 20.5C41.2 16.8 36.4 14.5 31 14.5C21.3 14.5 13.5 22.3 13.5 32C13.5 41.7 21.3 49.5 31 49.5C36.4 49.5 41.2 47.2 44.5 43.5" stroke="#60A5FA" strokeWidth="4.2" strokeLinecap="round" />
        <circle cx="45.5" cy="20.5" r="3.2" fill="#22D3EE" />
        <circle cx="31" cy="32" r="3.6" fill="#93C5FD" />
      </svg>
      <span className="leading-tight">
        <span className="block text-[15px] font-extrabold tracking-[-0.04em] text-[#0B1F4A]">CLASSORA</span>
        {!compact && <span className="block text-[10px] font-semibold tracking-[0.14em] uppercase text-[#5b6b82]">SIH 2026</span>}
      </span>
    </a>
  );
}

export function useTilt(enabled = true, intensity = 5) {
  const ref = useRef(null);
  const move = (e) => {
    if (!enabled || !ref.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (window.matchMedia("(pointer: coarse)").matches) return;
    const r = ref.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    ref.current.style.setProperty("--tx", `${(x * 4).toFixed(1)}px`);
    ref.current.style.setProperty("--ty", `${(y * 4).toFixed(1)}px`);
    ref.current.style.setProperty("--rx", `${(-y * intensity).toFixed(2)}deg`);
    ref.current.style.setProperty("--ry", `${(x * intensity).toFixed(2)}deg`);
  };
  const leave = () => {
    if (!ref.current) return;
    ref.current.style.setProperty("--tx", "0px");
    ref.current.style.setProperty("--ty", "0px");
    ref.current.style.setProperty("--rx", "0deg");
    ref.current.style.setProperty("--ry", "0deg");
  };
  return { ref, move, leave };
}

export function MagneticButton({ href, children, variant = "primary", onClick }) {
  const ref = useRef(null);
  const reset = () => {
    if (ref.current) ref.current.style.transform = "translate(0,0)";
  };
  const move = (e) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = ref.current.getBoundingClientRect();
    const x = (e.clientX - (r.left + r.width / 2)) * 0.22;
    const y = (e.clientY - (r.top + r.height / 2)) * 0.22;
    ref.current.style.transform = `translate(${x}px, ${y}px)`;
  };
  const cls =
    variant === "primary"
      ? "bg-[#2563EB] text-white shadow-[0_8px_18px_rgba(37,99,235,0.18)] hover:bg-[#1D4ED8]"
      : "bg-white text-[#0F172A] border border-[#E2E8F0] hover:border-[#BFDBFE]";
  return (
    <a
      ref={ref}
      href={href}
      onClick={onClick}
      onMouseMove={move}
      onMouseLeave={reset}
      className={`inline-flex items-center justify-center rounded-full px-6 py-3 text-sm font-semibold tracking-[-0.01em] no-underline transition-colors duration-200 ${cls}`}
    >
      {children}
    </a>
  );
}

export function SectionHeader({ kicker, title, body }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.4 }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      className="mx-auto max-w-2xl text-center"
    >
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#2563EB]">{kicker}</p>
      <h2 className="mt-3 font-display text-[clamp(1.75rem,3.4vw,2.75rem)] font-medium leading-[1.15] tracking-[-0.03em] text-[#0B1F4A]">
        {title}
      </h2>
      {body && <p className="mt-4 text-[15px] leading-7 text-[#5b6b82]">{body}</p>}
    </motion.div>
  );
}

export function Badge({ children }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-[#d7e0ee] bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#0B1F4A]">
      <span className="h-1.5 w-1.5 rounded-full bg-[#2563EB]" />
      {children}
    </span>
  );
}
