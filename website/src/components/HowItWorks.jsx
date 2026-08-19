import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Camera,
  Cpu,
  Mic,
  ShieldCheck,
  Target,
  UserPlus,
  Waypoints,
} from "lucide-react";
import { workflow } from "../content";

const META = [
  { kicker: "DATA / INPUT", status: "DATA RECEIVED", icon: Camera },
  { kicker: "AI / PROCESSING", status: "PROCESSING", icon: Cpu },
  { kicker: "INTELLIGENCE", status: "ANALYZING", icon: Activity },
  { kicker: "DECISION", status: "HUMAN REVIEW REQUIRED", icon: ShieldCheck },
  { kicker: "ACTION", status: "INTERVENTION PATH", icon: Waypoints },
  { kicker: "IMPACT", status: "MEASURABLE OUTCOME", icon: Target },
];

const IMPACT = ["Attendance", "Support", "Intervention", "Outcomes"];

export default function HowItWorks() {
  const itemRefs = useRef([]);
  const root = useRef(null);
  const ratios = useRef(Array(workflow.length).fill(0));
  const [active, setActive] = useState(0);
  const [hot, setHot] = useState(null);
  const [reduce, setReduce] = useState(false);
  const [coarse, setCoarse] = useState(false);
  const live = hot ?? active;

  useEffect(() => {
    const motionMq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const pointerMq = window.matchMedia("(pointer: coarse)");
    const sync = () => {
      setReduce(motionMq.matches);
      setCoarse(pointerMq.matches);
    };
    sync();
    motionMq.addEventListener("change", sync);
    pointerMq.addEventListener("change", sync);
    return () => {
      motionMq.removeEventListener("change", sync);
      pointerMq.removeEventListener("change", sync);
    };
  }, []);

  useEffect(() => {
    const nodes = itemRefs.current.filter(Boolean);
    if (!nodes.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const idx = Number(entry.target.getAttribute("data-stage"));
          if (!Number.isNaN(idx)) ratios.current[idx] = entry.intersectionRatio;
        });
        let best = 0;
        let bestR = -1;
        ratios.current.forEach((ratio, i) => {
          if (ratio > bestR) {
            bestR = ratio;
            best = i;
          }
        });
        if (bestR > 0) setActive(best);
      },
      { threshold: [0.15, 0.35, 0.55, 0.75, 1], rootMargin: "-18% 0px -48% 0px" },
    );
    nodes.forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, []);

  return (
    <section id="workflow" className="relative overflow-x-hidden py-20 md:py-28">
      <div className="pointer-events-none absolute inset-0 grid-tech opacity-55" />
      <div className="relative mx-auto max-w-6xl px-5">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#2563EB]">How it works</p>
          <h2 className="mt-3 font-display text-[clamp(1.75rem,3.4vw,2.75rem)] font-medium leading-[1.18] tracking-[-0.03em] text-[#0B1F4A]">
            Input to impact —
            <br />
            with a human checkpoint
            <br />
            on every consequential step.
          </h2>
        </motion.div>

        <div
          ref={root}
          data-active={live}
          data-processing={live === 1 ? "true" : "false"}
          className="hiw-pipe relative mt-16 md:mt-20"
          onMouseMove={(e) => {
            if (reduce || coarse || !root.current) return;
            const r = root.current.getBoundingClientRect();
            const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
            const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
            root.current.style.setProperty("--px", x.toFixed(3));
            root.current.style.setProperty("--py", y.toFixed(3));
          }}
          onMouseLeave={() => {
            if (!root.current) return;
            root.current.style.setProperty("--px", "0");
            root.current.style.setProperty("--py", "0");
          }}
        >
          <Spine reduce={reduce} live={live} />

          <ol className="relative z-[1] space-y-9 md:space-y-12">
            {workflow.map((w, i) => (
              <li
                key={w.step}
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                data-stage={i}
              >
                <StageRow
                  index={i}
                  step={w}
                  meta={META[i]}
                  live={live === i}
                  passed={i < live}
                  reduce={reduce}
                  coarse={coarse}
                  onEnter={() => setHot(i)}
                  onLeave={() => setHot(null)}
                />
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Spine({ reduce, live }) {
  const fill = ((live + 1) / workflow.length) * 100;
  const durBase = live === 1 ? 7 : 12;
  return (
    <div className="hiw-spine" aria-hidden>
      <div className="hiw-spine-glow" />
      <div className="hiw-spine-core" />
      <div className="hiw-spine-fill" style={{ height: `${fill}%` }} />
      {!reduce && (
        <svg className="hiw-spine-svg" viewBox="0 0 32 1000" preserveAspectRatio="none">
          <path id="hiw-path" d="M16 18 V 982" fill="none" stroke="transparent" strokeWidth="2" />
          {Array.from({ length: 8 }, (_, i) => (
            <circle key={i} r={i % 3 === 0 ? 2.4 : 1.8} className="hiw-dot" fill={i % 2 ? "#2563EB" : "#22D3EE"}>
              <animateMotion dur={`${durBase + (i % 3)}s`} begin={`${i * 1.55}s`} repeatCount="indefinite">
                <mpath href="#hiw-path" />
              </animateMotion>
            </circle>
          ))}
        </svg>
      )}
    </div>
  );
}

function StageRow({ index, step, meta, live, passed, reduce, coarse, onEnter, onLeave }) {
  const right = index % 2 === 1;
  const Icon = meta.icon;
  return (
    <div
      className={`hiw-row grid grid-cols-[32px_1fr] items-start gap-4 md:grid-cols-[1fr_56px_1fr] md:gap-0 ${
        live ? "is-live" : passed ? "is-passed" : "is-wait"
      }`}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <div className={`hidden md:block ${right ? "md:col-start-3" : "md:col-start-1 md:justify-self-end"}`}>
        <StageCard
          index={index}
          step={step}
          meta={meta}
          Icon={Icon}
          live={live}
          right={right}
          reduce={reduce}
          coarse={coarse}
          onEnter={onEnter}
          onLeave={onLeave}
        />
        {index === 3 && <HumanBadge />}
      </div>

      <div className="relative z-[2] flex justify-center pt-[1.35rem] md:col-start-2 md:row-start-1">
        <StageNode live={live} passed={passed} reduce={reduce} impact={index === 5} />
      </div>

      <div className="md:hidden">
        <StageCard
          index={index}
          step={step}
          meta={meta}
          Icon={Icon}
          live={live}
          right={false}
          reduce={reduce}
          coarse
          onEnter={onEnter}
          onLeave={onLeave}
        />
        {index === 3 && <HumanBadge />}
      </div>
    </div>
  );
}

function StageCard({ index, step, meta, Icon, live, right, reduce, coarse, onEnter, onLeave }) {
  const ref = useRef(null);
  const onMove = (e) => {
    if (reduce || coarse || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width - 0.5) * 2;
    const y = ((e.clientY - r.top) / r.height - 0.5) * 2;
    ref.current.style.setProperty("--tx", `${(x * 4).toFixed(1)}px`);
    ref.current.style.setProperty("--ty", `${(y * 4).toFixed(1)}px`);
    ref.current.style.setProperty("--rx", `${(-y * 2).toFixed(2)}deg`);
    ref.current.style.setProperty("--ry", `${(x * 2).toFixed(2)}deg`);
  };
  const reset = () => {
    if (!ref.current) return;
    ref.current.style.setProperty("--tx", "0px");
    ref.current.style.setProperty("--ty", "0px");
    ref.current.style.setProperty("--rx", "0deg");
    ref.current.style.setProperty("--ry", "0deg");
  };

  return (
    <article
      ref={ref}
      role="button"
      tabIndex={0}
      aria-current={live ? "step" : undefined}
      aria-pressed={live}
      aria-label={`${step.step}. ${meta.kicker}. ${step.title}. ${step.body}`}
      onMouseMove={onMove}
      onMouseLeave={reset}
      onFocus={onEnter}
      onBlur={onLeave}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onEnter();
        }
      }}
      className={`hiw-card ${live ? "is-on" : ""} ${right ? "hiw-card-right" : "hiw-card-left"} ${
        index === 3 ? "hiw-card-human" : ""
      } ${index === 5 ? "hiw-card-impact" : ""}`}
    >
      <span className={`hiw-arm ${right ? "hiw-arm-right" : "hiw-arm-left"}`} aria-hidden />
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-bold tracking-[0.16em] text-[#2563EB]">{step.step}</p>
        <span className={`hiw-status ${live ? "is-on" : ""}`}>
          <i />
          {live ? meta.status : "STANDBY"}
        </span>
      </div>
      <p className="mt-3 text-[10px] font-bold uppercase tracking-[0.16em] text-[#0891B2]">{meta.kicker}</p>
      <div className="mt-1.5 flex items-center gap-2">
        <span className="hiw-ico" aria-hidden>
          <Icon size={14} strokeWidth={2.1} />
        </span>
        <h3 className="text-[16px] font-semibold text-[#0B1F4A]">{step.title}</h3>
      </div>
      <p className="mt-2 text-[13px] leading-6 text-[#5b6b82]">{step.body}</p>
      <div className={`hiw-viz-slot ${live ? "is-on" : ""}`}>
        <StageVisual index={index} />
      </div>
    </article>
  );
}

function StageVisual({ index }) {
  if (index === 0) {
    return (
      <div className="hiw-viz flex gap-2">
        <span>
          <Camera size={11} strokeWidth={2.2} /> Photos
        </span>
        <span>
          <Mic size={11} strokeWidth={2.2} /> Voice
        </span>
        <span>
          <UserPlus size={11} strokeWidth={2.2} /> Enroll
        </span>
      </div>
    );
  }
  if (index === 1) {
    return (
      <div className="hiw-rings">
        <i />
        <i />
      </div>
    );
  }
  if (index === 2) {
    return (
      <svg className="hiw-wave" viewBox="0 0 88 22">
        {Array.from({ length: 11 }, (_, i) => (
          <rect key={i} x={i * 8} y="10" width="3.2" height="2" rx="1.4" />
        ))}
      </svg>
    );
  }
  if (index === 3) {
    return (
      <p className="hiw-human-line">
        <ShieldCheck size={12} strokeWidth={2.2} /> Human review required
      </p>
    );
  }
  if (index === 4) {
    return (
      <div className="hiw-actions" aria-hidden>
        <span />
        <span />
        <span />
      </div>
    );
  }
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2563EB]">Observed impact</p>
      <div className="hiw-viz mt-2 flex flex-wrap gap-1.5">
        {IMPACT.map((m) => (
          <span key={m}>{m}</span>
        ))}
      </div>
    </div>
  );
}

function StageNode({ live, passed, reduce, impact }) {
  return (
    <span className={`hiw-node ${live ? "is-on" : passed ? "is-passed" : ""} ${impact && live ? "is-impact" : ""}`}>
      <span className="hiw-node-sats" aria-hidden>
        <i />
        <i />
        <i />
        <i />
      </span>
      <span className="hiw-node-ring" />
      <span className="hiw-node-core" />
      {live && !reduce ? <span className="hiw-node-pulse" /> : null}
      {impact && live && !reduce ? <span className="hiw-node-pulse hiw-node-pulse-2" /> : null}
    </span>
  );
}

function HumanBadge() {
  return (
    <div className="hiw-badge mt-3 max-w-[240px]">
      <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[#2563EB]">
        <ShieldCheck size={12} aria-hidden /> Human checkpoint
      </p>
      <p className="mt-1 text-[11px] leading-4 text-[#5b6b82]">Final decision stays with authorized staff.</p>
    </div>
  );
}
