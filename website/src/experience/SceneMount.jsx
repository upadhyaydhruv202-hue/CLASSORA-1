import { Canvas } from "@react-three/fiber";
import World from "./World";

export default function SceneMount({ engine, dpr }) {
  return (
    <Canvas
      dpr={dpr}
      camera={{ position: [0.15, 1.42, 5.8], fov: 36, near: 0.1, far: 80 }}
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
