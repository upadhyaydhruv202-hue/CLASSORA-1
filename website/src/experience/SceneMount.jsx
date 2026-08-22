import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import World from "./World";
import { DEFAULT_CHARACTER_URL } from "./characterUrl";

export default function SceneMount({ engine, dpr, characterUrl = DEFAULT_CHARACTER_URL }) {
  useGLTF.preload(characterUrl);
  return (
    <Canvas
      shadows
      dpr={dpr}
      camera={{ position: [0.08, 1.06, 4.45], fov: 32, near: 0.1, far: 90 }}
      gl={{
        alpha: false,
        antialias: true,
        stencil: false,
        powerPreference: "high-performance",
      }}
      className="cine-canvas h-full w-full"
    >
      <Suspense fallback={null}>
        <World engine={engine} characterUrl={characterUrl} />
      </Suspense>
    </Canvas>
  );
}
