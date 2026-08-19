import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";

const nodeSphere = new THREE.SphereGeometry(0.085, 12, 12);
const COMPOSITION_RADIUS = 1.62;

const NODES = [
  { label: "Face identity", detail: "dlib embeddings · enrolled roster only", pos: [1.38, 0.48, 0.28], color: "#2563EB" },
  { label: "Voice presence", detail: "Resemblyzer match on spoken attendance", pos: [-1.36, 0.36, 0.3], color: "#0891B2" },
  { label: "Success Hub", detail: "Human-approved interventions", pos: [0.04, 1.32, -0.22], color: "#1D4ED8" },
  { label: "Attendance truth", detail: "is_present logs · Regular / Watch / Critical", pos: [1.08, -1.02, 0.2], color: "#0B1F4A" },
  { label: "Counsellor loop", detail: "Accept · modify · reject — never silent", pos: [-1.06, -0.98, 0.26], color: "#334155" },
];

function Core({ mouse, scroll }) {
  const group = useRef();
  const ring = useRef();
  const ring2 = useRef();
  const ring3 = useRef();
  const { ico, edges, torusA, torusB, torusC } = useMemo(() => {
    const ico = new THREE.IcosahedronGeometry(0.88, 1);
    return {
      ico,
      edges: new THREE.EdgesGeometry(ico),
      torusA: new THREE.TorusGeometry(1.22, 0.012, 8, 64),
      torusB: new THREE.TorusGeometry(1.38, 0.008, 8, 56),
      torusC: new THREE.TorusGeometry(1.52, 0.006, 6, 48),
    };
  }, []);
  useEffect(
    () => () => {
      ico.dispose();
      edges.dispose();
      torusA.dispose();
      torusB.dispose();
      torusC.dispose();
    },
    [ico, edges, torusA, torusB, torusC],
  );
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (!group.current) return;
    group.current.rotation.y = t * 0.2 + mouse.current.x * 0.18;
    group.current.rotation.x = 0.16 + mouse.current.y * 0.12 + scroll.current * 0.12;
    group.current.position.y = Math.sin(t * 0.45) * 0.025;
    if (ring.current) ring.current.rotation.z = t * 0.12;
    if (ring2.current) ring2.current.rotation.z = -t * 0.08;
    if (ring3.current) ring3.current.rotation.z = t * 0.045;
  });

  return (
    <group ref={group}>
      <mesh geometry={ico} scale={1.16}>
        <meshBasicMaterial color="#2563EB" transparent opacity={0.055} depthWrite={false} side={THREE.BackSide} />
      </mesh>
      <mesh geometry={ico}>
        <meshPhysicalMaterial
          color="#0B1F4A"
          metalness={0.5}
          roughness={0.14}
          clearcoat={1}
          clearcoatRoughness={0.1}
          emissive="#1E3A8A"
          emissiveIntensity={0.3}
          envMapIntensity={0.85}
        />
      </mesh>
      <lineSegments geometry={edges} scale={1.035}>
        <lineBasicMaterial color="#93C5FD" transparent opacity={0.42} />
      </lineSegments>
      <mesh ref={ring} geometry={torusA} rotation={[Math.PI / 2.4, 0.18, 0]}>
        <meshBasicMaterial color="#2563EB" transparent opacity={0.78} />
      </mesh>
      <mesh ref={ring2} geometry={torusB} rotation={[0.38, 0.72, 0.18]}>
        <meshBasicMaterial color="#22D3EE" transparent opacity={0.38} />
      </mesh>
      <mesh ref={ring3} geometry={torusC} rotation={[1.15, 0.25, 0.4]}>
        <meshBasicMaterial color="#93C5FD" transparent opacity={0.18} />
      </mesh>
    </group>
  );
}

function DataNode({ node, mouse }) {
  const ref = useRef();
  const [hot, setHot] = useState(false);
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (!ref.current) return;
    ref.current.position.y = node.pos[1] + Math.sin(t * 0.7 + node.pos[0]) * 0.045;
    ref.current.position.x = node.pos[0] + mouse.current.x * 0.05;
  });
  return (
    <group
      ref={ref}
      position={node.pos}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHot(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHot(false);
        document.body.style.cursor = "default";
      }}
    >
      <mesh geometry={nodeSphere} scale={hot ? 1.18 : 1}>
        <meshStandardMaterial
          color={node.color}
          emissive={node.color}
          emissiveIntensity={hot ? 0.5 : 0.24}
          roughness={0.35}
          metalness={0.15}
        />
      </mesh>
      {hot && (
        <Html distanceFactor={8} position={[0, 0.24, 0]} center>
          <div className="w-48 rounded-xl border border-[#d7e0ee] bg-white/95 px-3 py-2 text-left shadow-lg">
            <div className="text-[11px] font-semibold tracking-wide text-[#0B1F4A]">{node.label}</div>
            <div className="mt-0.5 text-[10px] leading-snug text-[#5b6b82]">{node.detail}</div>
          </div>
        </Html>
      )}
    </group>
  );
}

