import { MagneticButton } from "./ui";
import { APP_URL } from "../content";

export default function FinalCTA() {
  return (
    <section id="demo" className="relative overflow-hidden py-20 md:py-28">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(37,99,235,0.12),transparent_55%)]" />
      <div className="cta-orbit" aria-hidden>
        <i />
        <i />
        <i />
      </div>
      <div className="relative mx-auto max-w-4xl px-5 text-center">
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#2563EB]">Classora · SIH 2026</p>
        <h2 className="mt-4 font-display text-[clamp(1.9rem,4vw,3.1rem)] font-medium leading-[1.12] tracking-[-0.03em] text-[#0B1F4A]">
          Building a smarter future with AI &amp; innovation.
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-[15px] leading-7 text-[#5b6b82]">
          Face and voice attendance that institutions can trust — and a Student Success Hub that refuses to act without a human.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <MagneticButton href="#solution">Explore Our Solution</MagneticButton>
          <MagneticButton href={APP_URL} variant="secondary">
            Launch CLASSORA
          </MagneticButton>
        </div>
        <div className="mx-auto mt-12 h-px max-w-sm bg-gradient-to-r from-transparent via-[#93C5FD] to-transparent" />
        <p className="mt-6 text-[12px] font-medium tracking-[0.08em] text-[#5b6b82]">
          INTELLIGENT LEARNING · CONNECTED CLASSROOMS
        </p>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-[#d7e0ee] py-8 text-center text-[12px] text-[#5b6b82]">
      <strong className="font-semibold text-[#0B1F4A]">CLASSORA</strong>
      {" · "}Smart India Hackathon 2026{" · "}Learn. Connect. Evolve.
    </footer>
  );
}
