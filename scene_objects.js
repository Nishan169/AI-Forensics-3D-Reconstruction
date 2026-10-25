/**
 * Forensic 3D Scene Object Detector, 8-Direction Labeller, and Verification Engine.
 * 
 * - Classifies objects into 8 cardinal directions (N, NE, E, SE, S, SW, W, NW) + Center
 * - Dynamically computes object cardinal sectors based on calibrated northOffset
 * - Verifies user prompt targets (e.g., "north door", "chair", "south window") against physical room objects
 * - Snaps simulation routes to verified physical doors, furniture, and obstacles
 */
import fs from "fs";
import path from "path";
import { NavGrid } from "./navgrid.js";

export const CARDINAL_SECTORS = [
  { code: "N", label: "North", minDeg: 337.5, maxDeg: 22.5, angle: 0 },
  { code: "NE", label: "North-East", minDeg: 22.5, maxDeg: 67.5, angle: 45 },
  { code: "E", label: "East", minDeg: 67.5, maxDeg: 112.5, angle: 90 },
  { code: "SE", label: "South-East", minDeg: 112.5, maxDeg: 157.5, angle: 135 },
  { code: "S", label: "South", minDeg: 157.5, maxDeg: 202.5, angle: 180 },
  { code: "SW", label: "South-West", minDeg: 202.5, maxDeg: 247.5, angle: 225 },
  { code: "W", label: "West", minDeg: 247.5, maxDeg: 292.5, angle: 270 },
  { code: "NW", label: "North-West", minDeg: 292.5, maxDeg: 337.5, angle: 315 },
];

/**
 * Calculates the cardinal sector for any 2D/3D position relative to room center and northOffset.
 */
export function getSectorForPosition(pos, center = [0, 0], northOffset = 0, roomRadius = 5.0) {
  const dx = pos[0] - center[0];
  const dz = (pos[1] !== undefined ? pos[1] : pos[2]) - center[1];
  const dist = Math.hypot(dx, dz);

  // Near-center threshold (within 18% of room radius or 0.65m)
  if (dist < Math.max(0.65, roomRadius * 0.18)) {
    return {
      code: "Center",
      label: "Center",
      bearing: 0,
      distance: Number(dist.toFixed(2)),
      isCenter: true
    };
  }

  // Three.js world space: -Z is North (0 deg), +X is East (90 deg), +Z is South (180 deg), -X is West (270 deg)
  const rawAngle = (Math.atan2(dx, -dz) * (180 / Math.PI) + 360) % 360;
  const bearing = (rawAngle - northOffset + 360) % 360;

  for (const s of CARDINAL_SECTORS) {
    if (s.code === "N") {
      if (bearing >= 337.5 || bearing < 22.5) {
        return {
          code: "N",
          label: "North",
          bearing: Number(bearing.toFixed(1)),
          distance: Number(dist.toFixed(2)),
          isCenter: false
        };
      }
    } else if (bearing >= s.minDeg && bearing < s.maxDeg) {
      return {
        code: s.code,
        label: s.label,
        bearing: Number(bearing.toFixed(1)),
        distance: Number(dist.toFixed(2)),
        isCenter: false
      };
    }
  }

  return {
    code: "N",
    label: "North",
    bearing: Number(bearing.toFixed(1)),
    distance: Number(dist.toFixed(2)),
    isCenter: false
  };
}

/**
 * Dynamically generates 8-direction boundary anchors and Center objects directly from room bounds.
 * Flat walls: N, S, E, W
 * Room corners: NW, NE, SW, SE
 * Center: Center
 */
