import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { APP_URL } from "../content";

const ease = [0.22, 1, 0.36, 1];

const signals = ["Face attendance", "Voice match", "Human review"];

export default function Hero({ metrics, pred }) {
  const prefersReduce = useReducedMotion();
  const [toggled, setToggled] = useState(false);

  useEffect(() => {
    const apply = (value) => setToggled(Boolean(value));
    apply(document.documentElement.classList.contains("reduce-motion"));
    const onReduce = (event) => apply(event.detail);
    window.addEventListener("cine-reduce", onReduce);
    return () => window.removeEventListener("cine-reduce", onReduce);
  }, []);

  const skip = Boolean(prefersReduce || toggled);
  const item = {
    hidden: skip ? { opacity: 1, y: 0 } : { opacity: 0, y: 18 },
    show: {
      opacity: 1,
      y: 0,
      transition: skip ? { duration: 0 } : { duration: 0.5, ease },
    },
  };
  const ringColor = pred.band.includes("HIGH") ? "#f87171" : pred.band.includes("NEEDS") ? "#fbbf24" : "#34d399";

  return (
    <section id="experience" className="cine-section cine-hero">
      <motion.div
        className="cine-shell"
        initial="hidden"
        animate="show"
        variants={{
          hidden: {},
          show: {
            transition: skip ? { duration: 0 } : { staggerChildren: 0.09, delayChildren: 0.08 },
          },
        }}
      >
        <div className="cine-hero-copy">
          <motion.p className="cine-kicker" variants={item}>
            AI attendance and student success
          </motion.p>
          <motion.h1 className="cine-display cine-hero-title" variants={item}>
            Predict risk.
            <br />
            Prevent dropout.
          </motion.h1>
          <motion.p className="cine-body cine-hero-body" variants={item}>
            Faculty capture a class photo or a short recording. CLASSORA matches the enrolled roster, then explains support-risk for a counsellor to review — not a diagnosis, and never automatic.
          </motion.p>
          <motion.div className="cine-hero-hud" variants={item}>
            <div className="cine-hud-chip">
              <span>Attendance</span>
              <strong>{metrics.attendance}%</strong>
            </div>
            <div className="cine-hud-chip">
              <span>Academic</span>
              <strong>{metrics.academic}%</strong>
            </div>
            <div className="cine-hud-chip">
              <span>Assignments</span>
              <strong>{metrics.assignments}%</strong>
            </div>
            <div className="cine-hud-risk" style={{ color: ringColor }}>
              <strong>{pred.score}%</strong>
              <span>{pred.band}</span>
            </div>
          </motion.div>
          <motion.div className="cine-hero-actions" variants={item}>
            <motion.a
              href={APP_URL}
              className="cine-btn cine-btn-primary"
              data-cursor="LAUNCH"
              whileHover={skip ? undefined : { y: -1 }}
              whileTap={skip ? undefined : { scale: 0.98 }}
            >
              Launch CLASSORA
            </motion.a>
            <a href="#ai-demo" className="cine-btn cine-btn-ghost" data-cursor="EXPLORE">
              Explore the AI
            </a>
          </motion.div>
          <motion.ul className="cine-hero-signals" variants={item}>
            {signals.map((label) => (
              <li key={label}>{label}</li>
            ))}
          </motion.ul>
        </div>
        <div className="cine-stage cine-hero-visual" aria-hidden="true" />
      </motion.div>
    </section>
  );
}
