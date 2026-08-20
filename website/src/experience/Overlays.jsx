import { useEffect, useMemo, useState } from "react";
import {
  APP_URL,
  classroomStudents,
  impactCapabilities,
  interventions,
  networkStudents,
  pipeline,
  team,
  techNodes,
} from "../content";
import { DEFAULTS, predict, RECOVERED } from "./predict";

function Mag({ href, children, ghost, onClick }) {
  return (
    <a href={href} onClick={onClick} data-cursor="EXPLORE" className={`cine-btn ${ghost ? "cine-btn-ghost" : "cine-btn-primary"}`}>
      {children}
    </a>
  );
}

function Section({ id, children }) {
  return (
    <section id={id} className="cine-section">
      <div className="cine-shell">{children}</div>
    </section>
  );
}

function Capability({ label, body }) {
  return (
    <article className="cine-panel rounded-2xl p-5">
      <p className="font-mono text-[10px] tracking-[0.18em] text-[#2563EB]">{label}</p>
      <p className="mt-2 text-[15px] leading-6 text-[#0F172A]">{body}</p>
    </article>
  );
}

export default function Overlays({ engine, onHotNode }) {
  const [form, setForm] = useState(DEFAULTS);
  const [simulating, setSimulating] = useState(false);
  const [open, setOpen] = useState(null);
  const [factor, setFactor] = useState(null);
  const [probe, setProbe] = useState(2);
  const [node, setNode] = useState(0);
  const pred = useMemo(() => predict(form), [form]);

  useEffect(() => {
    engine.current.risk = pred.score;
  }, [engine, pred.score]);

  useEffect(() => {
    engine.current.hoverStudent = probe;
  }, [engine, probe]);

  useEffect(() => {
    engine.current.instHover = node;
  }, [engine, node]);

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const highlightFactor = (key, i) => {
    setFactor(key);
    engine.current.factor = i;
  };

  const clearFactor = () => {
    setFactor(null);
    engine.current.factor = -1;
  };

  const simulate = () => {
    if (simulating) return;
    setSimulating(true);
    const from = { ...form };
    const t0 = performance.now();
    const tick = (now) => {
      const u = Math.min((now - t0) / 5200, 1);
      const e = 1 - Math.pow(1 - u, 3);
      const next = {
        attendance: Math.round(from.attendance + (RECOVERED.attendance - from.attendance) * e),
        academic: Math.round(from.academic + (RECOVERED.academic - from.academic) * e),
        assignments: Math.round(from.assignments + (RECOVERED.assignments - from.assignments) * e),
        engagement: e > 0.55 ? "HIGH" : e > 0.25 ? "MEDIUM" : from.engagement,
        trend: e > 0.4 ? "IMPROVING" : from.trend,
      };
      setForm(next);
      engine.current.sim = e;
      if (u < 1) requestAnimationFrame(tick);
      else setSimulating(false);
    };
    requestAnimationFrame(tick);
  };

  const student = classroomStudents[probe];
  const inst = networkStudents[node];
  const ringColor = pred.band.includes("HIGH") ? "#ef4444" : pred.band.includes("NEEDS") ? "#f59e0b" : "#22c55e";

  return (
    <div className="relative">
      <Section id="experience">
        <div className="cine-span-5">
          <p className="cine-kicker">AI attendance and student success</p>
          <h1 className="cine-display mt-5 text-[clamp(3rem,7.2vw,6.2rem)]">
            Predict Risk.
            <br />
            Prevent Dropout.
          </h1>
          <p className="cine-body mt-6">AI-powered early intervention for students before it's too late.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Mag href={APP_URL}>Launch CLASSORA</Mag>
            <Mag href="#ai-demo" ghost>
              Explore the AI
            </Mag>
          </div>
        </div>
        <div className="cine-stage" aria-hidden />
      </Section>

      <Section id="problem">
        <div className="cine-span-5">
          <p className="cine-kicker">01 — Detect</p>
          <h2 className="cine-h2 mt-4">Dropout rarely happens suddenly.</h2>
          <p className="cine-body mt-4">There are measurable signals before the exit.</p>
          <p className="mt-3 font-mono text-[10px] tracking-[0.16em] text-[#64748B]">Illustrative scenario roster — not live campus data.</p>
          <div className="mt-8 flex flex-wrap gap-2">
            {["Attendance ↓", "Performance ↓", "Engagement ↓", "Assignments ↓"].map((s) => (
              <span key={s} className="cine-chip text-[#ef4444]">
                {s}
              </span>
            ))}
          </div>
          <div className="mt-10 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {classroomStudents.map((st, i) => (
              <button
                key={st.id}
                type="button"
                data-cursor="INSPECT"
                onMouseEnter={() => setProbe(i)}
                onFocus={() => setProbe(i)}
                className={`cine-panel rounded-xl px-3 py-3 text-left ${probe === i ? "ring-1 ring-[#2563EB]" : ""}`}
              >
                <p className="font-mono text-[10px] text-[#64748B]">#{st.id}</p>
                <p
                  className="mt-1 text-[11px] font-semibold"
                  style={{
                    color: st.risk === "HIGH" ? "#ef4444" : st.risk === "ATTENTION" ? "#f59e0b" : "#22c55e",
                  }}
                >
                  {st.risk}
                </p>
              </button>
            ))}
          </div>
        </div>
        <div className="cine-span-7">
          <article className="cine-panel ml-auto max-w-md rounded-3xl p-6">
            <p className="font-mono text-[10px] tracking-[0.18em] text-[#2563EB]">Scenario #{student.id}</p>
            <h3 className="mt-2 text-xl font-semibold">Inspecting a scenario profile</h3>
            <dl className="mt-5 grid grid-cols-2 gap-4 font-mono text-[12px] text-[#475569]">
              <div>
                Attendance
                <p className="mt-1 text-[#0F172A]">{student.attendance}%</p>
              </div>
              <div>
                Academic Score
                <p className="mt-1 text-[#0F172A]">{student.academic}%</p>
              </div>
              <div>
                Engagement
                <p className="mt-1 text-[#0F172A]">{student.engagement}</p>
              </div>
              <div>
                Assignments
                <p className="mt-1 text-[#0F172A]">{student.assignments}%</p>
              </div>
            </dl>
            <p
              className="mt-5 font-mono text-[12px] tracking-[0.2em]"
              style={{ color: student.risk === "HIGH" ? "#ef4444" : student.risk === "ATTENTION" ? "#f59e0b" : "#22c55e" }}
            >
              Risk: {student.risk}
            </p>
          </article>
        </div>
      </Section>

      <Section id="how">
        <div className="cine-span-12">
          <p className="cine-kicker">How it works</p>
          <h2 className="cine-h2 mt-4">Detect → Explain → Intervene → Improve</h2>
          <div className="mt-10 grid gap-3 md:grid-cols-5">
            {pipeline.map((n) => (
              <button
                key={n.id}
                type="button"
                data-cursor="INSPECT"
                onMouseEnter={() => onHotNode(n.id)}
                onMouseLeave={() => onHotNode(-1)}
                onFocus={() => onHotNode(n.id)}
                onBlur={() => onHotNode(-1)}
                className="cine-panel rounded-2xl p-5 text-left"
              >
                <p className="font-mono text-[10px] text-[#2563EB]">{n.kicker}</p>
                <h3 className="mt-2 text-[15px] font-semibold">{n.title}</h3>
                <p className="mt-2 text-[13px] leading-6 text-[#475569]">{n.body}</p>
              </button>
            ))}
          </div>
        </div>
      </Section>

      <Section id="ai-demo">
        <div className="cine-span-12">
          <p className="cine-kicker">AI Prediction Lab</p>
          <h2 className="cine-h2 mt-3">Student-risk simulator</h2>
          <p className="cine-body mt-2">Illustrative demo. Changing conditions changes predicted risk. Nothing is written to the database.</p>
        </div>
        <div className="cine-lab-in mt-8">
          <div className="cine-panel space-y-5 rounded-3xl p-6">
            {[
              ["attendance", "Attendance", form.attendance, "%"],
              ["academic", "Academic Score", form.academic, "%"],
              ["assignments", "Assignment Completion", form.assignments, "%"],
            ].map(([k, label, val, suf]) => (
              <label key={k} className="block">
                <div className="mb-2 flex justify-between font-mono text-[11px] tracking-[0.12em] text-[#475569]">
                  <span>{label}</span>
                  <span className="text-[#0F172A]">
                    {val}
                    {suf}
                  </span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="100"
                  value={val}
                  aria-label={label}
                  onChange={(e) => setField(k, Number(e.target.value))}
                  className="cine-range"
                />
              </label>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <label className="block font-mono text-[11px] text-[#475569]">
                Learning Engagement
                <select className="cine-select" value={form.engagement} onChange={(e) => setField("engagement", e.target.value)}>
                  <option>LOW</option>
                  <option>MEDIUM</option>
                  <option>HIGH</option>
                </select>
              </label>
              <label className="block font-mono text-[11px] text-[#475569]">
                Attendance Trend
                <select className="cine-select" value={form.trend} onChange={(e) => setField("trend", e.target.value)}>
                  <option>DECLINING</option>
                  <option>STABLE</option>
                  <option>IMPROVING</option>
                </select>
              </label>
            </div>
          </div>
        </div>
        <div className="cine-lab-stage mt-8 hidden lg:block" aria-hidden />
        <div className="cine-lab-out mt-8">
          <div className="cine-panel flex flex-col items-center rounded-3xl p-8 text-center">
            <p className="cine-kicker">Illustrative demo</p>
            <div
              className="cine-ring mt-6"
              style={{
                "--p": pred.score,
                background: `radial-gradient(circle at 50% 50%, #ffffff 58%, transparent 59%), conic-gradient(from -90deg, ${ringColor} calc(${pred.score} * 1%), #e2e8f0 0)`,
              }}
            >
              <p className="font-display text-[clamp(2.8rem,6vw,4.4rem)] leading-none">{pred.score}%</p>
            </div>
            <p className="mt-5 font-mono text-[12px] tracking-[0.18em]" style={{ color: ringColor }}>
              {pred.band}
            </p>
          </div>
        </div>
      </Section>

      <Section id="explain">
        <div className="cine-span-6">
          <p className="cine-kicker">02 — Explain</p>
          <h2 className="cine-h2 mt-3">Why is this student at risk?</h2>
          <p className="cine-body mt-3">Prediction + reasoning. Focus or hover a factor to isolate its contribution.</p>
          <div className="mt-8 space-y-5">
            {pred.factors.map((f, i) => (
              <button
                key={f.key}
                type="button"
                onMouseEnter={() => highlightFactor(f.key, i)}
                onMouseLeave={clearFactor}
                onFocus={() => highlightFactor(f.key, i)}
                onBlur={clearFactor}
                className={`w-full text-left transition-opacity ${factor && factor !== f.key ? "opacity-30" : "opacity-100"}`}
              >
                <div className="mb-2 flex justify-between font-mono text-[11px] text-[#475569]">
                  <span>{f.key}</span>
                  <span className="text-[#0F172A]">{f.contribution}% contribution</span>
                </div>
                <div className="cine-factor">
                  <i style={{ width: `${f.contribution}%` }} />
                </div>
                {factor === f.key && <p className="mt-2 text-[13px] text-[#475569]">{f.detail}</p>}
              </button>
            ))}
          </div>
        </div>
      </Section>

      <Section id="intervene">
        <div className="cine-span-12">
          <p className="cine-kicker">03 — Intervene</p>
          <h2 className="cine-h2 mt-3">What can we do?</h2>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {interventions.map((it) => (
              <button
                key={it.id}
                type="button"
                data-cursor="OPEN"
                aria-expanded={open === it.id}
                onClick={() => setOpen(open === it.id ? null : it.id)}
                className="cine-panel rounded-2xl p-6 text-left transition-transform hover:-translate-y-1"
              >
                <h3 className="text-[16px] font-semibold">{it.title}</h3>
                <p className="mt-2 text-[13px] leading-6 text-[#475569]">{it.body}</p>
                {open === it.id && <p className="mt-4 font-mono text-[11px] tracking-[0.12em] text-[#2563EB]">{it.detail}</p>}
              </button>
            ))}
          </div>
          <button type="button" onClick={simulate} data-cursor="SIMULATE" className="cine-btn cine-btn-primary mt-8">
            {simulating ? "Simulating…" : "Simulate Intervention"}
          </button>
          {(simulating || pred.score < 40) && (
            <div className="mt-8">
              <p className="font-mono text-[12px] tracking-[0.16em] text-[#475569]">
                {pred.score}% {simulating ? "· trajectory in motion" : ""}
              </p>
              {pred.score < 35 && (
                <h3 className="cine-display mt-3 text-[clamp(1.8rem,4vw,3rem)]">
                  Early intervention
                  <br />
                  can change the trajectory.
                </h3>
              )}
            </div>
          )}
        </div>
      </Section>

      <Section id="impact">
        <div className="cine-span-12">
          <p className="cine-kicker">04 — Improve</p>
          <h2 className="cine-h2 mt-3">What CLASSORA actually does.</h2>
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
            {impactCapabilities.map((m) => (
              <Capability key={m.key} label={m.key} body={m.body} />
            ))}
          </div>
          <div className="mt-6 flex gap-4 font-mono text-[11px] text-[#475569]">
            <span className="text-[#22c55e]">● Stable</span>
            <span className="text-[#f59e0b]">● Needs attention</span>
            <span className="text-[#ef4444]">● High risk</span>
          </div>
        </div>
      </Section>

      <Section id="map">
        <div className="cine-span-5">
          <p className="cine-kicker">Illustrative roster</p>
          <h2 className="cine-h2 mt-3">Inspect a scenario in the network.</h2>
          <p className="cine-body mt-3">These profiles demonstrate risk bands. They are not live students.</p>
          <div className="mt-8 space-y-2">
            {networkStudents.map((s, i) => (
              <button
                key={s.id}
                type="button"
                data-cursor="VIEW"
                onMouseEnter={() => setNode(i)}
                onFocus={() => setNode(i)}
                onClick={() => setNode(i)}
                className={`cine-panel flex w-full items-center justify-between rounded-xl px-4 py-3 text-left ${node === i ? "ring-1 ring-[#2563EB]" : ""}`}
              >
                <span className="font-mono text-[12px]">#{s.id}</span>
                <span
                  className="font-mono text-[10px] tracking-[0.14em]"
                  style={{ color: s.risk === "HIGH" ? "#ef4444" : s.risk === "ATTENTION" ? "#f59e0b" : "#22c55e" }}
                >
                  {s.risk}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="cine-span-7">
          <article className="cine-panel ml-auto max-w-md rounded-3xl p-6">
            <p className="font-mono text-[10px] tracking-[0.18em] text-[#2563EB]">Scenario #{inst.id}</p>
            <dl className="mt-4 grid grid-cols-2 gap-4 font-mono text-[12px] text-[#475569]">
              <div>
                Risk
                <p className="mt-1 text-[#0F172A]">{inst.risk}</p>
              </div>
              <div>
                Attendance
                <p className="mt-1 text-[#0F172A]">{inst.attendance}%</p>
              </div>
              <div>
                Academic
                <p className="mt-1 text-[#0F172A]">{inst.academic}%</p>
              </div>
              <div>
                Status
                <p className="mt-1 text-[#0F172A]">{inst.status}</p>
              </div>
            </dl>
            <a href="#intervene" className="cine-btn cine-btn-primary mt-6 text-[12px]" data-cursor="VIEW">
              View Intervention
            </a>
          </article>
        </div>
      </Section>

      <Section id="technology">
        <div className="cine-span-12">
          <p className="cine-kicker">Technology architecture</p>
          <h2 className="cine-h2 mt-3">Student Intelligence Engine</h2>
          <p className="cine-body mt-3">Not a glowing brain — feature vectors, signals, and prediction pathways.</p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {techNodes.map((n) => (
              <article key={n.id} className="cine-panel rounded-2xl p-5">
                <p className="font-mono text-[10px] text-[#2563EB]">{n.label}</p>
                <h3 className="mt-1 text-[15px] font-semibold">{n.tech}</h3>
                <p className="mt-2 text-[13px] leading-6 text-[#475569]">{n.purpose}</p>
              </article>
            ))}
          </div>
        </div>
      </Section>

      <Section id="team">
        <div className="cine-span-12">
          <p className="cine-kicker">Team</p>
          <h2 className="cine-h2 mt-3">Built for SIH 2026.</h2>
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {team.map((m) => (
              <article key={m.name} className="cine-panel rounded-2xl p-5">
                <p className="text-[15px] font-semibold">{m.name}</p>
                <p className="font-mono text-[10px] tracking-[0.14em] text-[#2563EB]">{m.role}</p>
                <div className="mt-3 flex gap-3 text-[12px]">
                  {m.github && (
                    <a href={m.github} target="_blank" rel="noopener noreferrer" className="text-[#475569] no-underline hover:text-[#2563EB]">
                      GitHub
                    </a>
                  )}
                  {m.linkedin && (
                    <a href={m.linkedin} target="_blank" rel="noopener noreferrer" className="text-[#475569] no-underline hover:text-[#2563EB]">
                      LinkedIn
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>
        </div>
      </Section>

      <Section id="demo">
        <div className="cine-span-12">
          <div className="cine-cta">
            <p className="cine-kicker">Don't wait for dropout.</p>
            <h2 className="cine-display">
              Predict it.
              <br />
              Prevent it.
            </h2>
            <p className="cine-cta-sub">Turn early signals into early intervention.</p>
            <p className="cine-cta-line">
              Detect early. Understand deeply.
              <br />
              Intervene smarter. Change outcomes.
            </p>
            <div className="cine-cta-actions">
              <Mag href={APP_URL}>Launch CLASSORA</Mag>
              <Mag href="#ai-demo" ghost>
                Explore the AI
              </Mag>
            </div>
          </div>
        </div>
      </Section>

      <footer className="relative z-[2] pb-16 pt-4">
        <div className="cine-shell">
          <p className="cine-span-12 text-center text-[12px] text-[#64748B]">
            <strong className="tracking-[0.18em] text-[#0F172A]">CLASSORA</strong> · Intelligent Learning. Connected Classrooms. · SIH 2026
          </p>
        </div>
      </footer>
    </div>
  );
}