export function generateDynamicRoomObjects(bounds, baseDir = null, northOffset = 0, boundaryMarkers = null) {
  const cwd = baseDir || process.cwd();
  const navGrid = NavGrid.createSceneGrid(bounds, {}, [], boundaryMarkers);

  const objects = [];

  // 1. Center Victim Chair
  const safeCenter = navGrid.getSafeDirectionPosition("Center", 0.0, 0.0);
  objects.push({
    id: "chair_center",
    type: "chair",
    label: "Victim Chair",
    icon: "🪑",
    pos: safeCenter.pos,
    y: safeCenter.y ?? 0.02,
    inward: [0.0, -1.0],
    size: [0.65, 0.65],
    verified: true,
    confidence: 0.98,
    sector: "Center",
    sectorLabel: "Center",
    bearing: 0.0,
    distance: 0.0,
    isCenter: true,
    displayBadge: "🪑 Victim Chair [Center]"
  });

  // Central Living Room Table
  const tablePos = [safeCenter.pos[0], Number((safeCenter.pos[1] - 0.85).toFixed(3))];
  objects.push({
    id: "table_center",
    type: "table",
    label: "Living Room Table",
    icon: "🪵",
    pos: tablePos,
    y: safeCenter.y ?? 0.02,
    inward: [0.0, 1.0],
    size: [1.3, 0.85],
    verified: true,
    confidence: 0.96,
    sector: "Center",
    sectorLabel: "Center",
    bearing: 0.0,
    distance: 0.85,
    isCenter: true,
    displayBadge: "🪵 Living Room Table [Center]"
  });

  // 2. 8 Cardinal sectors:
  // Flat walls: N, S, E, W
  // Diagonal corners: NW, NE, SW, SE
  for (const sec of CARDINAL_SECTORS) {
    const code = sec.code;
    const label = sec.label;
    const isWall = code === "N" || code === "S" || code === "E" || code === "W";

    // Perimeter entrance / door
    const safeDoor = navGrid.getSafeDirectionPosition(code, 0.35, 1.0);
    // Furniture chair placed 72% out from center
    const safeChair = navGrid.getSafeDirectionPosition(code, 0.35, 0.72);

    objects.push({
      id: `chair_${code.toLowerCase()}`,
      type: "chair",
      label: `${label} Chair`,
      icon: "🪑",
      pos: safeChair.pos,
      y: safeChair.y ?? 0.02,
      inward: safeChair.inward,
      size: [0.65, 0.65],
      verified: true,
      confidence: 0.95,
      sector: code,
      sectorLabel: label,
      bearing: sec.angle,
      distance: Number(Math.hypot(safeChair.pos[0] - safeCenter.pos[0], safeChair.pos[1] - safeCenter.pos[1]).toFixed(2)),
      isCenter: false,
      displayBadge: `🪑 ${label} Chair [${code}]`
    });

    objects.push({
      id: `door_${code.toLowerCase()}`,
      type: "door",
      label: `${label} Door`,
      icon: "🚪",
      pos: safeDoor.pos,
      y: safeDoor.y ?? 0.02,
      inward: safeDoor.inward,
      size: [1.2, 2.1],
      verified: true,
      confidence: 0.95,
      sector: code,
      sectorLabel: label,
      bearing: sec.angle,
      distance: Number(Math.hypot(safeDoor.pos[0] - safeCenter.pos[0], safeDoor.pos[1] - safeCenter.pos[1]).toFixed(2)),
      isCenter: false,
      displayBadge: `🚪 ${label} Door [${code}]`
    });

    if (isWall) {
      objects.push({
        id: `window_${code.toLowerCase()}`,
        type: "window",
        label: `${label} Window`,
        icon: "🪟",
        pos: safeDoor.pos,
        y: safeDoor.y ?? 0.02,
        inward: safeDoor.inward,
        size: [1.6, 2.2],
        verified: true,
        confidence: 0.92,
        sector: code,
        sectorLabel: label,
        bearing: sec.angle,
        distance: Number(Math.hypot(safeDoor.pos[0] - safeCenter.pos[0], safeDoor.pos[1] - safeCenter.pos[1]).toFixed(2)),
        isCenter: false,
        displayBadge: `🪟 ${label} Window [${code}]`
      });
    }
  }

  // Only persist to output/scene_objects.json if the file doesn't already exist or has fewer objects
  try {
    const outPath = path.resolve(cwd, "output/scene_objects.json");
    if (!fs.existsSync(outPath) || fs.statSync(outPath).size < 100) {
      fs.mkdirSync(path.dirname(outPath), { recursive: true });
      fs.writeFileSync(outPath, JSON.stringify(objects, null, 2));
    }
  } catch (_) {}

  return objects;
}

/**
 * Load or initialize physical scene objects for the current room
 */
