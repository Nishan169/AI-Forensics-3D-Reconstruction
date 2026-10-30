import { useMemo, useRef } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import VehicleEntity from "./VehicleEntity";
import RoadEnvironment from "./RoadEnvironment";

function SkidMarkMesh({ skid }) {
  const lineObj = useMemo(() => {
    if (!skid || !skid.from || !skid.to) return null;
    const fromV = new THREE.Vector3(skid.from[0] || 0, 0.015, skid.from[1] || 0);
    const toV = new THREE.Vector3(skid.to[0] || 0, 0.015, skid.to[1] || 0);
    const geom = new THREE.BufferGeometry().setFromPoints([fromV, toV]);
    const mat = new THREE.LineBasicMaterial({ color: 0x09090b, linewidth: 4, transparent: true, opacity: 0.85 });
    return new THREE.Line(geom, mat);
  }, [skid]);

  return lineObj ? <primitive object={lineObj} /> : null;
}

function CrashShockwave({ impact, currentTime }) {
  const meshRef = useRef();
  if (!impact || !impact.t) return null;
  const d = currentTime - impact.t;
  const isVisible = d >= 0 && d < 1.8;

  useFrame(() => {
    if (!meshRef.current) return;
    if (isVisible) {
      const u = d / 1.8;
      meshRef.current.visible = true;
      meshRef.current.scale.setScalar(1 + 5.5 * u);
      meshRef.current.material.opacity = Math.max(0, 1 - u);
    } else {
      meshRef.current.visible = false;
    }
  });

  const validPos = impact.pos && impact.pos.length >= 3 ? impact.pos : [0, 0, 0];

  return (
    <group position={validPos}>
      <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} visible={isVisible}>
        <ringGeometry args={[0.35, 0.65, 48]} />
        <meshBasicMaterial color="#ef4444" transparent opacity={1} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {d >= 0 && d < 2.5 && (
        <Html position={[0, 1.2, 0]} center distanceFactor={16}>
          <div
            style={{
              padding: "3px 8px",
              borderRadius: "4px",
              background: "rgba(220, 38, 38, 0.92)",
              border: "1px solid #f87171",
              color: "#ffffff",
              fontSize: "10px",
              fontWeight: "800",
              fontFamily: "monospace",
              whiteSpace: "nowrap",
              boxShadow: "0 2px 8px rgba(0,0,0,0.5)"
            }}
          >
            💥 IMPACT: {impact.energyDissipatedKJ ? `${impact.energyDissipatedKJ} kJ DISSIPATED` : "COLLISION"}
          </div>
        </Html>
      )}
    </group>
  );
}

function DebrisField({ items = [], currentTime = 0, impactTime = 3.5 }) {
  if (currentTime < impactTime) return null;
  return (
    <group>
      {items.map((item, idx) => {
        if (!item || !item.pos) return null;
        const isGlass = item.type === "glass_shatter";
        return (
          <mesh key={idx} position={item.pos} rotation={[0, idx * 0.4, 0]}>
            <boxGeometry args={[isGlass ? 0.06 : 0.14, 0.01, isGlass ? 0.06 : 0.08]} />
            <meshStandardMaterial
              color={isGlass ? 0x93c5fd : 0x334155}
              roughness={isGlass ? 0.1 : 0.6}
              metalness={isGlass ? 0.9 : 0.3}
              transparent={isGlass}
              opacity={isGlass ? 0.75 : 1.0}
            />
          </mesh>
        );
      })}
    </group>
  );
}

export default function AccidentSimulation({
  plan,
  currentTime = 0,
  cameraMode = "orbit",
  controlsRef,
  showRoutes = true,
  showLabels = true
}) {
  const { camera } = useThree();
  
  const v1 = plan?.vehicles?.[0];
  const v2 = plan?.vehicles?.[1];

  const getVehiclePos = (vehId) => {
    const trk = plan?.tracks?.[vehId];
    if (!trk || trk.length === 0) return null;
    let i = 0;
    while (i + 1 < trk.length && trk[i + 1].t0 <= currentTime) i++;
    const s = trk[i];
    if (!s || !s.from || !s.to) return null;
    const u = Math.min(1, Math.max(0, (currentTime - s.t0) / Math.max(1e-5, s.t1 - s.t0)));
    return {
      x: s.from[0] + (s.to[0] - s.from[0]) * u,
      z: s.from[1] + (s.to[1] - s.from[1]) * u,
      yaw: s.yaw || 0
    };
  };

  useFrame(() => {
    if (!controlsRef?.current) return;
    const controls = controlsRef.current;
    const p1 = v1 ? getVehiclePos(v1.id) : null;
    const p2 = v2 ? getVehiclePos(v2.id) : null;

    if (cameraMode === "follow_v1" && p1) {
      camera.position.lerp(new THREE.Vector3(p1.x - Math.sin(p1.yaw) * 8.5, 3.8, p1.z - Math.cos(p1.yaw) * 8.5), 0.12);
      controls.target.lerp(new THREE.Vector3(p1.x, 1.2, p1.z), 0.15);
    } else if (cameraMode === "follow_v2" && p2) {
      camera.position.lerp(new THREE.Vector3(p2.x - Math.sin(p2.yaw) * 8.5, 3.8, p2.z - Math.cos(p2.yaw) * 8.5), 0.12);
      controls.target.lerp(new THREE.Vector3(p2.x, 1.2, p2.z), 0.15);
    } else if (cameraMode === "top_down_cctv") {
      const poi = (plan && plan.poi && plan.poi.length >= 3) ? plan.poi : [0, 0, 0];
      camera.position.lerp(new THREE.Vector3(poi[0], 28.0, poi[2] + 0.1), 0.08);
      controls.target.lerp(new THREE.Vector3(poi[0], 0, poi[2]), 0.1);
    }
  });

  if (!plan || !plan.vehicles) return null;

  return (
    <group>
      {/* 1. Procedural Roads, Lanes & Rail Tracks */}
      <RoadEnvironment
        environmentType={plan.environmentType}
        trainAxis={plan.trainAxis || "X"}
      />

      {/* 2. Vehicles */}
      {plan.vehicles.map((veh) => {
        if (!veh || !veh.id) return null;
        return (
          <VehicleEntity
            key={veh.id}
            vehicle={veh}
            tracks={plan.tracks?.[veh.id] || []}
            currentTime={currentTime}
            showLabel={showLabels}
          />
        );
      })}

      {/* 3. Skid Marks */}
      {(plan.skidMarks || []).map((skid, idx) => (
        <SkidMarkMesh key={`skid_${idx}`} skid={skid} />
      ))}

      {/* 4. Debris Field */}
      <DebrisField 
        items={plan.debrisField || []} 
        currentTime={currentTime} 
        impactTime={plan.impactTime || 3.5} 
      />

      {/* 5. Impact Shockwaves */}
      {(plan.impacts || []).map((im, idx) => (
        <CrashShockwave key={`impact_${idx}`} impact={im} currentTime={currentTime} />
      ))}
    </group>
  );
}