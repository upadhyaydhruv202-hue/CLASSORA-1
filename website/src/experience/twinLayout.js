export const TWIN_NODES = [
  { key: "attendance", factor: 0, label: "ATTENDANCE", color: "#5EEAD4", pos: [0.28, 1.82, -0.28], rot: [0, -0.12, 0] },
  { key: "engagement", factor: 3, label: "ENGAGEMENT", color: "#FBBF24", pos: [1.12, 1.4, 0.18], rot: [0, -0.42, 0] },
  { key: "academic", factor: 1, label: "ACADEMICS", color: "#34D399", pos: [1.28, 1.02, -0.16], rot: [0, -0.38, 0] },
  { key: "history", factor: 4, label: "HISTORY", color: "#A78BFA", pos: [0.82, 0.24, -0.38], rot: [0, -0.22, 0] },
  { key: "assignments", factor: 2, label: "ASSIGNMENTS", color: "#67E8F9", pos: [1.08, 0.52, 0.22], rot: [0, -0.32, 0] },
];

export function lineTerminus(pos) {
  const y = pos[1];
  if (y > 1.65) return [0.16, 1.68, -0.06];
  const low = y < 0.7;
  return [0.44, low ? 0.42 : 1.1, 0.04];
}
