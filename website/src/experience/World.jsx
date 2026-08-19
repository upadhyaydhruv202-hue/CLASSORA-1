import { useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { pipeline } from "../content";

const CAM = [
  { t: 0.0, p: [0.08, 1.46, 5.7], l: [1.38, 1.12, 0] },
  { t: 0.12, p: [0.55, 1.52, 4.15], l: [1.42, 1.18, 0] },
  { t: 0.26, p: [-0.15, 1.58, 7.15], l: [0.35, 1.05, -1.4] },
  { t: 0.4, p: [0.05, 1.48, 5.55], l: [0, 1.32, 0.2] },
  { t: 0.54, p: [1.05, 1.4, 4.35], l: [1.35, 1.16, 0] },
  { t: 0.66, p: [-0.2, 1.46, 5.9], l: [0.2, 1.12, 0] },
  { t: 0.8, p: [0.05, 8.4, 17.6], l: [0, 0.15, 0] },
  { t: 0.94, p: [0.22, 1.4, 3.45], l: [0.85, 1.16, 0] },
];

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

function Student({ engine }) {
  const g = useRef();
  const head = useRef();
  const ring = useRef();
  const links = useRef();

  useFrame((state) => {
    if (!g.current) return;
    const t = state.clock.elapsedTime;
    const s = engine.current.scroll;
    const hide = THREE.MathUtils.smoothstep(s, 0.72, 0.82) * (1 - THREE.MathUtils.smoothstep(s, 0.9, 0.97));
    g.current.visible = hide < 0.92;
    const breath = engine.current.reduce ? 0 : Math.sin(t * 1.12) * 0.016;
    g.current.position.x = engine.current.mobile ? 0.12 : 1.42;
    g.current.position.y = 0.04 + breath;
    const risk = engine.current.risk / 100;
    const sim = engine.current.sim;
    const isolated = THREE.MathUtils.lerp(risk, 0.12, sim);
    if (head.current && !engine.current.reduce) {
      head.current.rotation.y = THREE.MathUtils.lerp(head.current.rotation.y, engine.current.mouse.x * 0.22, 0.05);
      head.current.rotation.x = THREE.MathUtils.lerp(head.current.rotation.x, engine.current.mouse.y * 0.08, 0.05);
    }
    if (ring.current) {
      ring.current.rotation.z = t * 0.18;
      ring.current.material.opacity = THREE.MathUtils.lerp(0.55, 0.18, isolated);
      ring.current.scale.setScalar(THREE.MathUtils.lerp(1.08, 0.78, isolated));
    }
    if (links.current) {
      links.current.material.opacity = THREE.MathUtils.lerp(0.28, 0.06, isolated);
    }
    g.current.traverse((o) => {
      if (o.material && o.userData.core) {
        o.material.emissiveIntensity = THREE.MathUtils.lerp(0.05 + risk * 0.14, 0.07, sim);
      }
    });
  });

  const mat = {
    color: "#1e293b",
    roughness: 0.38,
    metalness: 0.18,
    emissive: "#2563eb",
    emissiveIntensity: 0.08,
  };

  const linkGeom = useMemo(() => {
    const pos = [];
    for (let i = 0; i < 14; i++) {
      const a = (i / 14) * Math.PI * 2;
      pos.push(0, 1.18, 0, Math.cos(a) * 1.85, 1.05 + Math.sin(i) * 0.35, Math.sin(a) * 1.85);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    return g;
  }, []);

  return (
    <group ref={g} position={[1.42, 0, 0]}>
      <mesh position={[0, 0.74, 0]} userData={{ core: true }}>
        <capsuleGeometry args={[0.23, 0.64, 8, 16]} />
        <meshStandardMaterial {...mat} />
      </mesh>
      <group ref={head} position={[0, 1.32, 0]}>
        <mesh userData={{ core: true }}>
          <sphereGeometry args={[0.21, 24, 24]} />
          <meshStandardMaterial {...mat} />
        </mesh>
      </group>
      <mesh position={[-0.34, 0.84, 0]} rotation={[0, 0, 0.52]} userData={{ core: true }}>
        <capsuleGeometry args={[0.065, 0.4, 4, 10]} />
        <meshStandardMaterial {...mat} />
      </mesh>
      <mesh position={[0.34, 0.84, 0]} rotation={[0, 0, -0.52]} userData={{ core: true }}>
        <capsuleGeometry args={[0.065, 0.4, 4, 10]} />
        <meshStandardMaterial {...mat} />
      </mesh>
      <mesh position={[-0.12, 0.18, 0]} userData={{ core: true }}>
        <capsuleGeometry args={[0.075, 0.44, 4, 10]} />
        <meshStandardMaterial {...mat} />
      </mesh>
      <mesh position={[0.12, 0.18, 0]} userData={{ core: true }}>
        <capsuleGeometry args={[0.075, 0.44, 4, 10]} />
        <meshStandardMaterial {...mat} />
      </mesh>
      <mesh ref={ring} rotation={[Math.PI / 2.4, 0, 0]} position={[0, 1.05, 0]}>
        <torusGeometry args={[0.62, 0.008, 8, 64]} />
        <meshBasicMaterial color="#2563EB" transparent opacity={0.4} />
      </mesh>
      <lineSegments ref={links} geometry={linkGeom} position={[0, 0, 0]}>
        <lineBasicMaterial color="#2563EB" transparent opacity={0.2} />
      </lineSegments>
    </group>
  );
}

function Dust({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const count = engine.current.mobile ? 70 : 180;
  const seeds = useMemo(() => {
    const s = [];
    for (let i = 0; i < count; i++) {
      s.push({
        a: Math.random() * Math.PI * 2,
        r: 1.5 + Math.random() * 7.2,
        y: (Math.random() - 0.35) * 5.2,
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
      let z = Math.sin(spin) * (p.r + scatter) * 0.7;
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
      <meshBasicMaterial color="#2563EB" transparent opacity={0.22} depthWrite={false} />
    </instancedMesh>
  );
}

function Classroom({ engine }) {
  const group = useRef();
  const spots = useMemo(
    () => [
      { x: -1.7, z: -1.55, risk: 0 },
      { x: -0.7, z: -2.05, risk: 1 },
      { x: 0.35, z: -1.7, risk: 2 },
      { x: 1.25, z: -2.25, risk: 1 },
      { x: 2.15, z: -1.55, risk: 0 },
    ],
    [],
  );
  const colors = [RISK.low, RISK.mid, RISK.high];

  useFrame((state) => {
    if (!group.current) return;
    const s = engine.current.scroll;
    const vis = THREE.MathUtils.smoothstep(s, 0.16, 0.24) * (1 - THREE.MathUtils.smoothstep(s, 0.36, 0.44));
    group.current.visible = vis > 0.03;
    group.current.children.forEach((c, i) => {
      const hot = engine.current.hoverStudent === i;
      const body = c.children[0];
      if (body?.material) body.material.opacity = vis * (hot ? 0.95 : 0.55);
      const glow = c.children[1];
      if (glow?.material) glow.material.opacity = vis * (hot ? 0.9 : 0.45);
      c.position.y = hot ? 0.12 + Math.sin(state.clock.elapsedTime * 2) * 0.02 : 0;
    });
  });

  return (
    <group ref={group} position={[0.4, 0.55, 0]}>
      {spots.map((p, i) => (
        <group key={i} position={[p.x, 0, p.z]}>
          <mesh>
            <capsuleGeometry args={[0.13, 0.5, 4, 8]} />
            <meshStandardMaterial color="#94A3B8" transparent opacity={0.55} />
          </mesh>
          <mesh position={[0, 0.58, 0]}>
            <sphereGeometry args={[0.045, 10, 10]} />
            <meshBasicMaterial color={colors[p.risk]} transparent opacity={0.7} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function PipelineNodes({ engine }) {
  const refs = useRef([]);
  useFrame((state) => {
    const s = engine.current.scroll;
    const vis = THREE.MathUtils.smoothstep(s, 0.32, 0.4) * (1 - THREE.MathUtils.smoothstep(s, 0.5, 0.58));
    refs.current.forEach((m, i) => {
      if (!m) return;
      const hot = engine.current.hotNode === i;
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.1 + i) * 0.035;
      m.scale.setScalar((hot ? 1.38 : 1) * pulse * (0.35 + vis * 0.65));
      m.material.emissiveIntensity = hot ? 1.05 : 0.32;
      m.visible = vis > 0.04;
    });
  });
  return (
    <group position={[0.05, 1.38, 0.15]}>
      {pipeline.map((n, i) => (
        <mesh
          key={n.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          position={[(i - 2) * 0.92, 0, 0]}
        >
          <octahedronGeometry args={[0.12, 0]} />
          <meshStandardMaterial color="#2563EB" emissive="#1D4ED8" emissiveIntensity={0.28} roughness={0.25} />
        </mesh>
      ))}
    </group>
  );
}

function EngineLattice({ engine }) {
  const group = useRef();
  const count = engine.current.mobile ? 28 : 48;
  const pts = useMemo(() => {
    const a = [];
    for (let i = 0; i < count; i++) {
      const u = (i / count) * Math.PI * 2;
      const v = (i % 6) / 6;
      a.push([Math.cos(u) * (0.7 + v * 0.45), (v - 0.5) * 1.15, Math.sin(u) * (0.7 + v * 0.45)]);
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
    const s = engine.current.scroll;
    const vis = THREE.MathUtils.smoothstep(s, 0.48, 0.56) * (1 - THREE.MathUtils.smoothstep(s, 0.68, 0.76));
    group.current.visible = vis > 0.04;
    group.current.rotation.y = state.clock.elapsedTime * 0.12;
    group.current.scale.setScalar(0.7 + vis * 0.5);
  });

  return (
    <group ref={group} position={[-1.6, 1.25, 0]}>
      {pts.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.028, 8, 8]} />
          <meshBasicMaterial color="#1D4ED8" />
        </mesh>
      ))}
      <lineSegments geometry={geom}>
        <lineBasicMaterial color="#2563EB" transparent opacity={0.22} />
      </lineSegments>
    </group>
  );
}

function AnalyticsBars({ engine }) {
  const g = useRef();
  const h = [0.9, 0.55, 0.72, 0.4, 0.63];
  useFrame(() => {
    if (!g.current) return;
    const s = engine.current.scroll;
    const vis = THREE.MathUtils.smoothstep(s, 0.62, 0.7) * (1 - THREE.MathUtils.smoothstep(s, 0.78, 0.84));
    g.current.visible = vis > 0.04;
    g.current.children.forEach((c, i) => {
      c.scale.y = vis * h[i];
      c.position.y = vis * h[i];
    });
  });
  return (
    <group ref={g} position={[2.1, 0.2, 0.4]}>
      {h.map((_, i) => (
        <mesh key={i} position={[(i - 2) * 0.28, 0, 0]}>
          <boxGeometry args={[0.16, 2, 0.16]} />
          <meshStandardMaterial color="#2563EB" emissive="#2563EB" emissiveIntensity={0.18} transparent opacity={0.75} />
        </mesh>
      ))}
    </group>
  );
}

function Institution({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const pal = useMemo(
    () => [new THREE.Color(RISK.low), new THREE.Color(RISK.mid), new THREE.Color(RISK.high)],
    [],
  );
  const count = engine.current.mobile ? 70 : 220;
  const seeds = useMemo(() => {
    const s = [];
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2;
      const r = 2.05 + (i % 9) * 0.48;
      s.push({
        x: Math.cos(a) * r,
        z: Math.sin(a) * r * 0.92,
        y: ((i * 17) % 11) * 0.16 - 0.15,
        risk: i % 11 === 0 ? 2 : i % 5 === 0 ? 1 : 0,
      });
    }
    return s;
  }, [count]);
  const painted = useRef(false);

  useFrame((state) => {
    if (!mesh.current) return;
    const s = engine.current.scroll;
    const vis = THREE.MathUtils.smoothstep(s, 0.74, 0.82) * (1 - THREE.MathUtils.smoothstep(s, 0.9, 0.97));
    mesh.current.visible = vis > 0.03;
    if (!painted.current) {
      seeds.forEach((p, i) => mesh.current.setColorAt(i, pal[p.risk]));
      if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
      painted.current = true;
    }
    const hover = engine.current.instHover;
    seeds.forEach((p, i) => {
      const hot = hover === i % 6;
      dummy.position.set(p.x, p.y + (hot ? 0.18 : 0), p.z);
      dummy.scale.setScalar(Math.max(0.001, vis) * (hot ? 1.9 : 1));
      dummy.rotation.y = state.clock.elapsedTime * 0.04;
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <sphereGeometry args={[0.055, 8, 8]} />
      <meshStandardMaterial vertexColors roughness={0.35} emissive="#111" emissiveIntensity={0.2} />
    </instancedMesh>
  );
}

function Ground() {
  const grid = useMemo(() => {
    const pos = [];
    const n = 18;
    for (let i = -n; i <= n; i++) {
      pos.push(-n, 0, i, n, 0, i, i, 0, -n, i, 0, n);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    return g;
  }, []);
  return (
    <lineSegments geometry={grid} position={[0, -0.01, 0]}>
      <lineBasicMaterial color="#CBD5E1" transparent opacity={0.85} />
    </lineSegments>
  );
}

function Rig({ engine }) {
  const look = useMemo(() => new THREE.Vector3(), []);
  const { camera } = useThree();
  useFrame(() => {
    const { p, l } = lerpCam(engine.current.scroll);
    const mx = engine.current.mouse.x * 0.2;
    const my = engine.current.mouse.y * 0.12;
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, p[0] + mx, 0.048);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, p[1] + my, 0.048);
    camera.position.z = THREE.MathUtils.lerp(camera.position.z, p[2], 0.048);
    look.set(l[0], l[1], l[2]);
    camera.lookAt(look);
  });
  return null;
}

function MouseLight({ engine }) {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    ref.current.position.x = 1.2 + engine.current.mouse.x * 2.8;
    ref.current.position.y = 2.15 + engine.current.mouse.y * 1.1;
    const risk = engine.current.risk / 100;
    const sim = engine.current.sim;
    ref.current.intensity = THREE.MathUtils.lerp(0.55 - risk * 0.22, 0.85, sim);
  });
  return <pointLight ref={ref} color="#2563EB" intensity={0.42} distance={11} />;
}

export default function World({ engine }) {
  return (
    <>
      <color attach="background" args={["#F8FAFC"]} />
      <fog attach="fog" args={["#F8FAFC", 8, 26]} />
      <ambientLight intensity={0.58} />
      <hemisphereLight args={["#EFF6FF", "#E2E8F0", 0.55]} />
      <directionalLight position={[5, 8, 3]} intensity={1.05} color="#ffffff" />
      <directionalLight position={[-6, 2, -4]} intensity={0.2} color="#2563EB" />
      <MouseLight engine={engine} />
      <Rig engine={engine} />
      <Ground />
      <Dust engine={engine} />
      <Student engine={engine} />
      <Classroom engine={engine} />
      <PipelineNodes engine={engine} />
      <EngineLattice engine={engine} />
      <AnalyticsBars engine={engine} />
      <Institution engine={engine} />
    </>
  );
}
