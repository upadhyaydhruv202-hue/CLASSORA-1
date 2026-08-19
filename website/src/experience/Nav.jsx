import { useEffect, useState } from "react";
import { APP_URL, cineNav } from "../content";

export default function Nav() {
  const [on, setOn] = useState(false);
  const [open, setOpen] = useState(false);
  const [reduce, setReduce] = useState(false);

  useEffect(() => {
    const fn = () => setOn(window.scrollY > 24);
    fn();
    window.addEventListener("scroll", fn, { passive: true });
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduce(motion.matches);
    return () => window.removeEventListener("scroll", fn);
  }, []);

  const toggleMotion = () => {
    const next = !reduce;
    setReduce(next);
    document.documentElement.classList.toggle("reduce-motion", next);
    window.dispatchEvent(new CustomEvent("cine-reduce", { detail: next }));
  };

  return (
    <header className={`cine-nav fixed inset-x-0 top-0 z-50 ${on ? "is-on py-2.5" : "py-5"}`}>
      <div className="cine-nav-inner">
        <a href="#experience" className="justify-self-start no-underline">
          <span className="block text-[13px] font-extrabold tracking-[0.22em] text-[#0F172A]">CLASSORA</span>
          <span className="mt-0.5 block font-mono text-[9px] tracking-[0.18em] text-[#64748B]">
            Learn. Connect. Evolve.
          </span>
        </a>
        <nav className="hidden items-center justify-center gap-1 lg:flex" aria-label="Primary">
          {cineNav.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              className="rounded-full px-3 py-1.5 text-[12px] font-medium text-[#64748B] no-underline transition-colors hover:bg-[#EFF6FF] hover:text-[#2563EB]"
            >
              {n.label}
            </a>
          ))}
        </nav>
        <div className="hidden items-center justify-end gap-2 justify-self-end lg:flex">
          <button
            type="button"
            onClick={toggleMotion}
            className="rounded-full border border-[#E2E8F0] bg-white px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] text-[#64748B]"
            aria-pressed={reduce}
          >
            {reduce ? "MOTION ON" : "REDUCE MOTION"}
          </button>
          <a href={APP_URL} className="cine-btn cine-btn-primary text-[12px]" data-cursor="LAUNCH">
            Launch CLASSORA
          </a>
        </div>
        <button
          type="button"
          className="justify-self-end rounded-full border border-[#E2E8F0] bg-white px-3 py-1.5 text-[12px] text-[#0F172A] lg:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label="Menu"
          aria-expanded={open}
        >
          Menu
        </button>
      </div>
      {open && (
        <div className="cine-panel mx-4 mt-2 rounded-2xl p-4 lg:hidden">
          {cineNav.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              onClick={() => setOpen(false)}
              className="block py-2 text-sm text-[#0F172A] no-underline"
            >
              {n.label}
            </a>
          ))}
          <button type="button" onClick={toggleMotion} className="mt-2 font-mono text-[10px] tracking-[0.14em] text-[#64748B]">
            {reduce ? "Enable motion" : "Reduce motion"}
          </button>
          <a href={APP_URL} className="cine-btn cine-btn-primary mt-3 w-full">
            Launch CLASSORA
          </a>
        </div>
      )}
    </header>
  );
}
