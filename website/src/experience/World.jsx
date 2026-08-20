import { useMemo, useRef } from "react";
import { ContactShadows } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { pipeline } from "../content";

const CAM = [
  { t: 0, p: [0.08, 1.52, 3.7], l: [1.38, 1.08, 0] },
  { t: 0.18, p: [0.35, 1.92, -4.4], l: [0, 0.82, -9.2] },
  { t: 0.36, p: [0.05, 1.58, -13.4], l: [0, 1.22, -18.2] },
  { t: 0.54, p: [2.55, 1.72, -22.6], l: [0, 1.22, -27.2] },
  { t: 0.72, p: [0.12, 9.4, -28.5], l: [0, 0.15, -38] },
  { t: 0.9, p: [0, 1.52, -43.2], l: [0, 1.12, -48] },
  { t: 1, p: [0, 1.42, -44.6], l: [0, 1.12, -48] },
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

function setCursor(engine, label) {
  engine.current.cursor = label;
}

function Student({ engine }) {
  const g = useRef();
  const head = useRef();
  const ring = useRef();
  const links = useRef();

  useFrame((state) => {
    if (!g.current) return;
    const t = state.clock.elapsedTime;
    const breath = engine.current.reduce ? 0 : Math.sin(t * 1.12) * 0.016;
    g.current.position.y = breath;
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
      ring.current.scale.setScalar(THREE.MathUtils.lerp(1.12, 0.78, isolated));
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
    <group ref={g} position={[1.35, 0, 0]} scale={1.18}>
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
      <lineSegments ref={links} geometry={linkGeom}>
        <lineBasicMaterial color="#2563EB" transparent opacity={0.2} />
      </lineSegments>
    </group>
  );
}

function Dust({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const count = engine.current.mobile ? 90 : 260;
  const seeds = useMemo(() => {
    const s = [];
    for (let i = 0; i < count; i++) {
      s.push({
        a: Math.random() * Math.PI * 2,
        r: 1.2 + Math.random() * 6.4,
        z: -Math.random() * 52,
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
      <sphereGeometry args={[0.014, 6, 6]} />
      <meshBasicMaterial color="#2563EB" transparent opacity={0.22} depthWrite={false} />
    </instancedMesh>
  );
}

function Classroom({ engine }) {
  const spots = useMemo(
    () => [
      { x: -2.1, z: -0.2, risk: 0 },
      { x: -1.05, z: -1.15, risk: 1 },
      { x: 0, z: -0.55, risk: 2 },
      { x: 1.1, z: -1.35, risk: 1 },
      { x: 2.15, z: -0.25, risk: 0 },
    ],
    [],
  );
  const colors = [RISK.low, RISK.mid, RISK.high];
  const refs = useRef([]);

  useFrame((state) => {
    refs.current.forEach((c, i) => {
      if (!c) return;
      const hot = engine.current.hoverStudent === i;
      c.position.y = hot ? 0.14 + Math.sin(state.clock.elapsedTime * 2) * 0.02 : 0;
      const body = c.children[0];
      if (body?.material) body.material.opacity = hot ? 0.95 : 0.62;
    });
  });

  return (
    <group position={[0, 0.55, -9.2]}>
      {spots.map((p, i) => (
        <group
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          position={[p.x, 0, p.z]}
          onPointerOver={(e) => {
            e.stopPropagation();
            engine.current.hoverStudent = i;
            setCursor(engine, "INSPECT");
          }}
          onPointerOut={() => {
            engine.current.hoverStudent = -1;
            setCursor(engine, "");
          }}
          onClick={(e) => {
            e.stopPropagation();
            engine.current.hoverStudent = i;
          }}
        >
          <mesh>
            <capsuleGeometry args={[0.18, 0.62, 6, 10]} />
            <meshStandardMaterial color="#94A3B8" transparent opacity={0.62} />
          </mesh>
          <mesh position={[0, 0.72, 0]}>
            <sphereGeometry args={[0.055, 12, 12]} />
            <meshBasicMaterial color={colors[p.risk]} transparent opacity={0.85} />
          </mesh>
        </group>
      ))}
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

function Institution({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const pal = useMemo(
    () => [new THREE.Color(RISK.low), new THREE.Color(RISK.mid), new THREE.Color(RISK.high)],
    [],
  );
  const count = engine.current.mobile ? 90 : 240;
  const seeds = useMemo(() => {
    const s = [];
    for (let i = 0; i < count; i++) {
      const a = (i / count) * Math.PI * 2;
      const r = 2.2 + (i % 9) * 0.52;
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
    if (!painted.current) {
      seeds.forEach((p, i) => mesh.current.setColorAt(i, pal[p.risk]));
      if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
      painted.current = true;
    }
    const hover = engine.current.instHover;
    seeds.forEach((p, i) => {
      const hot = hover === i;
      dummy.position.set(p.x, p.y + (hot ? 0.22 : 0), p.z);
      dummy.scale.setScalar(hot ? 1.95 : 1);
      dummy.rotation.y = state.clock.elapsedTime * 0.04;
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      ref={mesh}
      args={[undefined, undefined, count]}
      position={[0, 0.2, -38]}
      onPointerMove={(e) => {
        e.stopPropagation();
        engine.current.instHover = e.instanceId ?? -1;
        setCursor(engine, "VIEW");
      }}
      onPointerOut={() => {
        engine.current.instHover = -1;
        setCursor(engine, "");
      }}
    >
      <sphereGeometry args={[0.06, 8, 8]} />
      <meshStandardMaterial vertexColors roughness={0.35} emissive="#111" emissiveIntensity={0.2} />
    </instancedMesh>
  );
}

function Portal({ engine }) {
  const ring = useRef();
  useFrame((state) => {
    if (!ring.current || engine.current.reduce) return;
    ring.current.rotation.z = state.clock.elapsedTime * 0.22;
  });
  return (
    <group position={[0, 1.15, -48]}>
      <mesh ref={ring} rotation={[0, 0, 0]}>
        <torusGeometry args={[1.05, 0.028, 12, 80]} />
        <meshBasicMaterial color="#2563EB" />
      </mesh>
      <mesh>
        <torusGeometry args={[1.05, 0.01, 8, 80]} />
        <meshBasicMaterial color="#93C5FD" transparent opacity={0.45} />
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
      <lineBasicMaterial color="#CBD5E1" transparent opacity={0.7} />
    </lineSegments>
  );
}

function Rig({ engine }) {
  const look = useMemo(() => new THREE.Vector3(), []);
  const { camera } = useThree();
  useFrame(() => {
    const { p, l } = lerpCam(engine.current.scroll);
    const mx = engine.current.mouse.x * 0.28;
    const my = engine.current.mouse.y * 0.16;
    const damp = engine.current.reduce ? 1 : 0.055;
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, p[0] + mx, damp);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, p[1] + my, damp);
    camera.position.z = THREE.MathUtils.lerp(camera.position.z, p[2], damp);
    look.set(l[0], l[1], l[2]);
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
  return <pointLight ref={ref} color="#2563EB" intensity={0.7} distance={14} />;
}

export default function World({ engine }) {
  return (
    <>
      <color attach="background" args={["#F8FAFC"]} />
      <fog attach="fog" args={["#F8FAFC", 10, 32]} />
      <ambientLight intensity={0.58} />
      <hemisphereLight args={["#EFF6FF", "#E2E8F0", 0.55]} />
      <directionalLight position={[5, 8, 3]} intensity={1.1} color="#ffffff" />
      <directionalLight position={[-6, 2, -4]} intensity={0.22} color="#2563EB" />
      <MouseLight engine={engine} />
      <Rig engine={engine} />
      <Ground />
      <ContactShadows position={[0, 0, 0]} opacity={0.22} scale={28} blur={2.4} far={10} />
      <Dust engine={engine} />
      <Student engine={engine} />
      <Classroom engine={engine} />
      <PipelineNodes engine={engine} />
      <EngineLattice engine={engine} />
      <Institution engine={engine} />
      <Portal engine={engine} />
    </>
  );
}
