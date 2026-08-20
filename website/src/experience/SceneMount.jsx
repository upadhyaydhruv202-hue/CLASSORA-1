import { Canvas } from "@react-three/fiber";
import World from "./World";

export default function SceneMount({ engine, dpr }) {
  return (
    <Canvas
      dpr={dpr}
      camera={{ position: [0.08, 1.52, 3.7], fov: 42, near: 0.1, far: 90 }}
      gl={{
        alpha: false,
        antialias: !engine.current.mobile,
        stencil: false,
        powerPreference: "high-performance",
      }}
      className="cine-canvas h-full w-full"
    >
      <World engine={engine} />
    </Canvas>
  );
}
