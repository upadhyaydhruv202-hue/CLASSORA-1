import { useMemo, useState } from "react";

export function ClassoraMark({ size = 48 }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="coG" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563EB" />
          <stop offset="1" stopColor="#1D4ED8" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#coG)" fillOpacity="0.12" stroke="url(#coG)" strokeWidth="1.5" />
      <path d="M44.5 20.5C41.2 16.8 36.4 14.5 31 14.5C21.3 14.5 13.5 22.3 13.5 32C13.5 41.7 21.3 49.5 31 49.5C36.4 49.5 41.2 47.2 44.5 43.5" stroke="url(#coG)" strokeWidth="4.2" strokeLinecap="round" />
      <circle cx="45.5" cy="20.5" r="3.2" fill="#2563EB" />
      <circle cx="45.5" cy="43.5" r="3.2" fill="#1D4ED8" />
      <circle cx="31" cy="32" r="3.6" fill="#2563EB" />
      <path d="M42.5 22.5L33.5 30.2" stroke="#93C5FD" strokeWidth="1.4" strokeLinecap="round" opacity="0.9" />
      <path d="M42.5 41.5L33.5 33.8" stroke="#93C5FD" strokeWidth="1.4" strokeLinecap="round" opacity="0.9" />
    </svg>
  );
}

export function HomeHeader() {
  return (
    <div className="mb-8 flex flex-col items-center text-center">
      <ClassoraMark size={88} />
      <div className="co-tagline mt-3.5">Intelligent Learning · Connected Classrooms</div>
      <h1 className="co-hero-title">CLASSORA</h1>
      <p className="co-hero-sub">
        Classora brings students, faculty, and classrooms into one connected digital environment — AI attendance that feels production-ready.
      </p>
    </div>
  );
}