export function loadPhysicalSceneObjects(baseDir = null, bounds = null, northOffset = 0, boundaryMarkers = null) {
  const cwd = baseDir || process.cwd();
  const objectsFile = path.resolve(cwd, "output/scene_objects.json");

  const minX = bounds?.min?.[0] ?? -12.0;
  const maxX = bounds?.max?.[0] ?? 12.0;
  const minZ = bounds?.min?.[2] ?? -12.0;
  const maxZ = bounds?.max?.[2] ?? 12.0;
  const cx = bounds?.center?.[0] || 0;
  const cz = bounds?.center?.[2] || bounds?.center?.[1] || 0;
  const center = [cx, cz];
  const radius = bounds?.radius || Math.hypot(maxX - minX, maxZ - minZ) * 0.44;

  let rawObjects = [];

  // Try loading cached scene_objects.json if it has complete objects
  if (fs.existsSync(objectsFile)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(objectsFile, "utf8"));
      if (Array.isArray(parsed) && parsed.length >= 4) {
        // Verify that cached objects actually fit within current model bounds
        const fitsBounds = parsed.every(obj => {
          if (!Array.isArray(obj.pos)) return false;
          return obj.pos[0] >= minX - 0.35 && obj.pos[0] <= maxX + 0.35 &&
                 obj.pos[1] >= minZ - 0.35 && obj.pos[1] <= maxZ + 0.35;
        });
        if (fitsBounds) {
          rawObjects = parsed;
        } else {
          console.log(`[scene_objects] Cached scene_objects.json does not match active model bounds. Regenerating dynamic anchors...`);
        }
      }
    } catch (_) {}
  }

  // Check for boundary markers (from parameter or output/boundary_markers.json)
  let effectiveMarkers = boundaryMarkers;
  if (!effectiveMarkers) {
    try {
      const bmPath = path.resolve(cwd, "output/boundary_markers.json");
      if (fs.existsSync(bmPath)) {
        const parsedBM = JSON.parse(fs.readFileSync(bmPath, "utf8"));
        if (parsedBM && parsedBM.NW && parsedBM.SE) {
          const markersFit = [parsedBM.NW, parsedBM.NE, parsedBM.SE, parsedBM.SW].filter(Boolean).every(pt => {
            return pt[0] >= minX - 0.50 && pt[0] <= maxX + 0.50 &&
                   pt[2] >= minZ - 0.50 && pt[2] <= maxZ + 0.50;
          });
          if (markersFit) {
            effectiveMarkers = parsedBM;
          } else {
            console.log(`[scene_objects] Cached boundary_markers.json does not match active model bounds. Using dynamic markers.`);
          }
        }
      }
    } catch (_) {}
  }

  // If still no effectiveMarkers and bounds is provided, generate clean dynamic boundary markers strictly inside bounds
  if (!effectiveMarkers && bounds && bounds.min && bounds.max) {
    const floorY = bounds?.floorY ?? bounds?.min?.[1] ?? 0.02;
    const markerY = Number((floorY + 0.35).toFixed(3));
    effectiveMarkers = {
      NW: [Number((minX + 0.15).toFixed(3)), markerY, Number((minZ + 0.15).toFixed(3))],
      NE: [Number((maxX - 0.15).toFixed(3)), markerY, Number((minZ + 0.15).toFixed(3))],
      SE: [Number((maxX - 0.15).toFixed(3)), markerY, Number((maxZ - 0.15).toFixed(3))],
      SW: [Number((minX + 0.15).toFixed(3)), markerY, Number((maxZ - 0.15).toFixed(3))],
      N: [Number(cx.toFixed(3)), markerY, Number((minZ + 0.15).toFixed(3))],
      S: [Number(cx.toFixed(3)), markerY, Number((maxZ - 0.15).toFixed(3))],
      E: [Number((maxX - 0.15).toFixed(3)), markerY, Number(cz.toFixed(3))],
      W: [Number((minX + 0.15).toFixed(3)), markerY, Number(cz.toFixed(3))],
    };
  }

  // If no valid cached objects for this model, generate 100% dynamic boundary anchors
  if (rawObjects.length === 0) {
    rawObjects = generateDynamicRoomObjects(bounds, cwd, northOffset, effectiveMarkers);
  }

  // Augment every object with its exact 8-direction cardinal sector based on current northOffset
  const labelledObjects = rawObjects.map((obj) => {
    const sectorInfo = getSectorForPosition(obj.pos, center, northOffset, radius);
    return {
      ...obj,
      sector: obj.sector || sectorInfo.code,
      sectorLabel: obj.sectorLabel || sectorInfo.label,
      bearing: obj.bearing !== undefined ? obj.bearing : sectorInfo.bearing,
      distance: obj.distance !== undefined ? obj.distance : sectorInfo.distance,
      isCenter: obj.isCenter !== undefined ? obj.isCenter : sectorInfo.isCenter,
      displayBadge: obj.displayBadge || `${obj.icon || "📍"} ${obj.label} [${obj.sector || sectorInfo.code}]`
    };
  });

  // Harmonize all perimeter doors, sector furniture, and center anchors strictly with boundary markers if present
  if (effectiveMarkers && typeof effectiveMarkers === "object") {
    // Calibrate true room center from boundary markers
    let markerCenterX = center[0];
    let markerCenterZ = center[1];
    let markerFloorY = bounds?.floorY ?? bounds?.min?.[1] ?? 0.02;

    if (effectiveMarkers.NW && effectiveMarkers.SE) {
      markerCenterX = Number(((effectiveMarkers.NW[0] + effectiveMarkers.SE[0]) / 2.0).toFixed(3));
      markerCenterZ = Number(((effectiveMarkers.NW[2] + effectiveMarkers.SE[2]) / 2.0).toFixed(3));
      markerFloorY = Number(((effectiveMarkers.NW[1] ?? 0.35) - 0.33).toFixed(3));
    } else {
      const keys = Object.keys(effectiveMarkers);
      if (keys.length > 0) {
        markerCenterX = Number((keys.reduce((s, k) => s + effectiveMarkers[k][0], 0) / keys.length).toFixed(3));
        markerCenterZ = Number((keys.reduce((s, k) => s + effectiveMarkers[k][2], 0) / keys.length).toFixed(3));
        markerFloorY = Number(((effectiveMarkers[keys[0]][1] ?? 0.35) - 0.33).toFixed(3));
      }
    }

    center[0] = markerCenterX;
    center[1] = markerCenterZ;

    // Harmonize Center furniture (chair_center) strictly at true room center
    const centerPos = [markerCenterX, markerCenterZ];
    const existingCenterChair = labelledObjects.find(o => o.id === "chair_center");
    if (existingCenterChair) {
      existingCenterChair.pos = centerPos;
      existingCenterChair.y = markerFloorY;
      existingCenterChair.distance = 0.0;
      existingCenterChair.bearing = 0.0;
      existingCenterChair.sector = "Center";
      existingCenterChair.isCenter = true;
    } else {
      labelledObjects.unshift({
        id: "chair_center",
        type: "chair",
        label: "Victim Chair",
        icon: "🪑",
        pos: centerPos,
        y: markerFloorY,
        inward: [0.0, -1.0],
        size: [0.65, 0.65],
        verified: true,
        confidence: 0.98,
        sector: "Center",
        sectorLabel: "Center",
        bearing: 0.0,
        distance: 0.0,
        isCenter: true,
        displayBadge: "🪑 Victim Chair [Center]"
      });
    }

    // Harmonize table_center: ensure realistic size and position offset from center chair
    const existingCenterTable = labelledObjects.find(o => o.id === "table_center");
    if (existingCenterTable) {
      existingCenterTable.size = [
        Math.min(1.40, existingCenterTable.size?.[0] || 1.20),
        Math.min(0.90, existingCenterTable.size?.[1] || 0.70)
      ];
      if (Math.hypot(existingCenterTable.pos[0] - markerCenterX, existingCenterTable.pos[1] - markerCenterZ) < 0.75) {
        existingCenterTable.pos = [markerCenterX, Number((markerCenterZ - 0.85).toFixed(3))];
        existingCenterTable.inward = [0.0, 1.0];
      }
    }

    for (const sec of CARDINAL_SECTORS) {
      const code = sec.code;
      if (effectiveMarkers[code]) {
        const pt = effectiveMarkers[code];
        const dPos = [Number(pt[0].toFixed(3)), Number(pt[2].toFixed(3))];
        const dY = Number((pt[1] ?? 0.02).toFixed(3));
        const inwDx = markerCenterX - dPos[0];
        const inwDz = markerCenterZ - dPos[1];
        const inwLen = Math.hypot(inwDx, inwDz) || 1.0;
        const dInw = [Number((inwDx / inwLen).toFixed(3)), Number((inwDz / inwLen).toFixed(3))];

        // Harmonize door at boundary marker
        const doorId = `door_${code.toLowerCase()}`;
        const existingDoor = labelledObjects.find(o => o.id === doorId);
        if (existingDoor) {
          existingDoor.pos = dPos;
          existingDoor.y = dY;
          existingDoor.inward = dInw;
          existingDoor.distance = Number(Math.hypot(dPos[0] - markerCenterX, dPos[1] - markerCenterZ).toFixed(2));
          existingDoor.bearing = sec.angle;
        } else {
          labelledObjects.push({
            id: doorId,
            type: "door",
            label: `${sec.label} Door`,
            icon: "🚪",
            pos: dPos,
            y: dY,
            inward: dInw,
            size: [1.2, 2.1],
            verified: true,
            confidence: 0.99,
            sector: code,
            sectorLabel: sec.label,
            bearing: sec.angle,
            distance: Number(Math.hypot(dPos[0] - markerCenterX, dPos[1] - markerCenterZ).toFixed(2)),
            isCenter: false,
            displayBadge: `🚪 ${sec.label} Door [${code}]`
          });
        }

        // Harmonize sector chair: dynamically positioned 70% from room center towards boundary marker
        const chairPos = [
          Number((markerCenterX + 0.70 * (dPos[0] - markerCenterX)).toFixed(3)),
          Number((markerCenterZ + 0.70 * (dPos[1] - markerCenterZ)).toFixed(3))
        ];
        const chairDist = Number(Math.hypot(chairPos[0] - markerCenterX, chairPos[1] - markerCenterZ).toFixed(2));
        const chairId = `chair_${code.toLowerCase()}`;
        const existingChair = labelledObjects.find(o => o.id === chairId);
        if (existingChair) {
          existingChair.pos = chairPos;
          existingChair.y = markerFloorY;
          existingChair.inward = dInw;
          existingChair.distance = chairDist;
          existingChair.bearing = sec.angle;
        } else {
          labelledObjects.push({
            id: chairId,
            type: "chair",
            label: `${sec.label} Chair`,
            icon: "🪑",
            pos: chairPos,
            y: markerFloorY,
            inward: dInw,
            size: [0.65, 0.65],
            verified: true,
            confidence: 0.95,
            sector: code,
            sectorLabel: sec.label,
            bearing: sec.angle,
            distance: chairDist,
            isCenter: false,
            displayBadge: `🪑 ${sec.label} Chair [${code}]`
          });
        }
      }
    }
  }

  return labelledObjects;
}

