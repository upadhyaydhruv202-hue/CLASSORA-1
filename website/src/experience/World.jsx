import { useMemo, useRef } from "react";
import { ContactShadows, Environment, Grid, Sparkles } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import * as THREE from "three";
import { classroomStudents, networkStudents, pipeline, interventions } from "../content";
import Student from "./Student";
import RiskDNA from "./RiskDNA";
import RiskUniverse from "./RiskUniverse";
import HoloHUD from "./HoloHUD";
import Chamber from "./Chamber";
import WhyGraph from "./WhyGraph";

const RING_Y = 1.55;
const RING_Z = -48;
const RING_R = 1.05;

const CAM = [
  { t: 0, p: [0.08, 1.06, 4.45], l: [1.72, 0.78, 0.08] },
  { t: 0.14, p: [0.35, 1.92, -4.4], l: [0, 0.82, -9.2] },
  { t: 0.28, p: [0.05, 1.58, -13.4], l: [0, 1.22, -18.2] },
  { t: 0.42, p: [2.55, 1.72, -22.6], l: [0, 1.22, -27.2] },
  { t: 0.56, p: [0.12, 9.4, -28.5], l: [0, 0.15, -38] },
  { t: 0.7, p: [0, RING_Y, RING_Z + 5.6], l: [0, RING_Y, RING_Z] },
  { t: 1, p: [0, RING_Y, RING_Z + 5.6], l: [0, RING_Y, RING_Z] },
];

function cineEase(t) {
  const x = THREE.MathUtils.clamp(t, 0, 1);
  const x1 = 0.22;
  const y1 = 1;
  const x2 = 0.36;
  const y2 = 1;
  let u = x;
  for (let i = 0; i < 6; i += 1) {
    const cx = 3 * x1;
    const bx = 3 * (x2 - x1) - cx;
    const ax = 1 - cx - bx;
    const qx = ((ax * u + bx) * u + cx) * u - x;
    const dqx = (3 * ax * u + 2 * bx) * u + cx;
    u -= qx / Math.max(dqx, 1e-6);
  }
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;
  return ((ay * u + by) * u + cy) * u;
}

function ringCameraDistance(camera) {
  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const spanY = 2 * Math.tan(vFov / 2);
  const spanX = spanY * Math.max(camera.aspect, 0.01);
  const minSpan = Math.min(spanX, spanY);
  const screenFrac = camera.aspect < 1 ? 0.78 : 0.5;
  return (2 * RING_R) / (screenFrac * minSpan);
}

function labAmount() {
  const el = typeof document !== "undefined" ? document.getElementById("ai-demo") : null;
  if (!el) return 0;
  const vh = typeof window !== "undefined" ? window.innerHeight || 1 : 1;
  const r = el.getBoundingClientRect();
  if (r.bottom < vh * 0.1 || r.top > vh * 0.9) return 0;
  const overlap = Math.min(r.bottom, vh * 0.94) - Math.max(r.top, vh * 0.06);
  return THREE.MathUtils.smoothstep(overlap / vh, 0.12, 0.4);
}

const LAB_CAM = { p: [1.38, 1.08, 4.15], l: [1.38, 0.8, 0.08] };

function portalStage(scroll) {
  const demo = typeof document !== "undefined" ? document.getElementById("demo") : null;
  const footer = typeof document !== "undefined" ? document.querySelector(".cine-footer") : null;
  const vh = typeof window !== "undefined" ? window.innerHeight || 1 : 1;

  let arrive = THREE.MathUtils.smoothstep(scroll, 0.62, 0.76);
  let leave = THREE.MathUtils.smoothstep(scroll, 0.9, 0.995);

  if (demo) {
    const rect = demo.getBoundingClientRect();
    const center = rect.top + rect.height / 2;
    const fromMid = (center - vh * 0.5) / vh;
    arrive = 1 - THREE.MathUtils.clamp((fromMid - 0.04) / 0.58, 0, 1);
    leave = THREE.MathUtils.clamp((-fromMid - 0.05) / 0.4, 0, 1);
  }
  if (footer) {
    const top = footer.getBoundingClientRect().top;
    const footerIn = THREE.MathUtils.smoothstep(vh - top, vh * 0.04, vh * 0.42);
    leave = Math.max(leave, footerIn);
  }

  return { arrive, leave };
}

