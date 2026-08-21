import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { APP_URL, cineNav } from "../content";

const ease = [0.22, 1, 0.36, 1];

export default function Nav() {
  const [on, setOn] = useState(false);
  const [open, setOpen] = useState(false);
  const [reduce, setReduce] = useState(false);
  const [active, setActive] = useState(cineNav[0]?.id || "experience");
  const menuBtn = useRef(null);
  const panel = useRef(null);
  const prefersReduce = useReducedMotion();
  const skip = Boolean(prefersReduce || reduce);

  useEffect(() => {
    const fn = () => setOn(window.scrollY > 24);
    fn();
    window.addEventListener("scroll", fn, { passive: true });
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduce(motionQuery.matches || document.documentElement.classList.contains("reduce-motion"));
    return () => window.removeEventListener("scroll", fn);
  }, []);

  useEffect(() => {
    const ids = cineNav.map((item) => item.id);
    const nodes = ids.map((id) => document.getElementById(id)).filter(Boolean);
    if (!nodes.length) return undefined;
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (hit?.target?.id) setActive(hit.target.id);
      },
      { rootMargin: "-18% 0px -62% 0px", threshold: [0.08, 0.25, 0.5] },
    );
    nodes.forEach((node) => io.observe(node));
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => [...(panel.current?.querySelectorAll("a,button") || [])];
    requestAnimationFrame(() => focusable()[0]?.focus());

    const onKey = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        menuBtn.current?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const onPointer = (event) => {
      const target = event.target;
      if (panel.current?.contains(target) || menuBtn.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  useEffect(() => {
    const onResize = () => {
      if (window.matchMedia("(min-width: 1024px)").matches) setOpen(false);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const closeMenu = () => {
    setOpen(false);
    menuBtn.current?.focus();
  };

  const toggleMotion = () => {
    const next = !reduce;
    setReduce(next);
    document.documentElement.classList.toggle("reduce-motion", next);
    window.dispatchEvent(new CustomEvent("cine-reduce", { detail: next }));
  };

  const instant = skip ? { duration: 0 } : { duration: 0.45, ease };
  const spring = skip ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 32 };

  return (
    <motion.header
      className={`cine-nav fixed inset-x-0 top-0 z-50 ${on ? "is-on" : ""}`}
      initial={skip ? false : { y: -16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={instant}
    >
      <div className="cine-nav-inner">
        <a href="#experience" className="cine-nav-brand justify-self-start no-underline" data-cursor="HOME">
          <span className="block text-[13px] font-extrabold tracking-[0.22em] text-[#0F172A]">CLASSORA</span>
          <span className="mt-0.5 block font-mono text-[9px] tracking-[0.18em] text-[#64748B]">Learn. Connect. Evolve.</span>
        </a>

        <nav className="cine-nav-links" aria-label="Primary">
          {cineNav.map((item) => {
            const current = active === item.id;
            return (
              <a
                key={item.id}
                href={`#${item.id}`}
                aria-current={current ? "location" : undefined}
                className={`cine-nav-link ${current ? "is-active" : ""}`}
              >
                {!skip && current && (
                  <motion.span className="cine-nav-pill" layoutId="cine-nav-pill" transition={spring} />
                )}
                <span className="relative z-[1]">{item.label}</span>
              </a>
            );
          })}
        </nav>

        <div className="cine-nav-actions">
          <button
            type="button"
            onClick={toggleMotion}
            className="cine-nav-ghost"
            aria-pressed={reduce}
          >
            {reduce ? "Motion on" : "Reduce motion"}
          </button>
          <motion.a
            href={APP_URL}
            className="cine-btn cine-btn-primary cine-nav-cta"
            data-cursor="LAUNCH"
            whileHover={skip ? undefined : { y: -1 }}
            whileTap={skip ? undefined : { scale: 0.98 }}
            transition={{ duration: 0.18, ease }}
          >
            Launch CLASSORA
          </motion.a>
        </div>

        <button
          ref={menuBtn}
          type="button"
          className="cine-nav-menu justify-self-end"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            setOpen((value) => !value);
          }}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="cine-mobile-menu"
        >
          <span className="cine-nav-burger" aria-hidden="true">
            <motion.i animate={{ rotate: open ? 45 : 0, y: open ? 5 : 0 }} transition={instant} />
            <motion.i animate={{ opacity: open ? 0 : 1 }} transition={instant} />
            <motion.i animate={{ rotate: open ? -45 : 0, y: open ? -5 : 0 }} transition={instant} />
          </span>
          <span className="cine-nav-menu-label">{open ? "Close" : "Menu"}</span>
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={panel}
            id="cine-mobile-menu"
            key="cine-mobile-menu"
            className="cine-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Site menu"
            initial={skip ? false : { opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={skip ? { opacity: 1 } : { opacity: 0, y: -8 }}
            transition={instant}
          >
            <nav aria-label="Mobile">
              {cineNav.map((item, index) => (
                <motion.a
                  key={item.id}
                  href={`#${item.id}`}
                  onClick={closeMenu}
                  className={`cine-nav-drawer-link ${active === item.id ? "is-active" : ""}`}
                  aria-current={active === item.id ? "location" : undefined}
                  initial={skip ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={skip ? { duration: 0 } : { delay: 0.04 * index, duration: 0.28, ease }}
                >
                  {item.label}
                </motion.a>
              ))}
            </nav>
            <button type="button" onClick={toggleMotion} className="cine-nav-ghost mt-3 w-full" aria-pressed={reduce}>
              {reduce ? "Enable motion" : "Reduce motion"}
            </button>
            <a href={APP_URL} className="cine-btn cine-btn-primary mt-3 w-full" data-cursor="LAUNCH">
              Launch CLASSORA
            </a>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
