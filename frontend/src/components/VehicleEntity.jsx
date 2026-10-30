import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { Html } from "@react-three/drei";

const lerp = (a, b, u) => a + (b - a) * u;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

function createWheel(radius = 0.34, width = 0.22) {
  const g = new THREE.Group();
  const tire = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, width, 24),
    new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.85 })
  );
  tire.rotation.z = Math.PI / 2;
  tire.castShadow = true;
  g.add(tire);

  const rim = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.62, radius * 0.62, width * 1.02, 16),
    new THREE.MeshStandardMaterial({ color: 0xd4d4d8, roughness: 0.25, metalness: 0.85 })
  );
  rim.rotation.z = Math.PI / 2;
  g.add(rim);

  return g;
}

function buildVehicleGeometry(type, colorHex) {
  const root = new THREE.Group();
  const mainMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(colorHex), roughness: 0.35, metalness: 0.45 });
  const darkCabMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });
  const glassMat = new THREE.MeshPhysicalMaterial({ color: 0x0f172a, roughness: 0.1, transmission: 0.85, transparent: true, opacity: 0.85 });
  const undercarriageMat = new THREE.MeshStandardMaterial({ color: 0x09090b, roughness: 0.9 });
  const chromeMat = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, metalness: 0.95, roughness: 0.1 });
  const lightRedMat = new THREE.MeshStandardMaterial({ color: 0xdc2626, emissive: 0x991b1b });
  const lightWhiteMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff });

  const wheels = [];
  let wheelRadius = 0.34;
  let wheelWidth = 0.22;
  let limbs = null;

  // ── 1. PEDESTRIAN (HUMANOID DUMMY) ──
  if (type === "pedestrian") {
    wheelRadius = 0.05;
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xf5d0b0, roughness: 0.6 });
    const clothesMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(colorHex), roughness: 0.7 });
    const pantsMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.8 });

    const torso = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.60, 0.25), clothesMat);
    torso.position.y = 1.15;
    torso.castShadow = true;
    root.add(torso);

    const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 16), skinMat);
    head.position.y = 1.62;
    head.castShadow = true;
    root.add(head);

    const leftArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.55, 0.12), clothesMat);
    leftArm.position.set(-0.28, 1.15, 0);
    root.add(leftArm);

    const rightArm = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.55, 0.12), clothesMat);
    rightArm.position.set(0.28, 1.15, 0);
    root.add(rightArm);

    const leftLeg = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.70, 0.16), pantsMat);
    leftLeg.position.set(-0.12, 0.50, 0);
    leftLeg.castShadow = true;
    root.add(leftLeg);

    const rightLeg = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.70, 0.16), pantsMat);
    rightLeg.position.set(0.12, 0.50, 0);
    rightLeg.castShadow = true;
    root.add(rightLeg);

    limbs = { leftArm, rightArm, leftLeg, rightLeg, torso, head };

  // ── 2. 18-WHEELER SEMI TRUCK (CAB + TANDEM TRAILER) ──
  } else if (type === "semi_trailer") {
    wheelRadius = 0.52;
    wheelWidth = 0.28;

    const cab = new THREE.Mesh(new THREE.BoxGeometry(2.55, 3.2, 3.6), mainMat);
    cab.position.set(0, 2.1, -4.5);
    cab.castShadow = true;
    root.add(cab);

    const hood = new THREE.Mesh(new THREE.BoxGeometry(2.35, 1.6, 2.2), mainMat);
    hood.position.set(0, 1.5, -7.0);
    hood.castShadow = true;
    root.add(hood);

    const grille = new THREE.Mesh(new THREE.BoxGeometry(2.1, 1.4, 0.1), chromeMat);
    grille.position.set(0, 1.5, -8.12);
    root.add(grille);

    [-1.25, 1.25].forEach((xPos) => {
      const stack = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 3.4, 12), chromeMat);
      stack.position.set(xPos, 3.2, -3.1);
      root.add(stack);
    });

    const trailer = new THREE.Mesh(
      new THREE.BoxGeometry(2.65, 3.8, 11.5),
      new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.4 })
    );
    trailer.position.set(0, 2.6, 2.8);
    trailer.castShadow = true;
    root.add(trailer);

    [-1.2, 1.2].forEach((xPos) => {
      const w = createWheel(wheelRadius, wheelWidth);
      w.position.set(xPos, wheelRadius, -6.8);
      root.add(w);
      wheels.push({ mesh: w, isFront: true });
    });

    [-4.5, -3.1].forEach((zPos) => {
      [-1.2, 1.2].forEach((xPos) => {
        const w = createWheel(wheelRadius, wheelWidth);
        w.position.set(xPos, wheelRadius, zPos);
        root.add(w);
        wheels.push({ mesh: w, isFront: false });
      });
    });

    [6.2, 7.6].forEach((zPos) => {
      [-1.25, 1.25].forEach((xPos) => {
        const w = createWheel(wheelRadius, wheelWidth);
        w.position.set(xPos, wheelRadius, zPos);
        root.add(w);
        wheels.push({ mesh: w, isFront: false });
      });
    });

  // ── 3. DIESEL-ELECTRIC FREIGHT LOCOMOTIVE (FIXED PROPORTIONS, NO PILLAR) ──
  } else if (type === "train") {
    wheelRadius = 0.52;
    wheelWidth = 0.20;

    // Main long engine hood
    const longHood = new THREE.Mesh(new THREE.BoxGeometry(2.9, 2.8, 13.0), mainMat);
    longHood.position.set(0, 2.2, 2.2);
    longHood.castShadow = true;
    root.add(longHood);

    // Engineer Cab
    const cab = new THREE.Mesh(new THREE.BoxGeometry(3.05, 3.2, 3.8), mainMat);
    cab.position.set(0, 2.4, -4.8);
    cab.castShadow = true;
    root.add(cab);

    // FIX FOR BUG 2: Cylinder rotated on X (Math.PI / 2) to lay flat along the Z-axis as a roof
    const roof = new THREE.Mesh(
      new THREE.CylinderGeometry(1.45, 1.45, 17.5, 16, 1, false, 0, Math.PI),
      mainMat
    );
    roof.rotation.x = Math.PI / 2; // Flat along train's length
    roof.position.set(0, 3.60, 0);
    root.add(roof);

    // Short Front Hood Nose
    const shortHood = new THREE.Mesh(new THREE.BoxGeometry(2.8, 2.0, 2.4), mainMat);
    shortHood.position.set(0, 1.8, -7.8);
    shortHood.castShadow = true;
    root.add(shortHood);

    // Cab Windshield Glass
    const windshield = new THREE.Mesh(new THREE.BoxGeometry(2.7, 1.1, 0.1), glassMat);
    windshield.position.set(0, 3.1, -6.71);
    root.add(windshield);

    // Realistic small chimney vent (0.35m height)
    const exhaustVent = new THREE.Mesh(
      new THREE.CylinderGeometry(0.18, 0.20, 0.35, 16),
      darkCabMat
    );
    exhaustVent.position.set(0, 3.75, -2.2);
    root.add(exhaustVent);

    // Rooftop Radiator Fans
    [-0.55, 0.55].forEach((xPos) => {
      const fan = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.08, 16), darkCabMat);
      fan.position.set(xPos, 3.65, 4.2);
      root.add(fan);
    });

    // Front Headlight
    const headlight = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.12, 16), lightWhiteMat);
    headlight.rotation.x = Math.PI / 2;
    headlight.position.set(0, 2.4, -9.02);
    root.add(headlight);

    // Cowcatcher Plow
    const cowcatcher = new THREE.Mesh(new THREE.ConeGeometry(1.6, 1.8, 4), undercarriageMat);
    cowcatcher.rotation.x = Math.PI / 2;
    cowcatcher.position.set(0, 0.85, -9.4);
    root.add(cowcatcher);

    // 6-Axle Steel Bogie Wheelsets
    [-7.2, -5.4, -3.6, 2.8, 4.6, 6.4].forEach((zPos) => {
      [-1.38, 1.38].forEach((xPos) => {
        const w = createWheel(wheelRadius, wheelWidth);
        w.position.set(xPos, wheelRadius, zPos);
        root.add(w);
        wheels.push({ mesh: w, isFront: false });
      });
    });

  // ── 4. TRANSIT BUS ──
  } else if (type === "bus") {
    wheelRadius = 0.48;
    wheelWidth = 0.28;

    const busBody = new THREE.Mesh(new THREE.BoxGeometry(2.6, 3.2, 11.8), mainMat);
    busBody.position.y = 2.1;
    busBody.castShadow = true;
    root.add(busBody);

    const frontGlass = new THREE.Mesh(new THREE.BoxGeometry(2.48, 1.4, 0.1), glassMat);
    frontGlass.position.set(0, 2.4, -5.91);
    root.add(frontGlass);

    [-1.31, 1.31].forEach((xPos) => {
      const sideGlass = new THREE.Mesh(new THREE.BoxGeometry(0.05, 1.1, 9.8), glassMat);
      sideGlass.position.set(xPos, 2.4, 0.4);
      root.add(sideGlass);
    });

    [-4.2, 3.6, 4.9].forEach((zPos, idx) => {
      [-1.25, 1.25].forEach((xPos) => {
        const w = createWheel(wheelRadius, wheelWidth);
        w.position.set(xPos, wheelRadius, zPos);
        root.add(w);
        wheels.push({ mesh: w, isFront: idx === 0 });
      });
    });

  // ── 5. MOTORCYCLE ──
  } else if (type === "motorcycle") {
    wheelRadius = 0.32;
    wheelWidth = 0.14;

    const bikeFrame = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.60, 1.5), mainMat);
    bikeFrame.position.y = 0.65;
    root.add(bikeFrame);

    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.15, 0.6), new THREE.MeshStandardMaterial({ color: 0x18181b }));
    seat.position.set(0, 0.95, 0.1);
    root.add(seat);

    const fork = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.85), chromeMat);
    fork.rotation.x = -0.35;
    fork.position.set(0, 0.70, -0.65);
    root.add(fork);

    const bars = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.05, 0.05), chromeMat);
    bars.position.set(0, 1.05, -0.55);
    root.add(bars);

    [-0.80, 0.80].forEach((zPos, idx) => {
      const w = createWheel(wheelRadius, wheelWidth);
      w.position.set(0, wheelRadius, zPos);
      root.add(w);
      wheels.push({ mesh: w, isFront: idx === 0 });
    });

    const rider = new THREE.Mesh(new THREE.BoxGeometry(0.40, 0.55, 0.25), new THREE.MeshStandardMaterial({ color: 0x1e293b }));
    rider.position.set(0, 1.25, 0.05);
    rider.rotation.x = 0.25;
    root.add(rider);

    const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.18, 14, 14), new THREE.MeshStandardMaterial({ color: 0x0284c7 }));
    helmet.position.set(0, 1.62, -0.05);
    root.add(helmet);

  // ── 6. DELIVERY TRUCK ──
  } else if (type === "truck") {
    wheelRadius = 0.45;
    wheelWidth = 0.25;

    const cabin = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.6, 2.5), mainMat);
    cabin.position.set(0, 1.9, -2.2);
    cabin.castShadow = true;
    root.add(cabin);

    const box = new THREE.Mesh(new THREE.BoxGeometry(2.5, 3.0, 5.2), new THREE.MeshStandardMaterial({ color: 0xe2e8f0 }));
    box.position.set(0, 2.2, 1.8);
    box.castShadow = true;
    root.add(box);

    [-2.2, 2.2, 3.4].forEach((zPos, idx) => {
      [-1.2, 1.2].forEach((xPos) => {
        const w = createWheel(wheelRadius, wheelWidth);
        w.position.set(xPos, wheelRadius, zPos);
        root.add(w);
        wheels.push({ mesh: w, isFront: idx === 0 });
      });
    });

  // ── 7. PASSENGER SEDAN & SUV ──
  } else {
    const isSUV = type === "suv";
    const L = isSUV ? 5.1 : 4.75;
    const W = isSUV ? 2.0 : 1.82;
    const H = isSUV ? 1.75 : 1.42;
    wheelRadius = isSUV ? 0.38 : 0.32;

    const lowerBody = new THREE.Mesh(new THREE.BoxGeometry(W, H * 0.45, L), mainMat);
    lowerBody.position.y = wheelRadius + (H * 0.45) / 2;
    lowerBody.castShadow = true;
    root.add(lowerBody);

    const upperCabin = new THREE.Mesh(new THREE.BoxGeometry(W * 0.88, H * 0.48, L * 0.55), glassMat);
    upperCabin.position.set(0, lowerBody.position.y + (H * 0.45) / 2 + (H * 0.48) / 2, isSUV ? 0.2 : 0.1);
    root.add(upperCabin);

    const roof = new THREE.Mesh(new THREE.BoxGeometry(W * 0.86, 0.06, L * 0.52), mainMat);
    roof.position.set(0, upperCabin.position.y + (H * 0.48) / 2 + 0.03, upperCabin.position.z);
    root.add(roof);

    [-W * 0.38, W * 0.38].forEach((xPos) => {
      const hl = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 0.06), lightWhiteMat);
      hl.position.set(xPos, lowerBody.position.y + 0.08, -L / 2 - 0.02);
      root.add(hl);
    });

    [-W * 0.38, W * 0.38].forEach((xPos) => {
      const bl = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.12, 0.06), lightRedMat);
      bl.position.set(xPos, lowerBody.position.y + 0.08, L / 2 + 0.02);
      root.add(bl);
    });

    [-L * 0.32, L * 0.32].forEach((zPos, idx) => {
      [-W / 2 + 0.08, W / 2 - 0.08].forEach((xPos) => {
        const w = createWheel(wheelRadius, wheelWidth);
        w.position.set(xPos, wheelRadius, zPos);
        root.add(w);
        wheels.push({ mesh: w, isFront: idx === 0 });
      });
    });
  }

  return { root, wheels, wheelRadius, limbs };
}