function lerpCam(t) {
  const x = THREE.MathUtils.clamp(t, 0, 1);
  let i = 0;
  while (i < CAM.length - 1 && CAM[i + 1].t < x) i += 1;
  const a = CAM[i];
  const b = CAM[Math.min(i + 1, CAM.length - 1)];
  const u = (x - a.t) / Math.max(b.t - a.t, 0.0001);
  const s = u * u * (3 - 2 * u);
  return {
    p: a.p.map((v, k) => THREE.MathUtils.lerp(v, b.p[k], s)),
    l: a.l.map((v, k) => THREE.MathUtils.lerp(v, b.l[k], s)),
  };
}

const RISK = {
  high: "#ef4444",
  mid: "#f59e0b",
  low: "#22c55e",
};

function setCursor(engine, label) {
  engine.current.cursor = label;
}

function HeroHud({ engine, children }) {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    const lab = engine.current.lab || 0;
    const s = engine.current.scroll || 0;
    ref.current.visible = lab < 0.32 && s < 0.14;
  });
  return <group ref={ref}>{children}</group>;
}

function LaterScene({ engine, children }) {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    const s = engine.current.scroll || 0;
    const lab = engine.current.lab || 0;
    ref.current.visible = s > 0.1 && lab < 0.28;
  });
  return <group ref={ref}>{children}</group>;
}

function MiniStudent({ student, hot }) {
  const orb = useRef();
  const glow = useRef();
  const rings = useRef([]);
  const risk =
    student.risk === "HIGH" ? RISK.high : student.risk === "ATTENTION" ? RISK.mid : student.risk === "STABLE" ? RISK.low : "#22d3ee";
  const metal = {
    color: "#0B1018",
    metalness: 0.92,
    roughness: 0.16,
    clearcoat: 0.55,
    clearcoatRoughness: 0.22,
    envMapIntensity: 1.4,
  };

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const pulse = 1 + Math.sin(t * 2.4 + student.id) * 0.1;
    const boost = hot ? 1.28 : 1;
    if (orb.current) orb.current.scale.setScalar(pulse * boost);
    if (glow.current) {
      glow.current.scale.setScalar(2.15 * pulse * boost);
      glow.current.material.opacity = 0.16 + (hot ? 0.1 : 0) + Math.sin(t * 2.4) * 0.04;
    }
    rings.current.forEach((mesh, i) => {
      if (!mesh?.material) return;
      mesh.rotation.z = t * (0.12 + i * 0.05);
      mesh.material.opacity = 0.28 + Math.sin(t * 1.7 + i) * 0.1 + (hot ? 0.12 : 0);
    });
  });

  return (
    <group>
      {[0.2, 0.32, 0.46].map((r, i) => (
        <mesh
          key={r}
          ref={(el) => {
            rings.current[i] = el;
          }}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, 0.008 + i * 0.003, 0]}
        >
          <torusGeometry args={[r, 0.007, 8, 48]} />
          <meshBasicMaterial color={risk} transparent opacity={0.4} depthWrite={false} />
        </mesh>
      ))}
      {Array.from({ length: 8 }, (_, i) => {
        const a = (i / 8) * Math.PI * 2;
        return (
          <mesh key={a} position={[Math.cos(a) * 0.39, 0.012, Math.sin(a) * 0.39]} rotation={[0, -a, 0]}>
            <boxGeometry args={[0.07, 0.004, 0.008]} />
            <meshBasicMaterial color={risk} transparent opacity={0.45} />
          </mesh>
        );
      })}
      <mesh position={[0, 0.3, 0]} castShadow>
        <capsuleGeometry args={[0.105, 0.34, 10, 20]} />
        <meshPhysicalMaterial {...metal} />
      </mesh>
      <mesh position={[0, 0.62, 0]} castShadow>
        <sphereGeometry args={[0.112, 28, 28]} />
        <meshPhysicalMaterial {...metal} />
      </mesh>
      <mesh ref={orb} position={[0, 0.86, 0]}>
        <sphereGeometry args={[0.038, 16, 16]} />
        <meshBasicMaterial color={risk} />
      </mesh>
      <mesh ref={glow} position={[0, 0.86, 0]}>
        <sphereGeometry args={[0.038, 12, 12]} />
        <meshBasicMaterial color={risk} transparent opacity={0.18} depthWrite={false} />
      </mesh>
      <pointLight color={risk} intensity={hot ? 1.15 : 0.7} distance={2.1} position={[0, 0.86, 0]} />
    </group>
  );
}

