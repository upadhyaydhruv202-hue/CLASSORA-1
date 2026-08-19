import { useEffect, useRef } from "react";

export default function Cursor() {
  const dot = useRef(null);
  const label = useRef(null);

  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) return undefined;
    const pos = { x: 0, y: 0 };
    let hot = false;
    const onMove = (e) => {
      pos.x = e.clientX;
      pos.y = e.clientY;
      if (dot.current) dot.current.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
      if (label.current) label.current.style.transform = `translate3d(${pos.x + 18}px, ${pos.y + 18}px, 0)`;
      const t = e.target?.closest?.("[data-cursor]");
      const next = Boolean(t);
      if (next !== hot) {
        hot = next;
        dot.current?.classList.toggle("is-hot", hot);
        if (label.current) {
          label.current.textContent = t?.getAttribute("data-cursor") || "EXPLORE";
          label.current.style.opacity = hot ? "1" : "0";
        }
      }
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  return (
    <>
      <div ref={dot} className="cine-cursor" aria-hidden />
      <div ref={label} className="cine-cursor-label" aria-hidden />
    </>
  );
}
