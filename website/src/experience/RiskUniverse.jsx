import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { classroomStudents, networkStudents } from "../content";

const TONE = {
  HIGH: "#ef4444",
  ATTENTION: "#f59e0b",
  STABLE: "#22c55e",
};

const CLUSTER = {
  HIGH: [-2.35, 0, 0],
  ATTENTION: [0, 0, 0],
  STABLE: [2.35, 0, 0],
};

function uniqueRoster() {
  const map = new Map();
  [...classroomStudents, ...networkStudents].forEach((s) => {
    if (!map.has(s.id)) map.set(s.id, s);
  });
  return [...map.values()];
}

export default function RiskUniverse({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const roster = useMemo(() => uniqueRoster(), []);
  const count = engine.current.mobile ? 120 : 360;
  const pal = useMemo(
    () => ({
      HIGH: new THREE.Color(TONE.HIGH),
      ATTENTION: new THREE.Color(TONE.ATTENTION),
      STABLE: new THREE.Color(TONE.STABLE),
    }),
    [],
  );

  const seeds = useMemo(() => {
    const s = [];
    for (let i = 0; i < count; i += 1) {
      const src = roster[i % roster.length];
      const c = CLUSTER[src.risk] || CLUSTER.STABLE;
      const a = (i / 12) * Math.PI * 2;
      const spread = 0.22 + (Math.floor(i / roster.length) % 5) * 0.12;
      s.push({
        x: c[0] + Math.cos(a) * spread * (0.7 + (i % 5) * 0.12),
        z: c[2] + Math.sin(a) * spread,
        y: ((i * 13) % 9) * 0.08 - 0.1,
        risk: src.risk,
        id: src.id,
      });
    }
    return s;
  }, [count, roster]);

  const painted = useRef(false);

  useFrame((state) => {
    if (!mesh.current) return;
    if (!painted.current) {
      seeds.forEach((p, i) => mesh.current.setColorAt(i, pal[p.risk] || pal.STABLE));
      if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
      painted.current = true;
    }
    const hover = engine.current.instHover;
    const focusId = engine.current.focusStudent;
    const t = engine.current.reduce ? 0 : state.clock.elapsedTime;
    seeds.forEach((p, i) => {
      const hot = hover === i || (focusId && p.id === focusId);
      dummy.position.set(p.x, p.y + (hot ? 0.16 : 0) + Math.sin(t * 0.55 + i) * 0.025, p.z);
      dummy.scale.setScalar(hot ? 1.9 : p.risk === "HIGH" ? 1.2 : 1);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]} position={[0, 0.22, -38]}>
      <sphereGeometry args={[0.048, 8, 8]} />
      <meshStandardMaterial vertexColors roughness={0.32} metalness={0.12} emissive="#111" emissiveIntensity={0.25} />
    </instancedMesh>
  );
}