function Dust({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const count = engine.current.mobile ? 28 : 64;
  const seeds = useMemo(() => {
    const s = [];
    for (let i = 0; i < count; i++) {
      s.push({
        a: Math.random() * Math.PI * 2,
        r: 1.2 + Math.random() * 6.4,
        z: -2.8 - Math.random() * 48,
        y: (Math.random() - 0.25) * 4.6,
        s: 0.55 + Math.random() * 1.5,
      });
    }
    return s;
  }, [count]);

  useFrame((state) => {
    if (!mesh.current) return;
    const t = state.clock.elapsedTime;
    const mx = engine.current.mouse.x;
    const my = engine.current.mouse.y;
    const click = Math.max(0, 1 - (t - engine.current.click) * 1.55);
    const risk = engine.current.risk / 100;
    const sim = engine.current.sim;
    const scatter = THREE.MathUtils.lerp(0.35 + risk * 0.9, 0.12, sim);
    seeds.forEach((p, i) => {
      const spin = t * 0.045 * p.s + p.a;
      let x = Math.cos(spin) * (p.r + scatter);
      let z = p.z + Math.sin(spin) * 0.35;
      let y = p.y + Math.sin(t * 0.38 + p.a) * 0.12;
      const dx = x - mx * 2.4;
      const dy = y - (1.1 + my);
      const d = Math.hypot(dx, dy) || 1;
      if (d < 1.6) {
        x -= (dx / d) * 0.12;
        y -= (dy / d) * 0.08;
      }
      if (click > 0) {
        const n = Math.hypot(x, y, z) || 1;
        x += (x / n) * click * 0.42;
        y += (y / n) * click * 0.22;
      }
      dummy.position.set(x, y, z);
      dummy.scale.setScalar(sim > 0.5 ? 0.82 : 1);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <sphereGeometry args={[0.012, 6, 6]} />
      <meshBasicMaterial color="#67E8F9" transparent opacity={0.12} depthWrite={false} />
    </instancedMesh>
  );
}

function Classroom({ engine }) {
  const spots = useMemo(
    () =>
      classroomStudents.map((student, i) => ({
        x: -2.1 + i * 1.05,
        z: i % 2 === 0 ? -0.25 : -1.2,
        student,
      })),
    [],
  );
  const refs = useRef([]);

  useFrame((state) => {
    refs.current.forEach((c, i) => {
      if (!c) return;
      const hot = engine.current.hoverStudent === i;
      c.position.y = hot ? 0.1 + Math.sin(state.clock.elapsedTime * 2) * 0.016 : 0;
    });
  });

  return (
    <group position={[0, 0, -9.2]}>
      {spots.map((p, i) => (
        <group
          key={p.student.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          position={[p.x, 0, p.z]}
        >
          <MiniStudent student={p.student} hot={engine.current.hoverStudent === i} />
        </group>
      ))}
      {classroomStudents.map((s, i) => {
        const h = Math.max(0.12, (s.academic / 100) * 0.9);
        return (
          <mesh key={`bar-${s.id}`} position={[2.55 + (i % 3) * 0.2, h / 2, -1.35 + Math.floor(i / 3) * 0.22]}>
            <boxGeometry args={[0.12, h, 0.12]} />
            <meshBasicMaterial color="#22D3EE" transparent opacity={0.38} />
          </mesh>
        );
      })}
      <mesh position={[-3.05, 0.55, -1.6]} rotation={[0.45, 0.6, 0.2]}>
        <octahedronGeometry args={[0.16, 0]} />
        <meshBasicMaterial color="#3B82F6" transparent opacity={0.4} wireframe />
      </mesh>
      <mesh position={[3.15, 0.72, -0.4]} rotation={[0.3, -0.4, 0.15]}>
        <boxGeometry args={[0.2, 0.2, 0.2]} />
        <meshBasicMaterial color="#67E8F9" transparent opacity={0.28} wireframe />
      </mesh>
    </group>
  );
}

function PipelineNodes({ engine }) {
  const refs = useRef([]);
  useFrame((state) => {
    refs.current.forEach((m, i) => {
      if (!m) return;
      const hot = engine.current.hotNode === i;
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.1 + i) * 0.04;
      m.scale.setScalar((hot ? 1.45 : 1) * pulse);
      m.material.emissiveIntensity = hot ? 1.15 : 0.38;
    });
  });
  return (
    <group position={[0, 1.28, -18.2]}>
      <mesh rotation={[0, 0, Math.PI / 2]} position={[0, -0.02, 0]}>
        <cylinderGeometry args={[0.012, 0.012, 4.7, 10]} />
        <meshBasicMaterial color="#22D3EE" transparent opacity={0.32} />
      </mesh>
      {pipeline.map((n, i) => (
        <group key={n.id} position={[(i - 2) * 1.15, 0, 0]}>
          <mesh
            ref={(el) => {
              refs.current[i] = el;
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              engine.current.hotNode = i;
              setCursor(engine, "INSPECT");
            }}
            onPointerOut={() => {
              engine.current.hotNode = -1;
              setCursor(engine, "");
            }}
            onClick={(e) => {
              e.stopPropagation();
              engine.current.hotNode = i;
            }}
          >
            <octahedronGeometry args={[0.22, 0]} />
            <meshStandardMaterial color="#2563EB" emissive="#1D4ED8" emissiveIntensity={0.32} roughness={0.22} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function MetricBars({ engine }) {
  const bars = useRef([]);
  useFrame(() => {
    const m = engine.current.metrics || { attendance: 62, academic: 54, assignments: 48 };
    const vals = [m.attendance, m.academic, m.assignments];
    bars.current.forEach((mesh, i) => {
      if (!mesh) return;
      const h = 0.18 + (vals[i] / 100) * 1.35;
      mesh.scale.y = THREE.MathUtils.lerp(mesh.scale.y || h, h, 0.12);
      mesh.position.y = mesh.scale.y / 2;
    });
  });
  const colors = ["#2563EB", "#4F46E5", "#0EA5E9"];
  return (
    <group position={[2.15, 0.12, -27.05]}>
      {colors.map((c, i) => (
        <mesh
          key={c}
          ref={(el) => {
            bars.current[i] = el;
          }}
          position={[(i - 1) * 0.28, 0.4, 0]}
          castShadow
        >
          <boxGeometry args={[0.16, 1, 0.16]} />
          <meshPhysicalMaterial color={c} roughness={0.28} metalness={0.12} transparent opacity={0.88} />
        </mesh>
      ))}
    </group>
  );
}

function EngineLattice({ engine }) {
  const group = useRef();
  const count = engine.current.mobile ? 32 : 56;
  const pts = useMemo(() => {
    const a = [];
    for (let i = 0; i < count; i++) {
      const u = (i / count) * Math.PI * 2;
      const v = (i % 7) / 7;
      a.push([Math.cos(u) * (0.85 + v * 0.55), (v - 0.5) * 1.35, Math.sin(u) * (0.85 + v * 0.55)]);
    }
    return a;
  }, [count]);
  const geom = useMemo(() => {
    const pos = [];
    pts.forEach((p, i) => {
      const q = pts[(i + 3) % pts.length];
      pos.push(...p, ...q);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    return g;
  }, [pts]);

  useFrame((state) => {
    if (!group.current) return;
    group.current.rotation.y = engine.current.reduce ? 0 : state.clock.elapsedTime * 0.14;
  });

  return (
    <group ref={group} position={[0, 1.3, -27.2]} scale={1.25}>
      {pts.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.032, 8, 8]} />
          <meshBasicMaterial color="#1D4ED8" />
        </mesh>
      ))}
      <lineSegments geometry={geom}>
        <lineBasicMaterial color="#2563EB" transparent opacity={0.28} />
      </lineSegments>
    </group>
  );
}

function InterventionOrbit({ engine }) {
  const group = useRef();
  const refs = useRef([]);
  useFrame((state) => {
    if (!group.current) return;
    const t = state.clock.elapsedTime;
    const open = engine.current.openIntervention;
    const show = open ? 0.7 : 0;
    group.current.visible = Boolean(open);
    group.current.rotation.y = engine.current.reduce ? 0 : t * 0.12;
    refs.current.forEach((m, i) => {
      if (!m) return;
      const id = interventions[i]?.id;
      const hot = open === id;
      m.scale.setScalar((hot ? 1.45 : 0.85) * (0.7 + show * 0.5));
      if (m.material) m.material.opacity = 0.25 + show * 0.55 + (hot ? 0.2 : 0);
    });
  });
  return (
    <group ref={group} position={[1.38, 1.15, 0.08]} scale={1.16} visible={false}>
      {interventions.map((it, i) => {
        const a = (i / interventions.length) * Math.PI * 2;
        return (
          <mesh
            key={it.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            position={[Math.cos(a) * 1.35, Math.sin(i) * 0.08, Math.sin(a) * 1.35]}
          >
            <octahedronGeometry args={[0.055, 0]} />
            <meshStandardMaterial color="#4F46E5" emissive="#4F46E5" emissiveIntensity={0.4} transparent opacity={0.5} />
          </mesh>
        );
      })}
    </group>
  );
}

function Atmosphere({ engine }) {
  const { scene } = useThree();
  const current = useMemo(() => new THREE.Color("#050814"), []);
  const target = useMemo(() => new THREE.Color("#050814"), []);
  useFrame(() => {
    const risk = (engine.current.risk || 0) / 100;
    const sim = engine.current.sim || 0;
    const analyze = engine.current.analyze || 0;
    if (sim > 0.45) target.set("#06140F");
    else if (analyze > 0.08) target.set("#061018");
    else if (risk > 0.7) target.set("#14080C");
    else if (risk > 0.45) target.set("#120E08");
    else target.set("#050814");
    current.lerp(target, 0.045);
    if (scene.background?.isColor) scene.background.copy(current);
    else scene.background = current.clone();
    if (scene.fog) scene.fog.color.copy(current);
  });
  return null;
}

function Institution({ engine }) {
  const nodes = useMemo(
    () =>
      networkStudents.map((student, i) => {
        const a = (i / networkStudents.length) * Math.PI * 2 - Math.PI / 2;
        const r = 2.35;
        return {
          student,
          x: Math.cos(a) * r,
          z: Math.sin(a) * r * 0.88,
          y: 0.28 + (i % 3) * 0.18,
          color: student.risk === "HIGH" ? RISK.high : student.risk === "ATTENTION" ? RISK.mid : RISK.low,
        };
      }),
    [],
  );
  const refs = useRef([]);
  useFrame((state) => {
    refs.current.forEach((g, i) => {
      if (!g) return;
      const hot = engine.current.instHover === i;
      g.position.y = nodes[i].y + (hot ? 0.16 : 0) + Math.sin(state.clock.elapsedTime * 1.2 + i) * 0.03;
      g.scale.setScalar(hot ? 1.22 : 1);
    });
  });
  return (
    <group position={[0, 0.2, -38]}>
      {nodes.map((n, i) => (
        <group
          key={n.student.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          position={[n.x, n.y, n.z]}
        >
          <mesh castShadow>
            <sphereGeometry args={[0.11, 16, 16]} />
            <meshPhysicalMaterial color={n.color} roughness={0.32} metalness={0.12} transparent opacity={0.9} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function Portal({ engine }) {
  const group = useRef();
  const spin = useRef();
  const glow = useRef();

  useFrame((state) => {
    if (!group.current) return;
    const { arrive, leave } = portalStage(engine.current.scroll);
    const reduce = engine.current.reduce;
    const a = reduce ? (arrive > 0.55 && leave < 0.45 ? 1 : 0) : cineEase(arrive);
    const e = reduce ? (leave >= 0.45 ? 1 : 0) : cineEase(leave);
    const opacity = Math.max(0, a * (1 - e));
    const scale = THREE.MathUtils.lerp(0.86, 1, a) * THREE.MathUtils.lerp(1, 0.16, e);
    const recede = THREE.MathUtils.lerp(0, 10, e);

    group.current.position.set(0, RING_Y, RING_Z - recede);
    group.current.scale.setScalar(Math.max(scale, 0.001));
    group.current.visible = opacity > 0.001;
    group.current.rotation.set(0, 0, 0);

    if (spin.current?.material) spin.current.material.opacity = opacity;
    if (glow.current?.material) glow.current.material.opacity = 0.45 * opacity;
    if (spin.current && !reduce && opacity > 0.04) {
      spin.current.rotation.z = state.clock.elapsedTime * 0.18;
    }
  });

  return (
    <group ref={group} position={[0, RING_Y, RING_Z]}>
      <mesh ref={spin} rotation={[0, 0, 0]}>
        <torusGeometry args={[RING_R, 0.028, 12, 80]} />
        <meshBasicMaterial color="#22D3EE" transparent depthWrite={false} opacity={0} />
      </mesh>
      <mesh ref={glow} rotation={[0, 0, 0]}>
        <torusGeometry args={[RING_R, 0.01, 8, 80]} />
        <meshBasicMaterial color="#67E8F9" transparent depthWrite={false} opacity={0} />
      </mesh>
    </group>
  );
}

function Ground() {
  const grid = useMemo(() => {
    const pos = [];
    const xSpan = 16;
    for (let z = 6; z >= -56; z -= 1.2) {
      pos.push(-xSpan, 0, z, xSpan, 0, z);
    }
    for (let x = -xSpan; x <= xSpan; x += 1.2) {
      pos.push(x, 0, 6, x, 0, -56);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    return g;
  }, []);
  return (
    <lineSegments geometry={grid} position={[0, -0.01, 0]}>
      <lineBasicMaterial color="#1A4E6E" transparent opacity={0.62} />
    </lineSegments>
  );
}

function Rig({ engine }) {
  const look = useMemo(() => new THREE.Vector3(), []);
  const axisP = useMemo(() => new THREE.Vector3(), []);
  const axisL = useMemo(() => new THREE.Vector3(), []);
  const { camera } = useThree();
  useFrame(() => {
    const { p, l } = lerpCam(engine.current.scroll);
    const labMix = labAmount();
    engine.current.lab = labMix;
    const { arrive } = portalStage(engine.current.scroll);
    const endMix = cineEase(arrive);
    const dist = ringCameraDistance(camera);
    axisP.set(0, RING_Y, RING_Z + dist);
    axisL.set(0, RING_Y, RING_Z);
    const useLab = labMix * (1 - endMix);
    const zoom = THREE.MathUtils.clamp(engine.current.twinZoom || 1, 0.75, 1.6);
    const panX = engine.current.twinPanX || 0;
    const panY = engine.current.twinPanY || 0;
    const labZ = LAB_CAM.l[2] + (LAB_CAM.p[2] - LAB_CAM.l[2]) / zoom;
    const sx = THREE.MathUtils.lerp(p[0], LAB_CAM.p[0] + panX, useLab);
    const sy = THREE.MathUtils.lerp(p[1], LAB_CAM.p[1] + panY, useLab);
    const sz = THREE.MathUtils.lerp(p[2], labZ, useLab);
    const slx = THREE.MathUtils.lerp(l[0], LAB_CAM.l[0] + panX, useLab);
    const sly = THREE.MathUtils.lerp(l[1], LAB_CAM.l[1] + panY, useLab);
    const slz = THREE.MathUtils.lerp(l[2], LAB_CAM.l[2], useLab);
    const tx = THREE.MathUtils.lerp(sx, axisP.x, endMix);
    const ty = THREE.MathUtils.lerp(sy, axisP.y, endMix);
    const tz = THREE.MathUtils.lerp(sz, axisP.z, endMix);
    const lx = THREE.MathUtils.lerp(slx, axisL.x, endMix);
    const ly = THREE.MathUtils.lerp(sly, axisL.y, endMix);
    const lz = THREE.MathUtils.lerp(slz, axisL.z, endMix);
    const end = endMix > 0.04;
    const mx = end || useLab > 0.55 ? 0 : engine.current.mouse.x * 0.28;
    const my = end || useLab > 0.55 ? 0 : engine.current.mouse.y * 0.16;
    const damp = engine.current.reduce ? 1 : end ? 0.085 : 0.055;
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, tx + mx, damp);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, ty + my, damp);
    camera.position.z = THREE.MathUtils.lerp(camera.position.z, tz, damp);
    look.set(lx, ly, lz);
    camera.up.set(0, 1, 0);
    camera.lookAt(look);
  });
  return null;
}

function MouseLight({ engine }) {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    ref.current.position.x = engine.current.mouse.x * 3.2;
    ref.current.position.y = 2.2 + engine.current.mouse.y * 1.1;
    ref.current.position.z = THREE.MathUtils.lerp(3.2, -46, engine.current.scroll);
    const risk = engine.current.risk / 100;
    const sim = engine.current.sim;
    ref.current.intensity = THREE.MathUtils.lerp(0.7 - risk * 0.22, 1.05, sim);
  });
  return <pointLight ref={ref} color="#67E8F9" intensity={1.1} distance={18} />;
}

export default function World({ engine, characterUrl }) {
  return (
    <>
      <color attach="background" args={["#050814"]} />
      <fog attach="fog" args={["#050814", 10, 42]} />
      <ambientLight intensity={0.28} color="#A9C8E8" />
      <hemisphereLight args={["#1B3A62", "#05060A", 0.48]} />
      <Environment preset="city" environmentIntensity={0.28} />
      <directionalLight
        position={[2.4, 5.4, 3.8]}
        intensity={0.85}
        color="#E8F4FF"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-far={28}
        shadow-camera-near={0.5}
        shadow-bias={-0.0002}
      />
      <directionalLight position={[-3.2, 2.4, -1.8]} intensity={0.7} color="#67E8F9" />
      <directionalLight position={[1.38, 1.4, 2.8]} intensity={0.28} color="#C7D7EA" />
      <MouseLight engine={engine} />
      <pointLight position={[2.05, 2.7, 1.55]} intensity={0.95} color="#9BE7FF" distance={9} />
      <pointLight position={[0.55, 1.35, 1.2]} intensity={0.28} color="#A78BFA" distance={7} />
      <Atmosphere engine={engine} />
      <Rig engine={engine} />
      <Chamber />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.021, -12]} receiveShadow>
        <planeGeometry args={[70, 80]} />
        <meshStandardMaterial color="#060A12" metalness={0.78} roughness={0.18} />
      </mesh>
      <Grid
        position={[0, 0, -12]}
        args={[40, 40]}
        cellSize={0.7}
        cellThickness={0.6}
        cellColor="#12324C"
        sectionSize={3.5}
        sectionThickness={1.1}
        sectionColor="#1E6A88"
        fadeDistance={32}
        fadeStrength={1.4}
        infiniteGrid
      />
      <Ground />
      <ContactShadows position={[1.38, 0.002, 0.08]} opacity={0.42} scale={4.5} blur={2.2} far={2.4} color="#00080C" />
      <Dust engine={engine} />
      <Student engine={engine} characterUrl={characterUrl} />
      {!engine.current.mobile && (
        <Sparkles count={12} scale={[3.2, 0.35, 3.2]} size={1.1} speed={0.18} color="#67E8F9" position={[1.38, 0.22, 0.08]} />
      )}
      <HeroHud engine={engine}>
        <HoloHUD engine={engine} />
      </HeroHud>
      <LaterScene engine={engine}>
        <RiskDNA engine={engine} />
        <WhyGraph engine={engine} />
        <InterventionOrbit engine={engine} />
        <Classroom engine={engine} />
        <PipelineNodes engine={engine} />
        <EngineLattice engine={engine} />
        <MetricBars engine={engine} />
        <Institution engine={engine} />
        <RiskUniverse engine={engine} />
      </LaterScene>
      <Portal engine={engine} />
      {!engine.current.mobile && (
        <EffectComposer disableNormalPass multisampling={0}>
          <Bloom luminanceThreshold={0.72} intensity={0.2} mipmapBlur radius={0.32} />
        </EffectComposer>
      )}
    </>
  );
}