function Links() {
  const geom = useMemo(() => {
    const positions = [];
    NODES.forEach((n) => positions.push(0, 0, 0, n.pos[0], n.pos[1], n.pos[2]));
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    return g;
  }, []);
  useEffect(() => () => geom.dispose(), [geom]);
  return (
    <lineSegments geometry={geom}>
      <lineBasicMaterial color="#93C5FD" transparent opacity={0.36} />
    </lineSegments>
  );
}

function Particles() {
  const ref = useRef();
  const { positions, count } = useMemo(() => {
    const count =
      typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches ? 10 : 18;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 1.42 + (i % 5) * 0.04;
      const theta = (i / count) * Math.PI * 2 + i * 0.17;
      const phi = Math.acos(((i % 7) - 3) / 4.2);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.62;
      positions[i * 3 + 2] = r * Math.cos(phi) * 0.48;
    }
    return { positions, count };
  }, []);
  useFrame((state) => {
    if (ref.current) ref.current.rotation.y = state.clock.elapsedTime * 0.028;
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} count={count} />
      </bufferGeometry>
      <pointsMaterial size={0.022} color="#60A5FA" transparent opacity={0.45} sizeAttenuation depthWrite={false} />
    </points>
  );
}

function FitGroup({ children }) {
  const { viewport, size } = useThree();
  const scale = useMemo(() => {
    const h = Math.max(size.height, 1);
    const targetPx =
      h < 480 ? Math.min(h * 0.52, 260) : THREE.MathUtils.clamp(h * 0.4, 308, 324);
    const targetWorld = (targetPx / h) * viewport.height;
    return THREE.MathUtils.clamp(targetWorld / (COMPOSITION_RADIUS * 2), 0.64, 0.78);
  }, [viewport.height, size.height]);
  return (
    <group scale={scale} position={[0, 0, 0]}>
      {children}
    </group>
  );
}

function Scene({ mouse, scroll }) {
  return (
    <>
      <ambientLight intensity={0.82} />
      <hemisphereLight args={["#DBEAFE", "#0B1F4A", 0.42]} />
      <directionalLight position={[4, 6, 5]} intensity={1.12} />
      <directionalLight position={[-3, 2, -2]} intensity={0.28} color="#67E8F9" />
      <pointLight position={[0, 0.2, 1.4]} intensity={0.35} color="#60A5FA" distance={4} />
      <FitGroup>
        <group>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.78, 0]} renderOrder={-1}>
            <circleGeometry args={[1.2, 28]} />
            <meshBasicMaterial color="#93C5FD" transparent opacity={0.16} depthWrite={false} />
          </mesh>
          <Particles />
          <Links />
          <Core mouse={mouse} scroll={scroll} />
          {NODES.map((node) => (
            <DataNode key={node.label} node={node} mouse={mouse} />
          ))}
        </group>
      </FitGroup>
    </>
  );
}

export default function HeroScene({ mouse, scroll }) {
  const dpr = useMemo(() => {
    if (typeof window === "undefined") return 1;
    const mobile = window.matchMedia("(max-width: 768px)").matches;
    return Math.min(window.devicePixelRatio || 1, mobile ? 1.15 : 1.5);
  }, []);
  return (
    <Canvas
      dpr={dpr}
      camera={{ position: [0, 0, 7.1], fov: 36 }}
      flat
      gl={{
        alpha: true,
        antialias: true,
        stencil: false,
        depth: true,
        powerPreference: "high-performance",
        premultipliedAlpha: false,
        preserveDrawingBuffer: false,
      }}
      onCreated={({ gl, scene, camera }) => {
        gl.setClearColor(0x000000, 0);
        gl.setClearAlpha(0);
        scene.background = null;
        scene.fog = null;
        camera.lookAt(0, 0, 0);
        gl.domElement.style.background = "transparent";
      }}
      className="hero-canvas h-full w-full bg-transparent"
      style={{ width: "100%", height: "100%", background: "transparent" }}
    >
      <Scene mouse={mouse} scroll={scroll} />
    </Canvas>
  );
}
