import { useEffect, useRef } from "react";

export default function Cursor({ engine }) {
  const dot = useRef(null);
  const label = useRef(null);

  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;
    const pos = { x: 0, y: 0 };
    let hot = false;
    let raf = 0;
    const onMove = (e) => {
      pos.x = e.clientX;
      pos.y = e.clientY;
      if (dot.current) dot.current.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
      if (label.current) label.current.style.transform = `translate3d(${pos.x + 18}px, ${pos.y + 18}px, 0)`;
      const t = e.target?.closest?.("[data-cursor]");
      const fromDom = t?.getAttribute("data-cursor") || "";
      const from3d = engine?.current?.cursor || "";
      const nextLabel = fromDom || from3d;
      const next = Boolean(nextLabel);
      if (next !== hot || (next && label.current && label.current.textContent !== nextLabel)) {
        hot = next;
        dot.current?.classList.toggle("is-hot", hot);
        if (label.current) {
          label.current.textContent = nextLabel || "EXPLORE";
          label.current.style.opacity = hot ? "1" : "0";
        }
      }
    };
    const poll = () => {
      const from3d = engine?.current?.cursor || "";
      if (!hot && from3d && label.current) {
        hot = true;
        dot.current?.classList.toggle("is-hot", true);
        label.current.textContent = from3d;
        label.current.style.opacity = "1";
      }
      if (hot && !from3d && label.current && !document.elementFromPoint(pos.x, pos.y)?.closest?.("[data-cursor]")) {
        hot = false;
        dot.current?.classList.toggle("is-hot", false);
        label.current.style.opacity = "0";
      }
      raf = requestAnimationFrame(poll);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    raf = requestAnimationFrame(poll);
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [engine]);

  return (
    <>
      <div ref={dot} className="cine-cursor" aria-hidden />
      <div ref={label} className="cine-cursor-label" aria-hidden />
    </>
  );
}
