import { useMemo } from "react";
import * as THREE from "three";

export default function Chamber() {
  const pylons = useMemo(() => {
    const z = [];
    for (let i = 0; i <= 8; i += 1) z.push(2 - i * 7.2);
    return z;
  }, []);

  return (
    <group>
      <mesh position={[0, 4.6, -18]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[48, 72]} />
        <meshStandardMaterial color="#05070E" roughness={0.92} metalness={0.08} />
      </mesh>
      <mesh position={[0, 2.4, -54]}>
        <planeGeometry args={[36, 10]} />
        <meshStandardMaterial color="#03050A" roughness={1} />
      </mesh>
      {pylons.map((z) => (
        <group key={z} position={[0, 0, z]}>
          <mesh position={[-6.4, 2.05, 0]} castShadow>
            <boxGeometry args={[0.14, 4.1, 0.14]} />
            <meshStandardMaterial color="#0A1524" emissive="#0E7490" emissiveIntensity={0.35} metalness={0.4} roughness={0.35} />
          </mesh>
          <mesh position={[6.4, 2.05, 0]} castShadow>
            <boxGeometry args={[0.14, 4.1, 0.14]} />
            <meshStandardMaterial color="#0A1524" emissive="#0E7490" emissiveIntensity={0.35} metalness={0.4} roughness={0.35} />
          </mesh>
          <mesh position={[-6.4, 4.12, 0]} rotation={[0, 0, Math.PI / 2]}>
            <boxGeometry args={[0.06, 1.1, 0.06]} />
            <meshBasicMaterial color="#22D3EE" transparent opacity={0.45} />
          </mesh>
          <mesh position={[6.4, 4.12, 0]} rotation={[0, 0, Math.PI / 2]}>
            <boxGeometry args={[0.06, 1.1, 0.06]} />
            <meshBasicMaterial color="#22D3EE" transparent opacity={0.45} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 0.01, -18]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[8.2, 8.35, 64]} />
        <meshBasicMaterial color="#155E75" transparent opacity={0.35} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}
