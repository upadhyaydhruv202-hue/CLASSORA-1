import * as THREE from "three";

export const CAM = {
  HERO: { p: [0, 1.95, 6.2], l: [0, 1.05, 0] },
  DIGITAL_TWIN: { p: [0.06, 1.42, 3.28], l: [0, 1.08, 0] },
  AI_SCAN: { p: [0.58, 1.34, 2.42], l: [0, 1.14, 0] },
  RISK_DNA: { p: [2.08, 1.7, 2.72], l: [0, 1.08, 0] },
  RISK_UNIVERSE: { p: [0.2, 6.25, 14.8], l: [0, 0.15, 0] },
  DEPARTMENT: { p: [4.1, 3.4, 8.4], l: [3.35, 0.45, 1.05] },
  WHAT_IF: { p: [-1.92, 1.5, 3.78], l: [0.18, 1.06, 0] },
  INTERVENTION_LAB: { p: [1.28, 1.55, 3.28], l: [0, 1.08, 0] },
  COMMAND_CENTER: { p: [0, 1.88, 7.7], l: [0, 1.18, 0] },
};

export const STAGE_TRACK = [
  { id: "experience", cam: "HERO" },
  { id: "problem", cam: "DIGITAL_TWIN" },
  { id: "features", cam: "AI_SCAN" },
  { id: "how", cam: "RISK_DNA" },
  { id: "impact", cam: "RISK_UNIVERSE" },
  { id: "ai-demo", cam: "WHAT_IF" },
  { id: "proof", cam: "INTERVENTION_LAB" },
  { id: "demo", cam: "COMMAND_CENTER" },
];

export function sampleStage() {
  const vh = typeof window !== "undefined" ? window.innerHeight || 1 : 1;
  const pts = STAGE_TRACK.map((s, i) => {
    const el = typeof document !== "undefined" ? document.getElementById(s.id) : null;
    if (!el) return { i, vis: 0, local: 0, cam: s.cam };
    const r = el.getBoundingClientRect();
    const center = r.top + r.height * 0.36;
    const vis = THREE.MathUtils.clamp(1 - Math.abs(center - vh * 0.44) / (vh * 0.9), 0, 1);
    const local = THREE.MathUtils.clamp((vh * 0.58 - r.top) / Math.max(r.height, 80), 0, 1);
    return { i, vis, local, cam: s.cam };
  });
  let i = 0;
  for (let k = 1; k < pts.length; k += 1) {
    if (pts[k].vis > pts[i].vis) i = k;
  }
  const from = pts[i];
  const to = pts[Math.min(i + 1, pts.length - 1)];
  const blend = i >= pts.length - 1 ? 0 : from.local;
  return { index: i, local: from.local, from: from.cam, to: to.cam, blend };
}

export function lerpCam(fromName, toName, t) {
  const a = CAM[fromName] || CAM.HERO;
  const b = CAM[toName] || a;
  const s = t * t * (3 - 2 * t);
  return {
    p: a.p.map((v, k) => THREE.MathUtils.lerp(v, b.p[k], s)),
    l: a.l.map((v, k) => THREE.MathUtils.lerp(v, b.l[k], s)),
  };
}

export function universeAmount(from, to, blend) {
  if (from === "RISK_DNA" && to === "RISK_UNIVERSE") return blend;
  if (from === "RISK_UNIVERSE" && to === "WHAT_IF") return 1 - blend;
  if (from === "RISK_UNIVERSE") return 1;
  if (from === "DEPARTMENT") return 1;
  return 0;
}
