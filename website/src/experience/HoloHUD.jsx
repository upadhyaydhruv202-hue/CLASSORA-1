import { useMemo, useRef } from "react";
import { Text } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { TWIN_NODES, lineTerminus } from "./twinLayout";

function NodePanel({ node, textRef }) {
  return (
    <>
      <mesh position={[0, -0.17, -0.012]} renderOrder={2}>
        <planeGeometry args={[0.52, 0.16]} />
        <meshBasicMaterial color="#050A14" transparent opacity={0.82} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.028, 16, 16]} />
        <meshBasicMaterial color={node.color} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.048, 16, 16]} />
        <meshBasicMaterial color={node.color} transparent opacity={0.14} depthWrite={false} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.054, 0.066, 24]} />
        <meshBasicMaterial color={node.color} transparent opacity={0.85} side={THREE.DoubleSide} />
      </mesh>
      <Text
        ref={textRef}
        position={[0, -0.16, 0.002]}
        fontSize={0.034}
        color="#E8F6FF"
        anchorX="center"
        anchorY="middle"
        textAlign="center"
        outlineWidth={0.004}
        outlineColor="#050A14"
        lineHeight={1.18}
        renderOrder={3}
      >
        {node.label}
      </Text>
    </>
  );
}

export default function HoloHUD({ engine }) {
  const labels = useRef([]);
  const lines = useRef();
  const hotLine = useRef();
  const nodes = useRef([]);
  const positions = useMemo(() => new Float32Array(TWIN_NODES.length * 6), []);
  const hotPos = useMemo(() => new Float32Array(6), []);
  const geom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return g;
  }, [positions]);
  const hotGeom = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(hotPos, 3));
    return g;
  }, [hotPos]);
  const ends = useMemo(() => TWIN_NODES.map((n) => lineTerminus(n.pos)), []);

  useFrame((state) => {
    const m = engine.current.metrics || { attendance: 62, academic: 54, assignments: 48, engagement: "LOW", trend: "DECLINING" };
    const factors = engine.current.factors || [];
    const focus = engine.current.factor;
    const t = state.clock.elapsedTime;
    const values = [
      `${m.attendance}%`,
      String(m.engagement || "LOW"),
      `${m.academic}%`,
      String(m.trend || "DECLINING"),
      `${m.assignments}%`,
    ];
    labels.current.forEach((txt, i) => {
      if (!txt) return;
      const fi = TWIN_NODES[i].factor;
      const contrib = factors[fi]?.contribution;
      const hot = focus === fi;
      txt.text = hot && contrib != null ? `${TWIN_NODES[i].label}\n${values[i]}  ·  ${contrib}%` : `${TWIN_NODES[i].label}\n${values[i]}`;
    });
    nodes.current.forEach((grp, i) => {
      if (!grp) return;
      const fi = TWIN_NODES[i].factor;
      const hot = focus === fi;
      const floatY = Math.sin(t * 0.7 + i) * 0.018;
      grp.position.y = TWIN_NODES[i].pos[1] + floatY;
      grp.scale.setScalar(hot ? 1.12 : 1);
    });
    TWIN_NODES.forEach((node, i) => {
      const end = ends[i];
      positions[i * 6] = end[0];
      positions[i * 6 + 1] = end[1];
      positions[i * 6 + 2] = end[2];
      positions[i * 6 + 3] = node.pos[0];
      positions[i * 6 + 4] = node.pos[1];
      positions[i * 6 + 5] = node.pos[2];
    });
    if (lines.current) {
      lines.current.geometry.attributes.position.needsUpdate = true;
      lines.current.material.opacity = 0.14 + (focus >= 0 ? 0.06 : 0);
    }
    if (hotLine.current) {
      const node = TWIN_NODES.find((n) => n.factor === focus);
      const idx = TWIN_NODES.findIndex((n) => n.factor === focus);
      const on = idx >= 0;
      hotLine.current.visible = on;
      if (on) {
        const end = ends[idx];
        hotPos[0] = end[0];
        hotPos[1] = end[1];
        hotPos[2] = end[2];
        hotPos[3] = node.pos[0];
        hotPos[4] = node.pos[1];
        hotPos[5] = node.pos[2];
        hotLine.current.geometry.attributes.position.needsUpdate = true;
        hotLine.current.material.color.set(node.color);
      }
    }
  });

  const pick = (i) => {
    engine.current.factor = TWIN_NODES[i].factor;
    engine.current.cursor = "INSPECT";
    window.dispatchEvent(new CustomEvent("cine-factor", { detail: TWIN_NODES[i].factor }));
  };
  const clear = () => {
    if (engine.current.analyze > 0.04) return;
    engine.current.factor = -1;
    engine.current.cursor = "";
    window.dispatchEvent(new CustomEvent("cine-factor", { detail: -1 }));
  };

  return (
    <group position={[1.38, 0, 0.08]}>
      {TWIN_NODES.map((node, i) => (
        <group
          key={node.key}
          ref={(el) => {
            nodes.current[i] = el;
          }}
          position={node.pos}
          rotation={node.rot}
          onPointerOver={(e) => {
            e.stopPropagation();
            pick(i);
          }}
          onPointerOut={(e) => {
            e.stopPropagation();
            clear();
          }}
        >
          <NodePanel
            node={node}
            textRef={(el) => {
              labels.current[i] = el;
            }}
          />
        </group>
      ))}
      <lineSegments ref={lines} geometry={geom} renderOrder={1}>
        <lineBasicMaterial color="#67E8F9" transparent opacity={0.14} depthWrite={false} />
      </lineSegments>
      <lineSegments ref={hotLine} geometry={hotGeom} visible={false} renderOrder={1}>
        <lineBasicMaterial color="#F87171" transparent opacity={0.75} depthWrite={false} />
      </lineSegments>
    </group>
  );
}