export function DashHeader() {
  return (
    <a href="/" className="flex items-center gap-3 no-underline text-inherit">
      <ClassoraMark size={48} />
      <div>
        <div className="text-[22px] font-extrabold leading-tight tracking-[-0.03em] text-[#0F172A]">CLASSORA</div>
        <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[#64748B]">Learn. Connect. Evolve.</div>
      </div>
    </a>
  );
}

export function HomeFooter() {
  return (
    <div className="co-footer">
      <strong>CLASSORA</strong> · Intelligent Learning. Connected Classrooms.
      <br />
      Learn. Connect. Evolve.
    </div>
  );
}

export function DashFooter() {
  return (
    <div className="co-footer">
      <strong>CLASSORA</strong> · Secure AI attendance for connected classrooms
    </div>
  );
}

export function WelcomeBanner({ name, subtitle = "Here’s what’s happening in your learning environment today." }) {
  return (
    <div className="co-welcome-card">
      <p className="co-section-kicker">Welcome</p>
      <h3 className="co-welcome">{name}</h3>
      <p className="co-welcome-sub">{subtitle}</p>
    </div>
  );
}

export function SubjectCard({ name, code, section, stats = [], children }) {
  return (
    <div className="co-subject">
      <h3>{name}</h3>
      <p className="mb-3 text-sm text-[#64748B]">
        Code: <span className="co-code">{code}</span> · Section: <span className="font-semibold text-[#0F172A]">{section}</span>
      </p>
      <div>
        {stats.map(([icon, label, value]) => (
          <span key={label} className="co-chip">
            {icon} <strong className="text-[#0F172A]">{value}</strong> {label}
          </span>
        ))}
      </div>
      {children}
    </div>
  );
}

export function Field({ label, as, children, ...props }) {
  const Tag = as || "input";
  return (
    <label className="co-field">
      {label && <span>{label}</span>}
      {children || <Tag {...props} />}
    </label>
  );
}

export function Notice({ title, body, tone = "info" }) {
  return (
    <div className={`co-notice co-notice-${tone}`}>
      {title && <strong>{title}</strong>}
      {body && <p>{body}</p>}
    </div>
  );
}

export function EmptyState({ title, body }) {
  return (
    <div className="co-empty">
      <h4>{title}</h4>
      {body && <p>{body}</p>}
    </div>
  );
}

export function Badge({ children, kind = "muted" }) {
  return <span className={`co-badge co-badge-${kind}`}>{children}</span>;
}

export function Chips({ items }) {
  return (
    <div className="co-chips" style={{ gridTemplateColumns: `repeat(${Math.min(items.length || 1, 4)}, minmax(0, 1fr))` }}>
      {items.map((item) => (
        <div key={item.label}>
          <em>{item.label}</em>
          <strong>{item.value ?? "—"}</strong>
        </div>
      ))}
    </div>
  );
}

export function DriverBars({ drivers = [], empty = "No concentrated driver in the available records." }) {
  const rows = (drivers || []).filter((d) => Number(d?.percent || d?.share || 0) > 0);
  if (!rows.length) {
    return <EmptyState title="No risk history available yet." body={empty} />;
  }
  return (
    <div className="co-drivers">
      <p className="co-section-kicker">Why is the risk at this level?</p>
      {rows.map((d, i) => {
        const pct = Math.max(0, Math.min(100, Number(d.percent || d.share || 0)));
        return (
          <div key={d.name || i} className="co-driver mb-3 last:mb-0">
            <div className="co-driver-label">
              <span>{d.name || d.label}</span>
              <strong>{Math.round(pct)}%</strong>
            </div>
            <div className="co-driver-track"><i style={{ width: `${pct}%` }} /></div>
          </div>
        );
      })}
    </div>
  );
}

export function ShareBarChart({ items = [] }) {
  const rows = (items || []).filter((d) => d?.name && Number(d.percent || d.share || 0) > 0);
  if (!rows.length) return null;
  const max = Math.max(1, ...rows.map((d) => Number(d.percent || d.share || 0)));
  const w = 640;
  const h = 220;
  const pad = { t: 28, r: 12, b: 52, l: 12 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const gap = 14;
  const barW = Math.max(18, (innerW - gap * Math.max(rows.length - 1, 0)) / rows.length);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="co-chart" role="img" aria-label="Driver share chart">
      {rows.map((d, i) => {
        const pct = Number(d.percent || d.share || 0);
        const bh = Math.max(4, (pct / max) * innerH);
        const x = pad.l + i * (barW + gap);
        const y = pad.t + innerH - bh;
        const words = String(d.name).split(" ");
        return (
          <g key={d.name || i}>
            <rect x={x} y={y} width={barW} height={bh} rx="8" fill="#2563EB" />
            <text x={x + barW / 2} y={y - 8} textAnchor="middle" fontSize="11" fontWeight="700" fill="#0F172A">{Math.round(pct)}%</text>
            <text x={x + barW / 2} y={h - 28} textAnchor="middle" fontSize="10" fill="#64748B">{words[0]}</text>
            {words[1] ? <text x={x + barW / 2} y={h - 14} textAnchor="middle" fontSize="10" fill="#64748B">{words.slice(1).join(" ")}</text> : null}
          </g>
        );
      })}
    </svg>
  );
}

export function ScoreLineChart({ points = [] }) {
  const pts = (points || []).filter((p) => p && p.score != null);
  if (pts.length < 2) return null;
  const w = 640;
  const h = 240;
  const pad = { t: 24, r: 24, b: 40, l: 44 };
  const xs = pts.map((p) => Number(p.days ?? 0));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = 0;
  const maxY = 100;
  const sx = (x) => pad.l + ((x - minX) / Math.max(1, maxX - minX)) * (w - pad.l - pad.r);
  const sy = (y) => pad.t + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - pad.t - pad.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(Number(p.days ?? 0))},${sy(Number(p.score))}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="co-chart" role="img" aria-label="Risk score trajectory">
      {[0, 25, 50, 75, 100].map((tick) => (
        <g key={tick}>
          <line x1={pad.l} y1={sy(tick)} x2={w - pad.r} y2={sy(tick)} stroke="#E2E8F0" />
          <text x={pad.l - 8} y={sy(tick) + 4} textAnchor="end" fontSize="10" fill="#64748B">{tick}</text>
        </g>
      ))}
      <path d={d} fill="none" stroke="#2563EB" strokeWidth="2.6" strokeLinejoin="round" />
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={sx(Number(p.days ?? 0))} cy={sy(Number(p.score))} r="4.5" fill="#2563EB" />
          <text x={sx(Number(p.days ?? 0))} y={h - 14} textAnchor="middle" fontSize="10" fill="#64748B">{p.days ?? 0}d</text>
        </g>
      ))}
    </svg>
  );
}

export function RecoveryCompare({ current, estimated }) {
  if (current == null && estimated == null) return null;
  return (
    <div className="co-recover">
      <div>
        <p className="co-caption">Current risk</p>
        <strong>{current == null ? "—" : `${current}%`}</strong>
      </div>
      <span aria-hidden="true">↓</span>
      <div>
        <p className="co-caption">With recommended actions</p>
        <strong className="is-better">{estimated == null ? "—" : `${estimated}%`}</strong>
      </div>
    </div>
  );
}

export function ActionItems({ items = [], title = "What can you do?" }) {
  const rows = (items || []).map((item) => (typeof item === "string" ? item : item?.name || item?.title || item?.text)).filter(Boolean);
  if (!rows.length) return null;
  return (
    <div className="co-actions">
      <p className="co-section-kicker">{title}</p>
      <ul>{rows.map((item, i) => <li key={i}>{item}</li>)}</ul>
    </div>
  );
}

export function NumberedWhy({ title, lines = [] }) {
  const rows = (lines || []).map((line) => (typeof line === "string" ? line : line?.label || line?.text)).filter(Boolean);
  if (!rows.length) return <EmptyState title="No explanation yet." body="Explanations appear after attendance or academic records exist." />;
  return (
    <div>
      {title && <h4 className="mb-3 font-semibold">{title}</h4>}
      <ol className="co-why">
        {rows.map((line, i) => <li key={i}>{line}</li>)}
      </ol>
    </div>
  );
}