export default function VehicleEntity({
  vehicle,
  tracks = [],
  currentTime = 0,
  showLabel = true
}) {
  const rootRef = useRef();
  const bodyRef = useRef();
  const labelRef = useRef(null);
  const totalDistRef = useRef(0);
  const prevPosRef = useRef(null);

  const { root: vehicleMesh, wheels, wheelRadius, limbs } = useMemo(() => {
    return buildVehicleGeometry(vehicle.type, vehicle.color || "#2563eb");
  }, [vehicle.type, vehicle.color]);

  const sampleTrack = (t) => {
    if (!tracks || tracks.length === 0) return [null, 0, null];
    let i = 0;
    while (i + 1 < tracks.length && tracks[i + 1].t0 <= t) i++;
    const s = tracks[i];
    if (!s || s.t0 === undefined) return [null, 0, null];
    const u = clamp((t - s.t0) / Math.max(1e-6, s.t1 - s.t0), 0, 1);
    const prev = i > 0 ? tracks[i - 1] : null;
    return [s, u, prev];
  };

  useFrame(() => {
    if (!rootRef.current) return;

    const [s, u, prev] = sampleTrack(currentTime);
    if (!s) {
      rootRef.current.visible = false;
      if (labelRef.current) labelRef.current.style.display = "none";
      return;
    }

    rootRef.current.visible = true;
    if (labelRef.current) labelRef.current.style.display = "block";

    const posX = lerp(s.from[0], s.to[0], u);
    const posZ = lerp(s.from[1], s.to[1], u);
    const posY = lerp(s.from_y ?? 0.02, s.to_y ?? 0.02, u);

    rootRef.current.position.set(posX, Math.max(0.02, posY), posZ);

    if (prevPosRef.current) {
      const stepDist = Math.hypot(posX - prevPosRef.current.x, posZ - prevPosRef.current.z);
      totalDistRef.current += stepDist;
    }
    prevPosRef.current = { x: posX, z: posZ };

    // Pedestrian animated walking vs ragdoll throw
    if (vehicle.type === "pedestrian" && limbs) {
      if (s.kind === "walk") {
        const ph = totalDistRef.current * 4.0;
        limbs.leftLeg.rotation.x = Math.sin(ph) * 0.6;
        limbs.rightLeg.rotation.x = -Math.sin(ph) * 0.6;
        limbs.leftArm.rotation.x = -Math.sin(ph) * 0.5;
        limbs.rightArm.rotation.x = Math.sin(ph) * 0.5;
        limbs.torso.rotation.x = 0;
      } else if (s.kind === "pedestrian_thrown") {
        const throwRot = Math.min(Math.PI / 2, u * (Math.PI / 2));
        limbs.torso.rotation.x = throwRot;
        rootRef.current.position.y = Math.max(0.1, 0.8 * (1 - u));
      }
    }

    // Wheel roll
    const wheelRot = totalDistRef.current / (wheelRadius || 0.35);
    wheels.forEach(({ mesh, isFront }) => {
      mesh.children[0].rotation.x = -wheelRot;
      mesh.children[1].rotation.x = -wheelRot;
      if (isFront && s.kind === "skid") {
        mesh.rotation.y = -0.25;
      } else if (isFront) {
        mesh.rotation.y = 0;
      }
    });

    // Orientation: Yaw, Pitch, Roll
    let yaw = s.yaw;
    if (prev && s.kind !== "post_collision_spin") {
      const w = clamp((u * (s.t1 - s.t0)) / 0.25, 0, 1);
      const k = w * w * (3 - 2 * w);
      let d = s.yaw - prev.yaw;
      d -= 2 * Math.PI * Math.round(d / (2 * Math.PI));
      yaw = prev.yaw + d * k;
    }
    rootRef.current.rotation.y = yaw;

    if (bodyRef.current) {
      bodyRef.current.rotation.x = s.pitch || 0;
      bodyRef.current.rotation.z = s.roll || 0;

      if (s.damageState === "crumpled") {
        bodyRef.current.scale.set(0.90, 0.88, 0.82);
      } else {
        bodyRef.current.scale.set(1, 1, 1);
      }
    }
  });

  const [currentSeg] = sampleTrack(currentTime);
  const currentSpeed = currentSeg?.speedKmh || 0;

  return (
    <group ref={rootRef}>
      <group ref={bodyRef}>
        <primitive object={vehicleMesh} />
      </group>

      {showLabel && (
        <Html position={[0, (vehicle.height || 1.6) + 0.65, 0]} center distanceFactor={22}>
          <div
            ref={labelRef}
            style={{
              padding: "3px 8px",
              borderRadius: "5px",
              background: "rgba(15, 23, 42, 0.92)",
              border: `1.5px solid ${vehicle.color || "#38bdf8"}`,
              color: "#f8fafc",
              fontSize: "11px",
              fontWeight: "700",
              fontFamily: "monospace",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              boxShadow: "0 4px 12px rgba(0,0,0,0.6)",
              display: "flex",
              alignItems: "center",
              gap: "6px"
            }}
          >
            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: vehicle.color || "#38bdf8" }} />
            <span>{vehicle.name || vehicle.label}</span>
            <span
              style={{
                background: currentSpeed > 0 ? "rgba(239, 68, 68, 0.25)" : "rgba(100, 116, 139, 0.25)",
                color: currentSpeed > 0 ? "#f87171" : "#94a3b8",
                padding: "1px 5px",
                borderRadius: "3px",
                border: "1px solid rgba(255,255,255,0.15)"
              }}
            >
              {currentSpeed} km/h
            </span>
          </div>
        </Html>
      )}
    </group>
  );
}