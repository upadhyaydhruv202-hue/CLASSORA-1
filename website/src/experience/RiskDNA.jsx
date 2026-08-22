import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const NODE_COLOR = ["#F87171", "#A78BFA", "#22D3EE", "#FBBF24", "#34D399"];

function helixPoint(i, n, strand) {
  const u = i / n;
  const t = u * Math.PI * 5.2 + strand * Math.PI;
  const y = 0.42 + u * 1.38;
  const r = 0.34 + Math.sin(u * Math.PI) * 0.08;
  return [Math.cos(t) * r, y, Math.sin(t) * r];
}

export default function RiskDNA({ engine }) {
  const group = useRef();
  const nodes = useRef([]);
  const helix = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const count = engine.current.mobile ? 48 : 96;
  const geom = useMemo(() => {
    const pos = [];
    for (let s = 0; s < 2; s += 1) {
      for (let i = 0; i < count; i += 1) {
        const p = helixPoint(i, count, s);
        const q = helixPoint(Math.min(i + 1, count - 1), count, s);
        pos.push(...p, ...q);
        if (s === 0 && i % 6 === 0) {
          const r = helixPoint(i, count, 1);
          pos.push(...p, ...r);
        }
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    return g;
  }, [count]);

  useFrame((state) => {
    if (!group.current) return;
    const t = state.clock.elapsedTime;
    const reduce = engine.current.reduce;
    const factors = engine.current.factors || [];
    const focus = engine.current.factor;
    const analyze = engine.current.analyze || 0;
    const step = engine.current.analyzeStep ?? -1;
    const sim = engine.current.sim || 0;
    const lab = engine.current.lab || 0;
    const scroll = engine.current.scroll || 0;
    group.current.visible = scroll > 0.22 && scroll < 0.46 && lab < 0.2;
    group.current.rotation.y = reduce ? 0 : t * 0.18;

    for (let i = 0; i < 5; i += 1) {
      const mesh = nodes.current[i];
      if (!mesh) continue;
      const contrib = (factors[i]?.contribution || 8) / 100;
      const p = helixPoint(Math.floor(((i + 0.5) / 5) * (count - 1)), count, 0);
      dummy.position.set(p[0], p[1], p[2]);
      const hot = focus === i || step === i;
      const appear = analyze > 0 ? THREE.MathUtils.smoothstep(analyze, i * 0.16, i * 0.16 + 0.22) : 1;
      dummy.scale.setScalar((0.85 + contrib * 2.1) * (hot ? 1.55 : 1) * Math.max(appear, 0.2) * (1 - sim * 0.12));
      dummy.updateMatrix();
      mesh.matrix.copy(dummy.matrix);
      mesh.matrixAutoUpdate = false;
      if (mesh.material) {
        mesh.material.opacity = 0.4 + appear * 0.55 + (hot ? 0.2 : 0);
        mesh.material.emissiveIntensity = hot ? 0.9 : 0.28;
      }
    }
    if (helix.current?.material) {
      helix.current.material.opacity = 0.22 + analyze * 0.35 + (1 - sim) * 0.08;
    }
  });

  return (
    <group ref={group} position={[0, 0.2, -18.2]} scale={1.08}>
      <lineSegments ref={helix} geometry={geom}>
        <lineBasicMaterial color="#67E8F9" transparent opacity={0.28} />
      </lineSegments>
      {NODE_COLOR.map((color, i) => (
        <mesh
          key={color}
          ref={(el) => {
            nodes.current[i] = el;
          }}
          scale={0.001}
        >
          <sphereGeometry args={[0.07, 14, 14]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.28} transparent opacity={0.8} roughness={0.25} />
        </mesh>
      ))}
    </group>
  );
}
