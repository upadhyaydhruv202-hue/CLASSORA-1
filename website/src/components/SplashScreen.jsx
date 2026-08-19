import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import SplashScene from "./SplashScene";

export const SPLASH_ENABLED = true;

const COPY = [
  { title: "INITIALIZING CLASSORA", sub: "Classroom intelligence is coming online." },
  { title: "NETWORK FORMATION", sub: "Identity · Attendance · Voice · Risk · Support · Human Review" },
  { title: "INTELLIGENCE LAYER READY", sub: "Predicted support signals are isolated from action." },
  { title: "Human review remains in control", sub: "No intervention is created automatically." },
  { title: "SYSTEM READY", sub: "CLASSORA · SIH 2026" },
];

export default function SplashScreen({ onDone }) {
  const [phase, setPhase] = useState("in");
  const [stage, setStage] = useState(1);
  const [reduce, setReduce] = useState(false);
  const [compact, setCompact] = useState(false);
  const done = useRef(false);

  const finish = () => {
    if (done.current) return;
    done.current = true;
    document.body.style.overflow = "";
    onDone?.();
  };

  useEffect(() => {
    document.body.style.overflow = "hidden";
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const compactView = window.matchMedia("(max-width: 768px)").matches;
    setReduce(reduceMotion);
    setCompact(compactView);
    const timers = [];

    if (reduceMotion) {
      setStage(5);
      timers.push(setTimeout(() => setPhase("out"), 700));
      timers.push(setTimeout(finish, 1050));
    } else {
      timers.push(setTimeout(() => setStage(2), 750));
      timers.push(setTimeout(() => setStage(3), 2100));
      timers.push(setTimeout(() => setStage(4), 2850));
      timers.push(setTimeout(() => setStage(5), 3350));
      timers.push(setTimeout(() => setPhase("out"), 3750));
      timers.push(setTimeout(finish, 4150));
    }

    const onKey = (e) => {
      if (e.key === "Escape") {
        setPhase("out");
        timers.push(setTimeout(finish, 280));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      timers.forEach(clearTimeout);
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, []);

  const copy = COPY[Math.min(stage, 5) - 1];

  return (
    <AnimatePresence>
      {phase !== "gone" && (
        <motion.div
          role="dialog"
          aria-label="Classora system initialization"
          aria-live="polite"
          initial={{ opacity: 1 }}
          animate={phase === "out" ? { opacity: 0 } : { opacity: 1 }}
          transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
          onAnimationComplete={() => {
            if (phase === "out") finish();
          }}
          className="splash-overlay fixed inset-0 z-[80] flex items-center justify-center overflow-hidden bg-[#F6F8FC]"
        >
          <div className="pointer-events-none absolute inset-0 grid-tech opacity-55" />

          <div className="relative z-[1] flex w-full max-w-lg flex-col items-center overflow-x-hidden px-5 text-center">
            <SplashScene stage={stage} reduce={reduce} compact={compact} />

            <motion.p
              key={copy.title}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32 }}
              className="mt-1 font-display text-[clamp(1.35rem,3.4vw,1.85rem)] font-medium tracking-[-0.03em] text-[#0B1F4A]"
            >
              {copy.title}
            </motion.p>
            <motion.p
              key={copy.sub}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.32 }}
              className="mt-2 max-w-sm text-[12px] leading-5 text-[#5b6b82]"
            >
              {copy.sub}
            </motion.p>

            <div className="mt-7 h-[2px] w-[min(240px,70vw)] overflow-hidden rounded-full bg-[#d7e0ee]">
              <motion.div
                className="h-full origin-left bg-[#22D3EE]"
                initial={{ scaleX: 0 }}
                animate={{ scaleX: stage / 5 }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