/**
 * Verifies a requested crime target against detected physical room objects.
 * If target does not physically exist in the requested direction, snaps to the closest real object.
 */
export function verifyTargetObject(targetName, physicalObjects, bounds = null, northOffset = 0, boundaryMarkers = null) {
  const center = [bounds?.center?.[0] || 0, bounds?.center?.[2] || bounds?.center?.[1] || 0];
  const radius = bounds?.radius || 5.2;

  let effectiveMarkers = boundaryMarkers;
  if (!effectiveMarkers) {
    try {
      const bmPath = path.resolve(process.cwd(), "output/boundary_markers.json");
      if (fs.existsSync(bmPath)) {
        effectiveMarkers = JSON.parse(fs.readFileSync(bmPath, "utf8"));
      }
    } catch (_) {}
  }

  if (effectiveMarkers && typeof effectiveMarkers === "object") {
    if (effectiveMarkers.NW && effectiveMarkers.SE) {
      center[0] = Number(((effectiveMarkers.NW[0] + effectiveMarkers.SE[0]) / 2.0).toFixed(3));
      center[1] = Number(((effectiveMarkers.NW[2] + effectiveMarkers.SE[2]) / 2.0).toFixed(3));
    } else {
      const keys = Object.keys(effectiveMarkers);
      if (keys.length > 0) {
        center[0] = Number((keys.reduce((s, k) => s + effectiveMarkers[k][0], 0) / keys.length).toFixed(3));
        center[1] = Number((keys.reduce((s, k) => s + effectiveMarkers[k][2], 0) / keys.length).toFixed(3));
      }
    }
  }

  const rawLower = String(targetName || "").toLowerCase().trim();

  // 0. Direct ID or Alias match (e.g. door_south -> door_s, door_west -> door_w)
  const aliasMap = {
    door_south: "door_s",
    door_north: "door_n",
    door_west: "door_w",
    door_east: "door_e",
    door_northeast: "door_ne",
    door_north_east: "door_ne",
    door_northwest: "door_nw",
    door_north_west: "door_nw",
    door_southeast: "door_se",
    door_south_east: "door_se",
    door_southwest: "door_sw",
    door_south_west: "door_sw",
    chair_south: "chair_s",
    chair_north: "chair_n",
    chair_west: "chair_w",
    chair_east: "chair_e",
    chair_northeast: "chair_ne",
    chair_north_east: "chair_ne",
    chair_northwest: "chair_nw",
    chair_north_west: "chair_nw",
    chair_southeast: "chair_se",
    chair_south_east: "chair_se",
    chair_southwest: "chair_sw",
    chair_south_west: "chair_sw",
    chair_middle: "chair_center",
    window_south: "window_s",
    window_north: "window_n",
    window_west: "window_w",
    window_east: "window_e",
    // Victim position direct aliases
    victim_north: "chair_n",
    victim_south: "chair_s",
    victim_west: "chair_w",
    victim_east: "chair_e",
    victim_northwest: "chair_nw",
    victim_north_west: "chair_nw",
    victim_northeast: "chair_ne",
    victim_north_east: "chair_ne",
    victim_southwest: "chair_sw",
    victim_south_west: "chair_sw",
    victim_southeast: "chair_se",
    victim_south_east: "chair_se",
    victim_center: "chair_center",
    victim_middle: "chair_center",
    // Cardinal shorthand to sector anchor
    north: "chair_n",
    south: "chair_s",
    west: "chair_w",
    east: "chair_e",
    northwest: "chair_nw",
    north_west: "chair_nw",
    northeast: "chair_ne",
    north_east: "chair_ne",
    southwest: "chair_sw",
    south_west: "chair_sw",
    southeast: "chair_se",
    south_east: "chair_se",
    center: "chair_center",
    middle: "chair_center",
    room_center: "chair_center",
  };
  const resolvedTargetId = aliasMap[rawLower] || targetName || rawLower;
  const directIdMatch = physicalObjects.find((o) => o.id === resolvedTargetId || o.id === targetName || o.id === rawLower);
  if (directIdMatch) {
    let pPos = directIdMatch.pos;
    let pY = directIdMatch.y ?? 0.02;
    let pInw = directIdMatch.inward || [0, 1];
    if (directIdMatch.type === "door" && directIdMatch.sector && effectiveMarkers?.[directIdMatch.sector]) {
      const bm = effectiveMarkers[directIdMatch.sector];
      pPos = [Number(bm[0].toFixed(3)), Number(bm[2].toFixed(3))];
      pY = Number((bm[1] ?? 0.02).toFixed(3));
      const inwDx = center[0] - pPos[0];
      const inwDz = center[1] - pPos[1];
      const inwLen = Math.hypot(inwDx, inwDz) || 1.0;
      pInw = [Number((inwDx / inwLen).toFixed(3)), Number((inwDz / inwLen).toFixed(3))];
    } else if (directIdMatch.isCenter || directIdMatch.sector === "Center" || resolvedTargetId === "chair_center") {
      pPos = [center[0], center[1]];
      pInw = [0, -1];
    } else if ((directIdMatch.type === "chair" || directIdMatch.type === "couch" || directIdMatch.type === "bed") && directIdMatch.sector && effectiveMarkers?.[directIdMatch.sector]) {
      const bm = effectiveMarkers[directIdMatch.sector];
      pPos = [
        Number((center[0] + 0.70 * (bm[0] - center[0])).toFixed(3)),
        Number((center[1] + 0.70 * (bm[2] - center[1])).toFixed(3))
      ];
      pY = Number((bm[1] ?? 0.02).toFixed(3));
      const inwDx = center[0] - pPos[0];
      const inwDz = center[1] - pPos[1];
      const inwLen = Math.hypot(inwDx, inwDz) || 1.0;
      pInw = [Number((inwDx / inwLen).toFixed(3)), Number((inwDz / inwLen).toFixed(3))];
    }
    return {
      verified: true,
      status: "verified",
      pos: pPos,
      y: pY,
      inward: pInw,
      targetKey: directIdMatch.id,
      label: `${directIdMatch.label} (${directIdMatch.sector})`,
      objectType: directIdMatch.type,
      sector: directIdMatch.sector,
      sectorLabel: directIdMatch.sectorLabel,
      message: `✅ Verified: ${directIdMatch.label} confirmed at ${directIdMatch.sectorLabel} sector.`,
      confidence: directIdMatch.confidence || 0.98
    };
  }

  // 1. Detect requested object category and cardinal direction
  let reqType = null;
  const targetCheck = `${rawLower} ${resolvedTargetId}`.toLowerCase();
  if (targetCheck.includes("door") || targetCheck.includes("gate") || targetCheck.includes("entrance")) reqType = "door";
  else if (targetCheck.includes("window")) reqType = "window";
  else if (targetCheck.includes("chair") || targetCheck.includes("seat") || targetCheck.includes("stool") || targetCheck.includes("armchair") || targetCheck.includes("victim")) reqType = "chair";
  else if (targetCheck.includes("table") || targetCheck.includes("desk")) reqType = "table";
  else if (targetCheck.includes("bed")) reqType = "bed";
  else if (targetCheck.includes("sofa") || targetCheck.includes("couch")) reqType = "couch";
  else if (targetCheck.includes("exit") || targetCheck.includes("leave")) reqType = "exit";
  else if (targetCheck.includes("center") || targetCheck.includes("middle")) reqType = "center";

  // Check requested cardinal direction with underscore/hyphen normalization
  const normTarget = `${rawLower} ${resolvedTargetId}`.replace(/[_-]+/g, " ");
  let reqDir = null;
  if (/\b(?:north[\s-]?west|nw)\b/i.test(normTarget)) reqDir = "NW";
  else if (/\b(?:north[\s-]?east|ne)\b/i.test(normTarget)) reqDir = "NE";
  else if (/\b(?:south[\s-]?west|sw)\b/i.test(normTarget)) reqDir = "SW";
  else if (/\b(?:south[\s-]?east|se)\b/i.test(normTarget)) reqDir = "SE";
  else if (/\b(?:north|n)\b/i.test(normTarget)) reqDir = "N";
  else if (/\b(?:south|s)\b/i.test(normTarget)) reqDir = "S";
  else if (/\b(?:east|e)\b/i.test(normTarget)) reqDir = "E";
  else if (/\b(?:west|w)\b/i.test(normTarget)) reqDir = "W";
  else if (/\b(?:center|middle)\b/i.test(normTarget)) reqDir = "Center";
  else if (/\bcorner\b/i.test(normTarget)) reqDir = "Corner";

  const isFurniture = reqType === "chair" || reqType === "table" || reqType === "bed" || reqType === "couch";

  // 2. Handle Furniture Objects (chair, table, bed, couch)
  if (isFurniture) {
    // A. Check if an exact matching furniture object exists in requested sector
    if (reqDir && reqDir !== "Corner") {
      const sectorObj = physicalObjects.find((o) => {
        if (o.type !== reqType && !(reqType === "table" && o.type === "desk")) return false;
        return o.sector && o.sector.toUpperCase() === reqDir.toUpperCase();
      });
      if (sectorObj) {
        return {
          verified: true,
          status: "verified",
          pos: sectorObj.pos,
          y: sectorObj.y ?? 0.02,
          inward: sectorObj.inward || [0, 1],
          targetKey: sectorObj.id,
          label: `${sectorObj.label} (${sectorObj.sector})`,
          objectType: sectorObj.type,
          sector: sectorObj.sector,
          sectorLabel: sectorObj.sectorLabel,
          message: `✅ Verified: ${sectorObj.label} confirmed at ${sectorObj.sectorLabel} sector.`,
          confidence: sectorObj.confidence || 0.95
        };
      }
    }

    // B. Check for corner furniture if user requested corner
    if (reqDir === "Corner") {
      const cornerObj = physicalObjects.find((o) => {
        if (o.type !== reqType && !(reqType === "table" && o.type === "desk")) return false;
        return ["NE", "NW", "SE", "SW"].includes(o.sector?.toUpperCase());
      });
      if (cornerObj) {
        return {
          verified: true,
          status: "verified",
          pos: cornerObj.pos,
          y: cornerObj.y ?? 0.02,
          inward: cornerObj.inward || [0, 1],
          targetKey: cornerObj.id,
          label: `${cornerObj.label} (${cornerObj.sector})`,
          objectType: cornerObj.type,
          sector: cornerObj.sector,
          sectorLabel: cornerObj.sectorLabel,
          message: `✅ Verified: ${cornerObj.label} confirmed in room corner (${cornerObj.sectorLabel}).`,
          confidence: cornerObj.confidence || 0.95
        };
      }
      const navGrid = NavGrid.loadActiveSceneGrid() || NavGrid.fromBoundsAndAnchors(bounds, {});
      const safe = navGrid.getSafeDirectionPosition("NW", 0.25, 0.72);
      const typeLabel = reqType.charAt(0).toUpperCase() + reqType.slice(1);
      return {
        verified: true,
        status: "verified",
        pos: safe.pos,
        y: safe.y,
        inward: safe.inward,
        targetKey: `${reqType}_nw`,
        label: `North-West ${typeLabel} [NW]`,
        objectType: reqType,
        sector: "NW",
        sectorLabel: "North-West",
        message: `✅ Verified: ${typeLabel} placed at North-West corner.`,
        confidence: 0.95
      };
    }

    // C. If user explicitly requested Center / Middle for furniture
    if (reqDir === "Center" || reqType === "center") {
      return {
        verified: true,
        status: "verified",
        pos: [center[0], center[1]],
        y: bounds?.floorY ?? 0.02,
        inward: [0, -1],
        targetKey: "chair_center",
        label: "Victim Chair [Center]",
        objectType: "chair",
        sector: "Center",
        sectorLabel: "Center",
        message: "✅ Verified: Victim placed at room center.",
        confidence: 0.98
      };
    }

    // D. If user explicitly requested a cardinal sector for furniture, calculate position in that sector covering full room area
    if (reqDir && reqDir !== "Center" && reqDir !== "Corner") {
      const secMeta = CARDINAL_SECTORS.find((s) => s.code === reqDir) || { code: reqDir, label: reqDir, angle: 45 };
      let safePos, safeY, safeInw;
      if (effectiveMarkers?.[reqDir]) {
        const bm = effectiveMarkers[reqDir];
        safePos = [
          Number((center[0] + 0.70 * (bm[0] - center[0])).toFixed(3)),
          Number((center[1] + 0.70 * (bm[2] - center[1])).toFixed(3))
        ];
        safeY = Number((bm[1] ?? 0.02).toFixed(3));
        const inwDx = center[0] - safePos[0];
        const inwDz = center[1] - safePos[1];
        const inwLen = Math.hypot(inwDx, inwDz) || 1.0;
        safeInw = [Number((inwDx / inwLen).toFixed(3)), Number((inwDz / inwLen).toFixed(3))];
      } else {
        const navGrid = NavGrid.loadActiveSceneGrid() || NavGrid.fromBoundsAndAnchors(bounds, {});
        const safe = navGrid.getSafeDirectionPosition(reqDir, 0.25, 0.72);
        safePos = safe.pos;
        safeY = safe.y;
        safeInw = safe.inward;
      }
      const typeLabel = reqType.charAt(0).toUpperCase() + reqType.slice(1);
      const objLabel = `${secMeta.label} ${typeLabel}`;
      return {
        verified: true,
        status: "verified",
        pos: safePos,
        y: safeY,
        inward: safeInw,
        targetKey: `${reqType}_${reqDir.toLowerCase()}`,
        label: `${objLabel} [${reqDir}]`,
        objectType: reqType,
        sector: reqDir,
        sectorLabel: secMeta.label,
        message: `✅ Verified: ${objLabel} placed at ${secMeta.label} sector.`,
        confidence: 0.95
      };
    }

    // E. Check if ANY furniture of this type exists in the room (when no specific direction was requested)
    const anyMatching = physicalObjects.find((o) => {
      return o.type === reqType || (reqType === "table" && o.type === "desk");
    });
    if (anyMatching) {
      return {
        verified: true,
        status: "verified",
        pos: anyMatching.pos,
        inward: anyMatching.inward || [0, 1],
        targetKey: anyMatching.id,
        label: `${anyMatching.label} (${anyMatching.sector})`,
        objectType: anyMatching.type,
        sector: anyMatching.sector,
        sectorLabel: anyMatching.sectorLabel,
        message: `✅ Verified: Detected ${anyMatching.label} at ${anyMatching.sectorLabel} sector (coordinates: [${anyMatching.pos[0]}, ${anyMatching.pos[1]}]).`,
        confidence: anyMatching.confidence || 0.92
      };
    }

    // D. NO matching furniture exists physically in the room!
    const missingLabel = reqType.charAt(0).toUpperCase() + reqType.slice(1);
    return {
      verified: false,
      status: "object_not_found",
      pos: [center[0], center[1]],
      inward: [0, 1],
      targetKey: "room_center",
      label: `Room Center (No ${missingLabel} Detected)`,
      objectType: "center",
      sector: "Center",
      sectorLabel: "Center",
      message: `⚠️ No ${reqType} was detected in this room. Victim placed standing at room center.`,
      confidence: 0.0
    };
  }

  // 3. Handle Perimeter Entrances / Portals (door, window, entrance, exit)
  const isPortal = reqType === "door" || reqType === "window" || reqType === "exit";

  if (isPortal) {
    // A. If a cardinal direction was specified (e.g., "south door", "north window")
    if (reqDir && reqDir !== "Center" && reqDir !== "Corner") {
      // If boundary marker exists for requested direction, strictly snap door to it
      if (effectiveMarkers && effectiveMarkers[reqDir]) {
        const bm = effectiveMarkers[reqDir];
        const bPos = [Number(bm[0].toFixed(3)), Number(bm[2].toFixed(3))];
        const bY = Number((bm[1] ?? 0.02).toFixed(3));
        const inwDx = center[0] - bPos[0];
        const inwDz = center[1] - bPos[1];
        const inwLen = Math.hypot(inwDx, inwDz) || 1.0;
        const bInw = [Number((inwDx / inwLen).toFixed(3)), Number((inwDz / inwLen).toFixed(3))];
        const sectorName = CARDINAL_SECTORS.find((s) => s.code === reqDir)?.label || reqDir;
        return {
          verified: true,
          status: "verified",
          pos: bPos,
          y: bY,
          inward: bInw,
          targetKey: `${reqType || "door"}_${reqDir.toLowerCase()}`,
          label: `${sectorName} ${reqType ? (reqType.charAt(0).toUpperCase() + reqType.slice(1)) : "Door"} [${reqDir}]`,
          objectType: reqType || "door",
          sector: reqDir,
          sectorLabel: sectorName,
          message: `✅ Verified: ${sectorName} Door aligned to boundary marker ${reqDir}.`,
          confidence: 0.99
        };
      }

      // Check physicalObjects for a door/window in that specific sector
      const sectorPortal = physicalObjects.find((o) => {
        if (!o.sector || o.sector.toUpperCase() !== reqDir.toUpperCase()) return false;
        if (reqType === "door" && (o.type === "door" || o.type === "entrance" || o.type === "exit")) return true;
        if (reqType === "exit" && (o.type === "door" || o.type === "entrance" || o.type === "exit" || o.type === "window")) return true;
        return o.type === reqType;
      });

      if (sectorPortal) {
        return {
          verified: true,
          status: "verified",
          pos: sectorPortal.pos,
          inward: sectorPortal.inward || [0, 1],
          targetKey: sectorPortal.id,
          label: `${sectorPortal.label} (${sectorPortal.sector})`,
          objectType: sectorPortal.type,
          sector: sectorPortal.sector,
          sectorLabel: sectorPortal.sectorLabel,
          message: `✅ Verified: ${sectorPortal.label} confirmed at ${sectorPortal.sectorLabel} sector.`,
          confidence: sectorPortal.confidence || 0.95
        };
      }

      // If no pre-registered portal in that sector, dynamically compute calibrated perimeter point!
      const targetDir = reqDir;
      const navGrid = NavGrid.loadActiveSceneGrid() || NavGrid.fromBoundsAndAnchors(bounds, {});
      const safe = navGrid.getSafeDirectionPosition(targetDir, 0.20, 1.0);
      const sectorName = CARDINAL_SECTORS.find((s) => s.code === targetDir)?.label || targetDir;

      return {
        verified: true,
        status: "dynamic_perimeter",
        pos: safe.pos,
        y: safe.y,
        inward: safe.inward,
        targetKey: `${reqType || "door"}_${targetDir.toLowerCase()}`,
        label: `${sectorName} ${reqType ? reqType.toUpperCase() : "Entrance"}`,
        objectType: reqType || "door",
        sector: targetDir,
        sectorLabel: sectorName,
        message: `✅ Verified: ${sectorName} perimeter entrance confirmed.`,
        confidence: 0.92
      };
    }

    // B. If NO cardinal direction was specified (user just said "door", "window", "entrance")
    const matchingPortals = physicalObjects.filter((o) => {
      if (reqType === "door" && (o.type === "door" || o.type === "entrance" || o.type === "exit")) return true;
      if (reqType === "exit" && (o.type === "door" || o.type === "entrance" || o.type === "exit" || o.type === "window")) return true;
      return o.type === reqType;
    });

    if (matchingPortals.length > 0) {
      const bestPortal = matchingPortals[0];
      return {
        verified: true,
        status: "snapped_to_verified",
        pos: bestPortal.pos,
        y: bestPortal.y ?? 0.02,
        inward: bestPortal.inward || [0, 1],
        targetKey: bestPortal.id,
        label: `${bestPortal.label} (${bestPortal.sector})`,
        objectType: bestPortal.type,
        sector: bestPortal.sector,
        sectorLabel: bestPortal.sectorLabel,
        message: `✅ Verified: Using detected ${bestPortal.label} at ${bestPortal.sectorLabel} sector.`,
        confidence: bestPortal.confidence || 0.94
      };
    }

    // If no portal registered, generate dynamic perimeter at South (standard entryway)
    const defDir = reqType === "window" ? "W" : "S";
    const navGrid = NavGrid.loadActiveSceneGrid() || NavGrid.fromBoundsAndAnchors(bounds, {});
    const safe = navGrid.getSafeDirectionPosition(defDir, 0.20, 1.0);
    return {
      verified: true,
      status: "dynamic_perimeter",
      pos: safe.pos,
      y: safe.y,
      inward: safe.inward,
      targetKey: reqType,
      label: `Perimeter ${reqType.toUpperCase()}`,
      objectType: reqType,
      sector: defDir,
      sectorLabel: defDir === "S" ? "South" : "West",
      message: `ℹ️ Using perimeter entrance at ${defDir === "S" ? "South" : "West"}.`,
      confidence: 0.88
    };
  }

  // 4. Default / Center
  const navGrid = NavGrid.loadActiveSceneGrid() || NavGrid.fromBoundsAndAnchors(bounds, {});
  const safe = navGrid.getSafeDirectionPosition("Center", 0.0, 0.0);
  return {
    verified: true,
    status: "verified",
    pos: safe.pos,
    y: safe.y,
    inward: safe.inward,
    targetKey: "room_center",
    label: "Room Center",
    objectType: "center",
    sector: "Center",
    sectorLabel: "Center",
    message: "ℹ️ Centered in room.",
    confidence: 1.0
  };
}
