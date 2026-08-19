import { useMemo } from "react";

const LABELS = ["Identity", "Attendance", "Voice", "Risk", "Support", "Human Review"];

function nodeLayout(scale) {
  const cx = 200;
  const cy = 188;
  const r = 142 * scale;
  return LABELS.map((label, i) => {
    const a = -Math.PI / 2 + (i * Math.PI) / 3;
    return {
      id: label.toLowerCase().replace(/\s+/g, "-"),
      label,
      x: cx + r * Math.cos(a),
      y: cy + r * Math.sin(a),
    };
  });
}

export default function SplashScene({ stage, reduce, compact }) {
  const scale = compact ? 0.78 : 1;
  const nodes = useMemo(() => nodeLayout(scale), [scale]);
  const dust = useMemo(() => {
    const n = reduce ? 6 : compact ? 10 : 16;
    return Array.from({ length: n }, (_, i) => ({
      id: i,
      x: 36 + ((i * 53) % 328),
      y: 28 + ((i * 79) % 328),
      delay: (i % 6) * 0.1,
    }));
  }, [reduce, compact]);

  const mesh = nodes
    .map((n, i) => {
      const next = nodes[(i + 1) % nodes.length];
      return `M${n.x} ${n.y} L${next.x} ${next.y}`;
    })
    .join(" ");

  const cls = [
    "splash-network origin-center",
    stage >= 1 ? "splash-on" : "",
    stage >= 2 || reduce ? "splash-forming" : "",
    stage >= 3 || reduce ? "splash-live" : "",
    stage >= 5 ? "splash-exit" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <svg
      viewBox="-28 -18 456 424"
      className="mx-auto h-auto w-full max-w-[min(420px,86vw)] overflow-visible"
      role="img"
      aria-label="Classora intelligence network initializing"
    >
      <g className={cls}>
        {dust.map((p) => (
          <circle
            key={p.id}
            cx={p.x}
            cy={p.y}
            r="1.25"
            fill="#60A5FA"
            className="splash-dust"
            style={{ animationDelay: `${p.delay}s` }}
          />
        ))}

        <path
          d={mesh}
          className="splash-mesh"
          stroke="#93C5FD"
          strokeWidth="0.7"
          pathLength="100"
        />

        {nodes.map((n, i) => (
          <line
            key={`link-${n.id}`}
            x1="200"
            y1="188"
            x2={n.x}
            y2={n.y}
            stroke="#2563EB"
            strokeWidth="1.1"
            strokeLinecap="round"
            pathLength="100"
            className="splash-link"
            style={{ animationDelay: `${0.08 + i * 0.12}s` }}
          />
        ))}

        {nodes.map((n, i) => (
          <g key={n.id} className="splash-node" style={{ animationDelay: `${0.16 + i * 0.14}s` }}>
            <circle cx={n.x} cy={n.y} r="15" fill="rgba(11,31,74,0.06)" stroke="#0B1F4A" strokeWidth="1.15" />
            <circle cx={n.x} cy={n.y} r="3.4" fill="#22D3EE" />
            <text
              x={n.x}
              y={n.y + 28}
              textAnchor="middle"
              fill="#0B1F4A"
              fontSize={compact ? "8" : "9"}
              fontFamily="Plus Jakarta Sans, sans-serif"
              fontWeight="600"
            >
              {n.label}
            </text>
          </g>
        ))}

        <g className="splash-hub">
          <circle className="splash-wave" cx="200" cy="188" r="34" fill="none" stroke="#2563EB" strokeWidth="0.8" />
          <circle cx="200" cy="188" r="34" fill="rgba(246,248,252,0.2)" stroke="#2563EB" strokeWidth="1.25" />
          <circle
            cx="200"
            cy="188"
            r="27"
            fill="none"
            stroke="#22D3EE"
            strokeWidth="0.75"
            className="splash-hub-ring"
          />
          <text
            x="200"
            y="184"
            textAnchor="middle"
            fill="#0B1F4A"
            fontSize="11"
            fontWeight="800"
            fontFamily="Plus Jakarta Sans, sans-serif"
            letterSpacing="0.14em"
          >
            CLASSORA
          </text>
          <text
            x="200"
            y="198"
            textAnchor="middle"
            fill="#5b6b82"
            fontSize="7"
            fontWeight="700"
            fontFamily="Plus Jakarta Sans, sans-serif"
            letterSpacing="0.18em"
          >
            SIH 2026
          </text>
        </g>
      </g>
    </svg>
  );
}
