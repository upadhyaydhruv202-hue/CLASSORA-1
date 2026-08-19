import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import { nav, APP_URL } from "../content";
import { Logo, MagneticButton } from "./ui";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 18);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
        scrolled ? "glass border-b border-[#d7e0ee]/80 py-2.5 shadow-[0_8px_30px_rgba(11,31,74,0.06)]" : "bg-transparent py-4"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5">
        <Logo compact={scrolled} />
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
          {nav.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className="rounded-full px-3 py-1.5 text-[13px] font-medium text-[#5b6b82] no-underline transition-colors hover:bg-white hover:text-[#0B1F4A]"
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="hidden lg:block">
          <MagneticButton href={APP_URL} variant="primary">
            Launch CLASSORA
          </MagneticButton>
        </div>
        <button
          type="button"
          className="rounded-full border border-[#d7e0ee] bg-white p-2 text-[#0B1F4A] lg:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>
      {open && (
        <div className="glass mx-4 mt-2 rounded-2xl border border-[#d7e0ee] p-4 lg:hidden">
          {nav.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              onClick={() => setOpen(false)}
              className="block rounded-xl px-3 py-2.5 text-sm font-medium text-[#0B1F4A] no-underline hover:bg-[#F6F8FC]"
            >
              {item.label}
            </a>
          ))}
          <a href={APP_URL} className="mt-2 block rounded-full bg-[#2563EB] px-4 py-2.5 text-center text-sm font-semibold text-white no-underline">
            Launch CLASSORA
          </a>
        </div>
      )}
    </header>
  );
}