export function TimelineList({ events = [] }) {
  const rows = events || [];
  if (!rows.length) return <EmptyState title="No timeline events yet." />;
  return (
    <ol className="co-timeline">
      {rows.map((event, i) => (
        <li key={i}>
          <em>{event.when || event.When || "Update"}</em>
          <span>{event.text || event.Event || event.title || ""}</span>
        </li>
      ))}
    </ol>
  );
}

export function NotifyCard({ title, body, when }) {
  const blob = `${title || ""} ${body || ""}`.toLowerCase();
  let tone = "muted";
  let kicker = "Notification";
  if (/(recover|improv|progress)/.test(blob)) { tone = "ok"; kicker = "Recovery Progress"; }
  else if (/(privacy|identity|anonymous|hidden)/.test(blob)) { tone = "info"; kicker = "Privacy"; }
  else if (/(mentor|counsel)/.test(blob)) { tone = "info"; kicker = "Mentorship"; }
  else if (/(risk|dropout|critical|watch)/.test(blob)) { tone = "info"; kicker = "Risk Update"; }
  return (
    <article className={`co-note co-note-${tone}`}>
      <p className="co-section-kicker">{kicker} {when ? <span>{when}</span> : null}</p>
      <strong>{title || "Update"}</strong>
      {body ? <p>{body}</p> : null}
    </article>
  );
}

export function StretchNav({ items, value, onChange, className = "" }) {
  return (
    <nav className={`co-nav ${items.length > 5 ? "co-nav-6" : items.length > 4 ? "co-nav-5" : "co-nav-4"} ${className}`}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`co-btn ${value === item.id ? "is-on" : "co-btn-tertiary"}`}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}

function ringColor(level) {
  if (level === "HIGH") return "#DC2626";
  if (level === "MODERATE") return "#D97706";
  if (level === "LOW") return "#16A34A";
  return "#64748B";
}

export function RiskWidget({ payload, onGoto }) {
  const [open, setOpen] = useState(false);
  const data = payload || {};
  const last = data.lastKnown || {};
  const available = data.available;
  const score = available ? data.riskScore : last.riskScore;
  const level = available ? data.riskLevel : last.riskLevel;
  const label = data.riskLevelLabel || (available ? "—" : "Unable to update");
  const display = score == null ? "—" : `${Math.round(Number(score))}%`;
  const circ = 2 * Math.PI * 42;
  const offset = circ * (1 - Math.max(0, Math.min(100, Number(score || 0))) / 100);
  const stroke = ringColor(level);
  const drivers = data.drivers || last.drivers || [];
  const recs = data.recommendations || last.recommendations || [];

  const trend = useMemo(() => {
    if (data.weekChange != null) {
      const week = data.weekChange;
      const arrow = week > 0 ? "↑" : week < 0 ? "↓" : "→";
      return `${arrow} ${Math.abs(week)}% vs last stored week`;
    }
    return data.updatedLabel || (available ? "Updated just now" : "Unable to update");
  }, [data, available]);

  return (
    <aside className="co-risk-float" aria-label="Dropout risk score">
      <div className="co-card flex gap-3.5">
        <div className="relative h-[88px] w-[88px] shrink-0">
          <svg width="88" height="88" viewBox="0 0 112 112" className="-rotate-90">
            <circle cx="56" cy="56" r="42" fill="none" stroke="#E2E8F0" strokeWidth="8" />
            <circle cx="56" cy="56" r="42" fill="none" stroke={stroke} strokeWidth="8" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset} />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center text-xl font-extrabold tracking-[-0.04em]">{display}</div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold tracking-[0.12em] text-[#64748B]">DROPOUT RISK SCORE</p>
          <p className="mt-1.5 text-[11px] font-extrabold tracking-[0.08em]" style={{ color: stroke }}>{label}</p>
          <p className="mt-1.5 text-[10px] text-[#64748B]">{trend}</p>
          <button type="button" className="mt-2 text-[11px] font-semibold text-[#2563EB]" onClick={() => setOpen((v) => !v)}>
            {open ? "Hide analysis" : "View analysis →"}
          </button>
          {open && (
            <div className="mt-2 text-[11px] leading-relaxed text-[#475569]">
              <p className="mb-1 text-[10px] font-bold tracking-[0.08em] text-[#64748B]">MAIN RISK DRIVERS</p>
              <ul className="mb-2 list-disc pl-4">
                {drivers.filter((d) => d.percent).slice(0, 4).map((d) => <li key={d.name}>{d.name} · {d.percent}%</li>)}
                {!drivers.length && <li>No concentrated driver in the available records.</li>}
              </ul>
              <div className="flex flex-col gap-1.5">
                <button type="button" className="co-btn co-btn-secondary min-h-11 text-[11px]" onClick={() => onGoto?.("explain")}>View detailed analysis</button>
                <button type="button" className="co-btn co-btn-secondary min-h-11 text-[11px]" onClick={() => onGoto?.("recovery")}>See recovery plan</button>
                <button type="button" className="co-btn co-btn-secondary min-h-11 text-[11px]" onClick={() => onGoto?.("twin")}>View Digital Twin</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
