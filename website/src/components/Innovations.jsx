import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ScanFace, AudioLines, ShieldCheck, LayoutDashboard, LineChart, Sparkles } from "lucide-react";
import { innovations } from "../content";
import { SectionHeader, useTilt } from "./ui";

const icons = [ScanFace, AudioLines, ShieldCheck, LayoutDashboard, LineChart, Sparkles];

function FeatureCard({ item, i, Icon, open, setOpen }) {
  const tilt = useTilt(true, 5);
  const active = open === i;
  return (
    <motion.article
      ref={tilt.ref}
      onHoverStart={() => setOpen(i)}
      onHoverEnd={() => setOpen(null)}
      onFocus={() => setOpen(i)}
      onBlur={() => setOpen(null)}
      onMouseMove={tilt.move}
      onMouseLeave={() => {
        tilt.leave();
        setOpen(null);
      }}
      tabIndex={0}
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: i * 0.05 }}
      className="fx-tilt group rounded-2xl border border-[#d7e0ee] bg-[#F6F8FC] p-6 outline-none hover:border-[#93C5FD] hover:bg-white hover:shadow-[0_18px_40px_rgba(37,99,235,0.12)] focus-visible:border-[#2563EB]"
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0B1F4A] text-white">
        <Icon size={18} />
      </div>
      <h3 className="mt-4 text-[16px] font-semibold text-[#0B1F4A]">{item.title}</h3>
      <p className="mt-2 text-[13px] leading-6 text-[#5b6b82]">{item.line}</p>
      <AnimatePresence>
        {active && (
          <motion.p
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden pt-3 text-[13px] leading-6 text-[#0B1F4A]"
          >
            {item.more}
          </motion.p>
        )}
      </AnimatePresence>
    </motion.article>
  );
}

export default function Innovations() {
  const [open, setOpen] = useState(null);
  return (
    <section id="innovations" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5">
        <SectionHeader
          kicker="Key innovations"
          title="Technology that is meaningful in a classroom — not decorative AI."
          body="Each capability maps to a real workflow already running in Classora."
        />
        <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-3" style={{ perspective: "1200px" }}>
          {innovations.map((item, i) => {
            const Icon = icons[i];
            return (
              <FeatureCard key={item.title} item={item} i={i} Icon={Icon} open={open} setOpen={setOpen} />
            );
          })}
        </div>
      </div>
    </section>
  );
}
