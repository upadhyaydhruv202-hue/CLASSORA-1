import { Suspense, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { TWIN_NODES, lineTerminus } from "./twinLayout";
import { DEFAULT_CHARACTER_URL } from "./characterUrl";
import { CharacterErrorBoundary, CharacterFallback, CharacterLoading, CharacterModel } from "./Character3DViewer";

function DataStreams({ engine }) {
  const mesh = useRef();
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const per = 4;
  const count = TWIN_NODES.length * per;
  const ends = useMemo(() => TWIN_NODES.map((n) => lineTerminus(n.pos)), []);

  useFrame((state) => {
    if (!mesh.current) return;
    const t = engine.current.reduce ? 0 : state.clock.elapsedTime * 0.12;
    const focus = engine.current.factor;
    let i = 0;
    TWIN_NODES.forEach((n, ni) => {
      const end = ends[ni];
      const hot = focus === n.factor;
      for (let k = 0; k < per; k += 1) {
        const u = (t + ni * 0.14 + k / per) % 1;
        dummy.position.set(n.pos[0] + (end[0] - n.pos[0]) * u, n.pos[1] + (end[1] - n.pos[1]) * u, n.pos[2] + (end[2] - n.pos[2]) * u);
        dummy.scale.setScalar((hot ? 1.15 : 0.7) * (0.45 + (1 - u) * 0.55));
        dummy.updateMatrix();
        mesh.current.setMatrixAt(i, dummy.matrix);
        i += 1;
      }
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]} frustumCulled={false} renderOrder={1}>
      <sphereGeometry args={[0.008, 6, 6]} />
      <meshBasicMaterial color="#67E8F9" transparent opacity={0.42} depthWrite={false} />
    </instancedMesh>
  );
}

export default function Student({ engine, characterUrl = DEFAULT_CHARACTER_URL }) {
  const root = useRef();
  const rings = useRef([]);
  const scan = useRef();
  const floorGlow = useRef();
  const color = useMemo(() => new THREE.Color("#22D3EE"), []);
  const recover = useMemo(() => new THREE.Color("#34D399"), []);

  useFrame((state) => {
    if (!root.current) return;
    const t = state.clock.elapsedTime;
    const reduce = engine.current.reduce;
    root.current.position.y = reduce ? 0 : Math.sin(t * 1.05) * 0.005;
    const risk = THREE.MathUtils.clamp(engine.current.risk / 100, 0, 1);
    const sim = THREE.MathUtils.clamp(engine.current.sim || 0, 0, 1);
    const analyze = THREE.MathUtils.clamp(engine.current.analyze || 0, 0, 1);
    const isolated = THREE.MathUtils.lerp(risk, 0.12, sim);
    color.set(isolated > 0.62 ? "#F87171" : isolated > 0.4 ? "#FBBF24" : "#22D3EE");
    if (sim > 0.35) color.lerp(recover, sim * 0.65);

    rings.current.forEach((mesh, i) => {
      if (!mesh?.material) return;
      mesh.rotation.z = (reduce ? 0 : t * (0.05 + i * 0.02)) * (1 + isolated * 0.25);
      mesh.material.color.lerp(color, 0.08);
      mesh.material.opacity = 0.32 + isolated * 0.12 + analyze * 0.15;
    });
    if (floorGlow.current?.material) {
      floorGlow.current.material.color.lerp(color, 0.08);
      floorGlow.current.material.opacity = 0.08 + isolated * 0.08;
    }
    if (scan.current) {
      const on = analyze > 0.05 && analyze < 0.95;
      scan.current.visible = on;
      scan.current.position.y = 0.08 + analyze * 1.62;
      if (scan.current.material) scan.current.material.opacity = on ? 0.4 : 0;
    }
  });

  return (
    <group ref={root} position={[1.38, 0, 0.08]}>
      <spotLight position={[0.45, 2.5, 2.2]} angle={0.5} penumbra={0.88} intensity={1.85} color="#F7FAFF" distance={8} />
      <pointLight position={[-0.4, 1.5, -0.45]} intensity={0.45} color="#67E8F9" distance={3} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]} receiveShadow>
        <circleGeometry args={[0.46, 48]} />
        <meshStandardMaterial color="#081018" metalness={0.72} roughness={0.26} emissive="#0E7490" emissiveIntensity={0.1} />
      </mesh>
      <mesh ref={floorGlow} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.003, 0]}>
        <ringGeometry args={[0.22, 0.48, 48]} />
        <meshBasicMaterial color="#22D3EE" transparent opacity={0.1} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      {[0.28, 0.4].map((r, i) => (
        <mesh
          key={r}
          ref={(el) => {
            rings.current[i] = el;
          }}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, 0.008 + i * 0.003, 0]}
        >
          <torusGeometry args={[r, 0.007, 8, 64]} />
          <meshBasicMaterial color="#22D3EE" transparent opacity={0.45} depthWrite={false} />
        </mesh>
      ))}

      <CharacterLoading />
      <Suspense fallback={null}>
        <CharacterErrorBoundary
          resetKey={characterUrl}
          fallback={<CharacterFallback />}
          onError={(err) => {
            engine.current.characterError = err?.message || "Couldn’t load 3D character";
          }}
        >
          <CharacterModel modelUrl={characterUrl} engine={engine} targetHeight={1.72} />
        </CharacterErrorBoundary>
      </Suspense>

      <DataStreams engine={engine} />
      <mesh ref={scan} rotation={[Math.PI / 2, 0, 0]} position={[0, 0.3, 0]} visible={false}>
        <ringGeometry args={[0.14, 0.28, 40]} />
        <meshBasicMaterial color="#67E8F9" transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}
