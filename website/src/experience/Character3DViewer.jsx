import { Component, Suspense, useEffect, useMemo, useRef } from "react";
import { Html, OrbitControls, useGLTF, useProgress } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { DEFAULT_CHARACTER_URL } from "./characterUrl";
import CharacterControls from "./CharacterControls";

const FACE_Y = 0.22;

function fitCharacter(root, targetHeight) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const height = Math.max(size.y, 0.001);
  root.scale.multiplyScalar(targetHeight / height);
  root.updateMatrixWorld(true);
  box.setFromObject(root);
  root.position.x -= (box.min.x + box.max.x) * 0.5;
  root.position.z -= (box.min.z + box.max.z) * 0.5;
  root.position.y -= box.min.y;
}

function prepareMeshes(root) {
  root.traverse((obj) => {
    if (!obj.isMesh) return;
    obj.castShadow = true;
    obj.receiveShadow = true;
    obj.frustumCulled = true;
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    mats.forEach((mat) => {
      if (!mat) return;
      mat.envMapIntensity = 1;
      if (mat.map) mat.map.colorSpace = THREE.SRGBColorSpace;
      mat.needsUpdate = true;
    });
  });
}

export function CharacterModel({ modelUrl = DEFAULT_CHARACTER_URL, targetHeight = 1.72, engine }) {
  const wrap = useRef();
  const { scene } = useGLTF(modelUrl);
  const fitted = useMemo(() => {
    const root = scene.clone(true);
    prepareMeshes(root);
    fitCharacter(root, targetHeight);
    return root;
  }, [scene, targetHeight]);

  useFrame(() => {
    if (!wrap.current) return;
    wrap.current.rotation.y = FACE_Y + (engine?.current?.twinYaw || 0);
    wrap.current.rotation.x = engine?.current?.twinPitch || 0;
  });

  useEffect(() => {
    if (engine?.current) engine.current.characterError = "";
  }, [engine, modelUrl]);

  return (
    <group ref={wrap}>
      <primitive object={fitted} />
    </group>
  );
}

export function CharacterLoading() {
  const { active, progress } = useProgress();
  if (!active) return null;
  return (
    <Html position={[0, 0.95, 0]} center>
      <div className="cine-twin-load">
        <span>Loading 3D Model...</span>
        <i style={{ width: `${Math.round(progress)}%` }} />
      </div>
    </Html>
  );
}

export class CharacterErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error) {
    this.props.onError?.(error);
  }

  render() {
    if (this.state.error) return this.props.fallback || null;
    return this.props.children;
  }
}

export function CharacterFallback({ message = "Couldn’t load 3D character" }) {
  return (
    <Html position={[0, 0.95, 0]} center>
      <p className="cine-twin-load cine-twin-load-error">{message}</p>
    </Html>
  );
}

function StandaloneStage({ modelUrl, engine }) {
  return (
    <>
      <color attach="background" args={["#050814"]} />
      <ambientLight intensity={0.4} color="#A9C8E8" />
      <hemisphereLight args={["#1B3A62", "#05060A", 0.5]} />
      <directionalLight position={[2.2, 4.4, 3.2]} intensity={1.1} color="#F2F7FF" castShadow />
      <directionalLight position={[-2.4, 1.8, -1.4]} intensity={0.55} color="#67E8F9" />
      <Suspense fallback={<CharacterLoading />}>
        <CharacterErrorBoundary
          resetKey={modelUrl}
          fallback={<CharacterFallback />}
          onError={(err) => {
            if (engine?.current) engine.current.characterError = err.message || "Load failed";
          }}
        >
          <CharacterModel modelUrl={modelUrl} engine={engine} />
        </CharacterErrorBoundary>
      </Suspense>
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} minDistance={1.4} maxDistance={6.5} target={[0, 0.85, 0]} />
    </>
  );
}

/**
 * R3F character loader. Pass `modelUrl` to swap the static TRELLIS GLB later.
 * Use `standalone` for a self-contained canvas; the Lab uses CharacterControls on the existing scene.
 */
export default function Character3DViewer({ modelUrl = DEFAULT_CHARACTER_URL, engine, standalone = false, compact = false }) {
  if (!standalone) {
    return <CharacterControls modelUrl={modelUrl} engine={engine} compact={compact} />;
  }
  return (
    <div className="cine-twin-standalone">
      <Canvas shadows camera={{ position: [0, 1.1, 3.6], fov: 34 }} gl={{ antialias: true }}>
        <StandaloneStage modelUrl={modelUrl} engine={engine} />
      </Canvas>
      <CharacterControls modelUrl={modelUrl} engine={engine} compact />
    </div>
  );
}

useGLTF.preload(DEFAULT_CHARACTER_URL);
