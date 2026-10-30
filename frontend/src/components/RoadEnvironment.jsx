import { useMemo } from "react";
import * as THREE from "three";

/**
 * Procedural Road Intersection & Railway Track Environment
 */
export default function RoadEnvironment({
  environmentType = "road_intersection",
  trainAxis = "X",
  roadWidth = 9.0,
  extent = 50.0
}) {
  // Fix: Show tracks for ANY rail scenario (level-crossing, multi-train, or solo derailment)
  const isRailScenario = environmentType === "rail_crossing" || environmentType === "rail_corridor" || environmentType.includes("rail");
  const isPureRail = environmentType === "rail_corridor" || environmentType === "derailment";

  const railwayTies = useMemo(() => {
    if (!isRailScenario) return [];
    const ties = [];
    const tieSpacing = 0.65;
    const count = Math.floor(extent / tieSpacing);

    for (let i = -count; i <= count; i++) {
      const coord = i * tieSpacing;
      ties.push({
        pos: trainAxis === "X" ? [coord, 0.04, 0] : [0, 0.04, coord],
        rotY: trainAxis === "X" ? 0 : Math.PI / 2
      });
    }
    return ties;
  }, [isRailScenario, trainAxis, extent]);

  return (
    <group position={[0, -0.005, 0]}>
      {/* ── 1. ASPHALT ROADS (East-West only shown if not a rail track along X) ── */}
      {!isRailScenario && (
        <>
          <mesh receiveShadow position={[0, 0.005, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[extent * 2, roadWidth]} />
            <meshStandardMaterial color="#18181b" roughness={0.92} />
          </mesh>
          {[-extent, 0].map((baseX, idx) => (
            <group key={`ew_lines_${idx}`}>
              {Array.from({ length: 18 }).map((_, i) => {
                const x = (i - 9) * 4.5;
                if (Math.abs(x) < roadWidth / 2 + 1.5) return null;
                return (
                  <mesh key={i} position={[x, 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                    <planeGeometry args={[2.5, 0.18]} />
                    <meshBasicMaterial color="#eab308" />
                  </mesh>
                );
              })}
            </group>
          ))}
        </>
      )}

      {/* North-South Road: Shown on intersections and grade-crossings, hidden for pure rail corridor */}
      {!isPureRail && (
        <>
          <mesh receiveShadow position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[roadWidth, extent * 2]} />
            <meshStandardMaterial color="#18181b" roughness={0.92} />
          </mesh>
          {Array.from({ length: 18 }).map((_, i) => {
            const z = (i - 9) * 4.5;
            if (Math.abs(z) < roadWidth / 2 + 1.5) return null;
            return (
              <mesh key={`ns_lines_${i}`} position={[0, 0.012, z]} rotation={[-Math.PI / 2, 0, Math.PI / 2]}>
                <planeGeometry args={[2.5, 0.18]} />
                <meshBasicMaterial color="#eab308" />
              </mesh>
            );
          })}
          {[-roadWidth / 2 + 0.15, roadWidth / 2 - 0.15].map((offset, i) => (
            <group key={`shoulders_${i}`}>
              {!isRailScenario && (
                <mesh position={[0, 0.011, offset]} rotation={[-Math.PI / 2, 0, 0]}>
                  <planeGeometry args={[extent * 2, 0.15]} />
                  <meshBasicMaterial color="#f8fafc" />
                </mesh>
              )}
              <mesh position={[offset, 0.011, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 2]}>
                <planeGeometry args={[extent * 2, 0.15]} />
                <meshBasicMaterial color="#f8fafc" />
              </mesh>
            </group>
          ))}
        </>
      )}

      {/* Crosswalks: Shown only on road intersections */}
      {!isRailScenario && [-roadWidth / 2 - 1.2, roadWidth / 2 + 1.2].map((zPos, sIdx) => (
        <group key={`crosswalk_ew_${sIdx}`}>
          {Array.from({ length: 7 }).map((_, barIdx) => (
            <mesh
              key={barIdx}
              position={[(barIdx - 3) * 1.15, 0.014, zPos]}
              rotation={[-Math.PI / 2, 0, 0]}
            >
              <planeGeometry args={[0.55, 1.8]} />
              <meshBasicMaterial color="#ffffff" />
            </mesh>
          ))}
        </group>
      ))}

      {/* ── 2. RAILWAY TRACKS & GRAVEL BALLAST BED ── */}
      {isRailScenario && (
        <group>
          <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={trainAxis === "X" ? [extent * 2, 4.2] : [4.2, extent * 2]} />
            <meshStandardMaterial color="#475569" roughness={0.98} />
          </mesh>

          {railwayTies.map((tie, idx) => (
            <mesh key={idx} position={tie.pos} rotation={[0, tie.rotY, 0]} castShadow>
              <boxGeometry args={[0.24, 0.14, 2.7]} />
              <meshStandardMaterial color="#451a03" roughness={0.8} />
            </mesh>
          ))}

          {[-0.717, 0.717].map((offset, idx) => (
            <group key={`rail_${idx}`}>
              <mesh
                position={trainAxis === "X" ? [0, 0.16, offset] : [offset, 0.16, 0]}
                rotation={trainAxis === "X" ? [0, 0, Math.PI / 2] : [Math.PI / 2, 0, 0]}
                castShadow
              >
                <cylinderGeometry args={[0.045, 0.045, extent * 2, 12]} />
                <meshStandardMaterial color="#94a3b8" metalness={0.92} roughness={0.15} />
              </mesh>
            </group>
          ))}
        </group>
      )}
    </group>
  );
}