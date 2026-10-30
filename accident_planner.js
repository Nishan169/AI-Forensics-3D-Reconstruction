/**
 * accident_planner.js
 * 
 * Forensic Vehicular, Rail & Pedestrian Accident Simulation Planner.
 * Features:
 * - Dynamic yaw computation (atan2(-dx, -dz)) ensuring all vehicles face forward
 * - Multi-train collision & single-train derailment kinematic tracks
 * - Multi-environment support (pure rail corridor, rail grade-crossing, road intersection)
 * - Crash-proof null-safe data pipelines
 */

export const VEHICLE_PRESETS = {
  sedan: {
    label: "Passenger Sedan",
    type: "car",
    mass: 1550,
    length: 4.75,
    width: 1.82,
    height: 1.44,
    frictionCoeff: 0.78,
  },
  suv: {
    label: "SUV / Pickup",
    type: "car",
    mass: 2350,
    length: 5.10,
    width: 2.02,
    height: 1.82,
    frictionCoeff: 0.74,
  },
  truck: {
    label: "Delivery Box Truck",
    type: "truck",
    mass: 8800,
    length: 7.80,
    width: 2.45,
    height: 3.20,
    frictionCoeff: 0.68,
  },
  semi_trailer: {
    label: "18-Wheeler Semi Truck",
    type: "semi_trailer",
    mass: 28000,
    length: 16.50,
    width: 2.55,
    height: 4.10,
    frictionCoeff: 0.64,
  },
  bus: {
    label: "Transit Bus",
    type: "bus",
    mass: 13500,
    length: 12.00,
    width: 2.55,
    height: 3.20,
    frictionCoeff: 0.68,
  },
  train: {
    label: "Freight Train Locomotive",
    type: "train",
    mass: 125000,
    length: 19.50,
    width: 3.15,
    height: 4.20,
    frictionCoeff: 0.22,
    constrainedToRails: true,
  },
  motorcycle: {
    label: "Motorcycle",
    type: "motorcycle",
    mass: 215,
    length: 2.10,
    width: 0.82,
    height: 1.15,
    frictionCoeff: 0.82,
    riderEjection: true,
  },
  pedestrian: {
    label: "Pedestrian",
    type: "pedestrian",
    mass: 75,
    length: 0.50,
    width: 0.50,
    height: 1.75,
    frictionCoeff: 0.60,
  }
};

const GEMINI_ACCIDENT_SYSTEM_PROMPT = `You are an expert forensic accident reconstruction physicist.
Parse traffic, train, and pedestrian crashes into structured simulation parameters.
Valid vehicle types: "sedan", "suv", "truck", "semi_trailer", "bus", "train", "motorcycle", "pedestrian".
Approach directions: "N", "S", "E", "W", "NE", "NW", "SE", "SW".
Crash types: "t_bone", "head_on", "rear_end", "sideswipe", "rail_crossing", "pedestrian_strike", "derailment", "train_head_on".
Weather: "dry", "wet", "snow".

OUTPUT FORMAT: Return ONLY valid JSON:
{
  "scenarioTitle": string,
  "crashType": "t_bone" | "head_on" | "rear_end" | "sideswipe" | "rail_crossing" | "pedestrian_strike" | "derailment" | "train_head_on",
  "weather": "dry" | "wet" | "snow",
  "poi": [0, 0],
  "vehicles": [
    {
      "id": "veh_1",
      "type": "train" | "semi_trailer" | "sedan" | "suv" | "truck" | "bus" | "motorcycle" | "pedestrian",
      "name": "Vehicle 1",
      "color": "#b91c1c",
      "speedKmh": 75,
      "approachDir": "W",
      "reaction": "braking" | "none"
    }
  ]
}`;

export async function parseAccidentPrompt(prompt, apiKey = null) {
  const fallbackScript = ruleBasedParseAccident(prompt);
  const key = apiKey || process.env.GEMINI_API_KEY;
  if (!key) return { script: fallbackScript, source: "rule_based" };

  try {
    const models = ["gemini-2.5-flash", "gemini-2.0-flash"];
    for (const model of models) {
      try {
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`;
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: `${GEMINI_ACCIDENT_SYSTEM_PROMPT}\n\nAccident Scenario:\n${prompt}` }] }],
            generationConfig: { temperature: 0.1, responseMimeType: "application/json" }
          })
        });
        if (res.ok) {
          const data = await res.json();
          const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
          if (text) {
            const parsed = JSON.parse(text);
            if (parsed && Array.isArray(parsed.vehicles) && parsed.vehicles.length >= 1) {
              if (fallbackScript.crashType === "train_head_on" || fallbackScript.crashType === "derailment") {
                return { script: fallbackScript, source: "rule_based" };
              }
              return { script: parsed, source: "gemini" };
            }
          }
        }
      } catch (_) {}
    }
  } catch (_) {}

  return { script: fallbackScript, source: "rule_based" };
}

const ENTITY_PATTERNS = [
  { type: "semi_trailer", name: "18-Wheeler Semi", color: "#334155", defaultSpeed: 65, regex: /\b(?:semi[\s-]?trucks?|18[\s-]?wheelers?|semi[\s-]?trailers?|tractor[\s-]?trailers?)\b/i },
  { type: "train", name: "Freight Locomotive", color: "#b91c1c", defaultSpeed: 80, regex: /\b(?:trains?|locomotives?|freight trains?|railways?|railroads?)\b/i },
  { type: "bus", name: "Transit Bus", color: "#eab308", defaultSpeed: 45, regex: /\b(?:bus|buses|transit bus|coach|school bus)\b/i },
  { type: "truck", name: "Delivery Truck", color: "#1d4ed8", defaultSpeed: 55, regex: /\b(?:trucks?|lorr(?:y|ies)|box trucks?|delivery trucks?)\b/i },
  { type: "motorcycle", name: "Motorcycle", color: "#111827", defaultSpeed: 70, regex: /\b(?:motorcycles?|motorbikes?|bikes?|scooters?|mopeds?)\b/i },
  { type: "pedestrian", name: "Pedestrian", color: "#f59e0b", defaultSpeed: 5, regex: /\b(?:pedestrians?|persons?|walkers?|man|woman|humans?|child)\b/i },
  { type: "suv", name: "White SUV", color: "#f8fafc", defaultSpeed: 50, regex: /\b(?:suvs?|pickups?|crossovers?|jeeps?|4x4s?)\b/i },
  { type: "sedan", name: "Passenger Sedan", color: "#2563eb", defaultSpeed: 60, regex: /\b(?:cars?|sedans?|coupes?|automobiles?|vehicles?|taxis?)\b/i },
];

function extractSpeedForSpan(span, fallback) {
  const m = span.match(/(\d{2,3})\s*(?:km\/?h|kph|mph)/i);
  if (m) {
    const val = parseInt(m[1], 10);
    return span.toLowerCase().includes("mph") ? Math.round(val * 1.609) : val;
  }
  return fallback;
}

function extractDirectionForSpan(span) {
  if (/\b(?:north[\s-]?west|nw)\b/i.test(span)) return "NW";
  if (/\b(?:north[\s-]?east|ne)\b/i.test(span)) return "NE";
  if (/\b(?:south[\s-]?west|sw)\b/i.test(span)) return "SW";
  if (/\b(?:south[\s-]?east|se)\b/i.test(span)) return "SE";
  if (/\b(?:north|n)\b/i.test(span)) return "N";
  if (/\b(?:south|s)\b/i.test(span)) return "S";
  if (/\b(?:east|e)\b/i.test(span)) return "E";
  if (/\b(?:west|w)\b/i.test(span)) return "W";
  return null;
}

export function ruleBasedParseAccident(prompt) {
  const t = (prompt || "").toLowerCase();

  // Multi-train collision check
  const isMultiTrain = (
    /\b(?:two|2|both|pair of)\s+(?:freight\s+|passenger\s+|diesel\s+)?(?:trains?|locomotives?)\b/i.test(t) ||
    /\b(?:train[\s-]on[\s-]train|trains?\s+collide|locomotives?\s+collide)\b/i.test(t) ||
    (/\b(?:train|locomotive)\b/i.test(t) && /\b(?:another|second|opposing|oncoming)\s+(?:train|locomotive)\b/i.test(t))
  );

  const isDerailment = /\b(?:derail|derails|derailed|derailment|jumps?\s+tracks?|off\s+the\s+tracks?)\b/i.test(t);

  const foundEntities = [];
  if (isMultiTrain) {
    foundEntities.push({ type: "train", name: "Freight Locomotive A", color: "#b91c1c", defaultSpeed: 75, index: 0 });
    foundEntities.push({ type: "train", name: "Freight Locomotive B", color: "#1e3a8a", defaultSpeed: 65, index: Math.floor(t.length / 2) });
  } else {
    for (const ent of ENTITY_PATTERNS) {
      const match = ent.regex.exec(t);
      if (match) {
        foundEntities.push({
          type: ent.type,
          name: ent.name,
          color: ent.color,
          defaultSpeed: ent.defaultSpeed,
          index: match.index,
        });
      }
    }
    foundEntities.sort((a, b) => a.index - b.index);
  }

  let ent1 = foundEntities[0] || { type: "sedan", name: "Blue Sedan", color: "#2563eb", defaultSpeed: 65, index: 0 };
  let ent2 = foundEntities[1] || null;

  const isSoloDerailment = isDerailment && !isMultiTrain && ent1.type === "train" && !ent2;

  if (!ent2 && !isSoloDerailment) {
    if (ent1.type === "train") {
      ent2 = { type: "suv", name: "Stalled SUV", color: "#f8fafc", defaultSpeed: 0, index: t.length };
    } else if (ent1.type === "pedestrian") {
      ent2 = { type: "sedan", name: "Striking Sedan", color: "#2563eb", defaultSpeed: 50, index: t.length };
    } else if (ent1.type === "motorcycle") {
      ent2 = { type: "suv", name: "White SUV", color: "#f8fafc", defaultSpeed: 45, index: t.length };
    } else {
      ent2 = { type: "truck", name: "Delivery Truck", color: "#dc2626", defaultSpeed: 50, index: t.length };
    }
  }

  let crashType = "t_bone";
  if (isMultiTrain) crashType = "train_head_on";
  else if (isSoloDerailment) crashType = "derailment";
  else if (ent1.type === "train" || ent2?.type === "train") crashType = "rail_crossing";
  else if (/\b(?:head[\s-]?on|frontal)\b/i.test(t)) crashType = "head_on";
  else if (/\b(?:rear[\s-]?end|from behind|tailgate)\b/i.test(t)) crashType = "rear_end";
  else if (/\b(?:sideswipe|side swipe)\b/i.test(t)) crashType = "sideswipe";
  else if (ent1.type === "pedestrian" || ent2?.type === "pedestrian") crashType = "pedestrian_strike";

  const midIdx = ent2 ? ent2.index : t.length;
  const clause1 = t.slice(0, midIdx);
  const clause2 = ent2 ? t.slice(midIdx) : "";

  const isStalled1 = /\b(?:stalled|stopped|stationary|parked|stranded)\b/i.test(clause1);
  const isStalled2 = /\b(?:stalled|stopped|stationary|parked|stranded)\b/i.test(clause2) || (crashType === "rail_crossing" && /\b(?:stalled|stopped|stationary|parked)\b/i.test(t) && ent2?.type !== "train");

  const speed1 = isStalled1 ? 0 : extractSpeedForSpan(clause1, ent1.defaultSpeed);
  const speed2 = ent2 ? (isStalled2 ? 0 : extractSpeedForSpan(clause2, ent2.defaultSpeed)) : 0;

  let dir1 = extractDirectionForSpan(clause1);
  let dir2 = ent2 ? extractDirectionForSpan(clause2) : null;

  if (isMultiTrain || crashType === "train_head_on") {
    dir1 = "W";
    dir2 = "E";
  } else if (isSoloDerailment) {
    dir1 = "W";
  } else if (crashType === "rail_crossing") {
    if (ent1.type === "train") {
      dir1 = dir1 || "W";
      dir2 = dir2 || "S";
    } else {
      dir1 = dir1 || "S";
      dir2 = dir2 || "W";
    }
  } else if (!dir1 && !dir2) {
    if (crashType === "head_on") { dir1 = "W"; dir2 = "E"; }
    else if (crashType === "rear_end") { dir1 = "W"; dir2 = "W"; }
    else if (crashType === "pedestrian_strike") { dir1 = "W"; dir2 = "N"; }
    else { dir1 = "W"; dir2 = "S"; }
  } else if (dir1 && !dir2) {
    if (crashType === "head_on") dir2 = { N: "S", S: "N", E: "W", W: "E" }[dir1] || "E";
    else if (crashType === "rear_end") dir2 = dir1;
    else dir2 = { N: "E", S: "W", E: "S", W: "N" }[dir1] || "S";
  } else if (!dir1 && dir2) {
    dir1 = { N: "W", S: "E", E: "N", W: "S" }[dir2] || "W";
  }

  const isBraking1 = t.includes("brake") || t.includes("skid") || t.includes("tried to stop");
  const weather = t.includes("rain") || t.includes("wet") ? "wet" : (t.includes("snow") ? "snow" : "dry");

  const vehicles = [
    {
      id: "veh_1",
      type: ent1.type,
      name: ent1.name,
      color: ent1.color,
      speedKmh: speed1,
      approachDir: dir1 || "W",
      reaction: isBraking1 ? "braking" : "none",
    }
  ];

  if (ent2) {
    vehicles.push({
      id: "veh_2",
      type: ent2.type,
      name: ent2.name,
      color: ent2.color,
      speedKmh: speed2,
      approachDir: dir2 || "S",
      reaction: "none",
    });
  }

  return {
    scenarioTitle: isMultiTrain
      ? "Rail Collision: Head-On Crash Between Two Trains"
      : isSoloDerailment
        ? "Rail Incident: High-Speed Train Derailment"
        : `Accident Reconstruction: ${ent1.name} vs ${ent2.name}`,
    crashType,
    weather,
    poi: [0, 0],
    vehicles
  };
}

export function generateAccidentPlan(script, bounds = null) {
  const g = 9.81;
  const impactTime = 3.5;
  const totalDuration = 7.0;

  const rawVehicles = Array.isArray(script?.vehicles) && script.vehicles.length > 0
    ? script.vehicles
    : [{ id: "veh_1", type: "train", name: "Freight Locomotive", color: "#b91c1c", speedKmh: 80, approachDir: "W", reaction: "none" }];

  const v1 = {
    id: rawVehicles[0].id || "veh_1",
    type: rawVehicles[0].type || "sedan",
    name: rawVehicles[0].name || "Vehicle 1",
    color: rawVehicles[0].color || "#b91c1c",
    speedKmh: rawVehicles[0].speedKmh ?? 60,
    approachDir: rawVehicles[0].approachDir || "W",
    reaction: rawVehicles[0].reaction || "none"
  };

  const isSoloDerailment = script?.crashType === "derailment" && v1.type === "train" && rawVehicles.length === 1;

  const v2 = rawVehicles[1] ? {
    id: rawVehicles[1].id || "veh_2",
    type: rawVehicles[1].type || "suv",
    name: rawVehicles[1].name || "Vehicle 2",
    color: rawVehicles[1].color || "#1e3a8a",
    speedKmh: rawVehicles[1].speedKmh ?? 0,
    approachDir: rawVehicles[1].approachDir || "S",
    reaction: rawVehicles[1].reaction || "none"
  } : null;

  const spec1 = VEHICLE_PRESETS[v1.type] || VEHICLE_PRESETS.sedan;
  const spec2 = v2 ? (VEHICLE_PRESETS[v2.type] || VEHICLE_PRESETS.sedan) : null;

  const hasTrain = v1.type === "train" || v2?.type === "train";
  const hasPedestrian = v1.type === "pedestrian" || v2?.type === "pedestrian";
  const isTrainOnTrain = Boolean(v1.type === "train" && v2 && v2.type === "train");
  const isDerailment = isSoloDerailment || isTrainOnTrain || script?.crashType === "derailment";

  const environmentType = (isTrainOnTrain || isSoloDerailment)
    ? "rail_corridor"
    : (hasTrain ? "rail_crossing" : (hasPedestrian ? "pedestrian_crosswalk" : "road_intersection"));

  const m1 = spec1.mass;
  const m2 = spec2 ? spec2.mass : 0;

  const weatherFriction = script?.weather === "wet" ? 0.60 : (script?.weather === "snow" ? 0.30 : 1.0);
  const mu1 = spec1.frictionCoeff * weatherFriction;
  const mu2 = spec2 ? spec2.frictionCoeff * weatherFriction : mu1;

  const v1_init_mps = (v1.speedKmh ?? 60) / 3.6;
  const v2_init_mps = v2 ? (v2.speedKmh ?? 50) / 3.6 : 0;

  // Track vs Road alignment assignment
  if (isTrainOnTrain && v2) {
    v1.approachDir = "W"; // Train A travels West -> East (+X)
    v2.approachDir = "E"; // Train B travels East -> West (-X)
  } else if (hasTrain && v2) {
    const trainVehicle = v1.type === "train" ? v1 : v2;
    const roadVehicle = trainVehicle === v1 ? v2 : v1;
    trainVehicle.approachDir = "W";
    roadVehicle.approachDir = "S";
  }

  // 2D Movement Vectors: [dx, dz]
  const DIR_MAP = {
    N:  { dir: [0, 1] },              // Approaching from North, traveling South (+Z)
    S:  { dir: [0, -1] },             // Approaching from South, traveling North (-Z)
    E:  { dir: [-1, 0] },             // Approaching from East, traveling West (-X)
    W:  { dir: [1, 0] },              // Approaching from West, traveling East (+X)
    NE: { dir: [-0.707, 0.707] },
    NW: { dir: [0.707, 0.707] },
    SE: { dir: [-0.707, -0.707] },
    SW: { dir: [0.707, -0.707] }
  };

  const vec1 = DIR_MAP[v1.approachDir] || DIR_MAP.W;
  const vec2 = v2 ? (DIR_MAP[v2.approachDir] || (isTrainOnTrain ? DIR_MAP.E : DIR_MAP.S)) : { dir: [0, 0] };

  // MATHEMATICAL FIX FOR BUG 1: Vehicles built facing local -Z -> yaw = atan2(-dx, -dz)
  const yaw1 = Number(Math.atan2(-vec1.dir[0], -vec1.dir[1]).toFixed(4));
  const yaw2 = v2 ? Number(Math.atan2(-vec2.dir[0], -vec2.dir[1]).toFixed(4)) : 0;

  const trainAxis = "X";
  const poi = Array.isArray(script?.poi) && script.poi.length >= 2 ? script.poi : [0, 0];

  const tracks = { [v1.id]: [] };
  if (v2) tracks[v2.id] = [];

  const skidMarks = [];
  const debrisField = [];
  const impacts = [];
  const captions = [];

  function addSeg(aid, kind, t0, t1, from, to, yaw, extra = {}) {
    if (!tracks[aid]) tracks[aid] = [];
    tracks[aid].push({
      kind,
      t0: Number(t0.toFixed(3)),
      t1: Number(t1.toFixed(3)),
      from: [Number(from[0].toFixed(3)), Number(from[1].toFixed(3))],
      to: [Number(to[0].toFixed(3)), Number(to[1].toFixed(3))],
      from_y: 0.02,
      to_y: 0.02,
      yaw: Number(yaw.toFixed(3)),
      pitch: extra.pitch || 0.0,
      roll: extra.roll || 0.0,
      speedKmh: extra.speedKmh ?? 0,
      damageState: extra.damageState || "intact"
    });
  }

  // ── SOLO DERAILMENT SCENARIO ──────────────────────────────────────────────
  if (isSoloDerailment || !v2) {
    const approachDist1 = Math.max(30.0, v1_init_mps * impactTime);
    const start1 = [poi[0] - vec1.dir[0] * approachDist1, poi[1] - vec1.dir[1] * approachDist1];

    addSeg(v1.id, "drive", 0, impactTime, start1, poi, yaw1, { speedKmh: v1.speedKmh });

    const forwardSlide = Math.min(22.0, Math.max(12.0, v1_init_mps * (totalDuration - impactTime) * 0.45));
    const lateralThrow = 4.5;
    const restPos1 = [
      poi[0] + vec1.dir[0] * forwardSlide,
      poi[1] + lateralThrow
    ];

    addSeg(v1.id, "post_collision_spin", impactTime, totalDuration, poi, restPos1, yaw1 - 0.45, {
      speedKmh: 0,
      damageState: "crumpled",
      roll: 0.82, // Rolls 47° onto its side into the ballast
      pitch: -0.05
    });

    skidMarks.push({ vehicleId: v1.id, from: poi, to: restPos1, intensity: 0.95 });

    const deltaE_KJ = Math.round((0.5 * m1 * Math.pow(v1_init_mps, 2)) / 1000);
    impacts.push({
      t: impactTime,
      pos: [poi[0], 0.85, poi[1]],
      style: "train_derailment",
      energyDissipatedKJ: deltaE_KJ
    });

    for (let i = 0; i < 45; i++) {
      const u = Math.random();
      debrisField.push({
        pos: [
          Number((poi[0] + (restPos1[0] - poi[0]) * u + (Math.random() - 0.5) * 3.5).toFixed(3)),
          0.02,
          Number((poi[1] + (restPos1[1] - poi[1]) * u + (Math.random() - 0.5) * 3.5).toFixed(3))
        ],
        type: "metal_plastic_shard"
      });
    }

    captions.push({ t: 0.0, text: `${v1.name} travelling at ${v1.speedKmh} km/h along the railway corridor.` });
    captions.push({ t: impactTime, text: `DERAILMENT: High-speed wheel flange failure forces ${v1.name} off the rails.` });
    captions.push({ t: Number((impactTime + 0.8).toFixed(2)), text: "Locomotive rolls onto its side, plowing through the gravel ballast." });
    captions.push({ t: totalDuration - 0.5, text: "Derailment halted; locomotive rests off-track." });

    return {
      duration: totalDuration,
      scenarioTitle: script.scenarioTitle || "High-Speed Freight Train Derailment",
      crashType: "derailment",
      weather: script.weather || "dry",
      environmentType: "rail_corridor",
      trainAxis: "X",
      impactTime,
      poi: [poi[0], 0.02, poi[1]],
      tracks,
      skidMarks,
      debrisField,
      impacts,
      captions,
      vehicles: [{ ...spec1, ...v1, type: spec1.type }]
    };
  }

  // ── TWO-VEHICLE COLLISION SCENARIO ────────────────────────────────────────
  const isBraking1 = v1.reaction === "braking";
  const brakeDuration1 = isBraking1 ? 1.4 : 0.0;
  const a_brake1 = -mu1 * g;

  const v1_impact = isBraking1 ? Math.max(4.0, v1_init_mps + a_brake1 * brakeDuration1) : v1_init_mps;
  const v2_impact = v2_init_mps;

  // Nose offset accounts for locomotive length so cowcatchers touch at POI
  const noseOffset1 = v1.type === "train" ? (isTrainOnTrain ? 9.2 : 8.5) : 0;
  const noseOffset2 = v2.type === "train" ? (isTrainOnTrain ? 9.2 : 8.5) : 0;

  const impactPos1 = [poi[0] - vec1.dir[0] * noseOffset1, poi[1] - vec1.dir[1] * noseOffset1];
  const impactPos2 = [poi[0] - vec2.dir[0] * noseOffset2, poi[1] - vec2.dir[1] * noseOffset2];

  let start1, start2;
  if (script.crashType === "rear_end") {
    const leadDist = Math.max(3.0, v1_impact * 0.8);
    start1 = [impactPos1[0] - vec1.dir[0] * leadDist, impactPos1[1] - vec1.dir[1] * leadDist];
    const chaseDist = Math.max(leadDist + 16.0, v2_init_mps * impactTime);
    start2 = [impactPos2[0] - vec2.dir[0] * chaseDist, impactPos2[1] - vec2.dir[1] * chaseDist];
  } else {
    const approachDist1 = isBraking1
      ? (v1_init_mps * (impactTime - brakeDuration1) + (v1_init_mps * brakeDuration1 + 0.5 * a_brake1 * Math.pow(brakeDuration1, 2)))
      : (v1_init_mps * impactTime);
    const approachDist2 = (v2.type === "pedestrian") ? 5.2 : (v2_init_mps * impactTime);

    start1 = [impactPos1[0] - vec1.dir[0] * approachDist1, impactPos1[1] - vec1.dir[1] * approachDist1];
    start2 = [impactPos2[0] - vec2.dir[0] * approachDist2, impactPos2[1] - vec2.dir[1] * approachDist2];
  }

  if (isBraking1) {
    const tBrakeStart = impactTime - brakeDuration1;
    const brakePos1 = [
      impactPos1[0] - vec1.dir[0] * (v1_impact * brakeDuration1 - 0.5 * a_brake1 * Math.pow(brakeDuration1, 2)),
      impactPos1[1] - vec1.dir[1] * (v1_impact * brakeDuration1 - 0.5 * a_brake1 * Math.pow(brakeDuration1, 2))
    ];
    addSeg(v1.id, "drive", 0, tBrakeStart, start1, brakePos1, yaw1, { speedKmh: v1.speedKmh });
    addSeg(v1.id, "skid", tBrakeStart, impactTime, brakePos1, impactPos1, yaw1, {
      speedKmh: Math.round(v1_impact * 3.6),
      pitch: -0.035
    });
    skidMarks.push({ vehicleId: v1.id, from: brakePos1, to: impactPos1, intensity: 0.85 });
  } else {
    addSeg(v1.id, "drive", 0, impactTime, start1, impactPos1, yaw1, { speedKmh: v1.speedKmh });
  }

  addSeg(v2.id, (v2.type === "pedestrian" ? "walk" : "drive"), 0, impactTime, start2, impactPos2, yaw2, { speedKmh: v2.speedKmh });

  const p_total_x = (m1 * v1_impact * vec1.dir[0]) + (m2 * v2_impact * vec2.dir[0]);
  const p_total_z = (m1 * v1_impact * vec1.dir[1]) + (m2 * v2_impact * vec2.dir[1]);

  let post_vx = p_total_x / (m1 + m2);
  let post_vz = p_total_z / (m1 + m2);

  if (spec1.constrainedToRails && !isTrainOnTrain) {
    post_vx = v1_impact * vec1.dir[0] * 0.85;
    post_vz = v1_impact * vec1.dir[1] * 0.85;
  } else if (spec2 && spec2.constrainedToRails && !isTrainOnTrain) {
    post_vx = v2_impact * vec2.dir[0] * 0.85;
    post_vz = v2_impact * vec2.dir[1] * 0.85;
  }

  const post_speed = Math.hypot(post_vx, post_vz);
  const skidDist = Math.pow(post_speed, 2) / (2 * Math.max(0.4, (mu1 + mu2) / 2) * g);

  const crossProduct = vec1.dir[0] * vec2.dir[1] - vec1.dir[1] * vec2.dir[0];
  const spinSign = crossProduct >= 0 ? 1 : -1;

  let restPos1, restPos2, spinRate1 = 0, spinRate2 = 0, roll1 = 0, roll2 = 0;

  if (isTrainOnTrain) {
    // Both locomotives telescope and jackknife off opposite sides of the track
    restPos1 = [impactPos1[0] + vec1.dir[0] * 3.8, impactPos1[1] + 2.8];
    restPos2 = [impactPos2[0] + vec2.dir[0] * 3.8, impactPos2[1] - 2.8];
    spinRate1 = 0.35;
    spinRate2 = 0.35;
    roll1 = 0.65;
    roll2 = -0.65;
  } else if (hasTrain) {
    const trainIsV1 = v1.type === "train";
    const trainVec = trainIsV1 ? vec1.dir : vec2.dir;
    const trainSpeed = trainIsV1 ? v1_impact : v2_impact;
    const trainRunout = Math.min(26.0, Math.max(15.0, trainSpeed * (totalDuration - impactTime) * 0.65));

    if (trainIsV1) {
      restPos1 = [impactPos1[0] + trainVec[0] * trainRunout, impactPos1[1] + trainVec[1] * trainRunout];
      restPos2 = [impactPos2[0] + trainVec[0] * (trainRunout + 9.5), impactPos2[1] + 5.5];
      spinRate1 = 0;
      spinRate2 = Math.PI * 2.2;
      roll2 = 0.65;
    } else {
      restPos2 = [impactPos2[0] + trainVec[0] * trainRunout, impactPos2[1] + trainVec[1] * trainRunout];
      restPos1 = [impactPos1[0] + trainVec[0] * (trainRunout + 9.5), impactPos1[1] + 5.5];
      spinRate2 = 0;
      spinRate1 = Math.PI * 2.2;
      roll1 = 0.65;
    }
  } else {
    spinRate1 = spinSign * (m2 / (m1 + m2)) * Math.PI * 1.5;
    spinRate2 = -spinSign * (m1 / (m1 + m2)) * Math.PI * 1.8;

    restPos1 = [
      impactPos1[0] + (vec1.dir[0] * 2.5) + (post_vx / (post_speed || 1)) * Math.min(18.0, skidDist),
      impactPos1[1] + (vec1.dir[1] * 2.5) + (post_vz / (post_speed || 1)) * Math.min(18.0, skidDist)
    ];
    restPos2 = [
      impactPos2[0] + (vec2.dir[0] * 2.5) + (post_vx / (post_speed || 1)) * Math.min(18.0, skidDist),
      impactPos2[1] + (vec2.dir[1] * 2.5) + (post_vz / (post_speed || 1)) * Math.min(18.0, skidDist)
    ];

    if (v2.type === "pedestrian") {
      const throwDist = Math.min(14.0, 0.05 * Math.pow(v1_impact * 3.6, 1.3));
      restPos2[0] = poi[0] + vec1.dir[0] * throwDist;
      restPos2[1] = poi[1] + vec1.dir[1] * throwDist;
    }

    roll1 = Math.abs(spinRate1) > 2.2 ? 0.35 * spinSign : 0.0;
    roll2 = Math.abs(spinRate2) > 2.2 ? -0.40 * spinSign : 0.0;
  }

  addSeg(v1.id, "post_collision_spin", impactTime, totalDuration, impactPos1, restPos1, yaw1 + spinRate1, {
    speedKmh: 0,
    damageState: (v1.type === "train" && !isTrainOnTrain && !isDerailment) ? "intact" : "crumpled",
    roll: roll1
  });

  addSeg(v2.id, (v2.type === "pedestrian" ? "pedestrian_thrown" : "post_collision_spin"), impactTime, totalDuration, impactPos2, restPos2, yaw2 + spinRate2, {
    speedKmh: 0,
    damageState: (v2.type === "train" && !isTrainOnTrain && !isDerailment) ? "intact" : "crumpled",
    roll: roll2
  });

  if (!spec1.constrainedToRails && v1.type !== "pedestrian") {
    skidMarks.push({ vehicleId: v1.id, from: impactPos1, to: restPos1, intensity: 0.90 });
  }
  if (spec2 && !spec2.constrainedToRails && v2.type !== "pedestrian") {
    skidMarks.push({ vehicleId: v2.id, from: impactPos2, to: restPos2, intensity: 0.90 });
  }

  const deltaE_Joules = Math.max(0, Math.round(
    0.5 * m1 * Math.pow(v1_impact, 2) + 0.5 * m2 * Math.pow(v2_impact, 2) - 0.5 * (m1 + m2) * Math.pow(post_speed, 2)
  ));
  impacts.push({
    t: impactTime,
    pos: [poi[0], 0.85, poi[1]],
    style: isDerailment ? "train_derailment" : script.crashType,
    energyDissipatedKJ: Math.round(deltaE_Joules / 1000)
  });

  const debrisCount = isTrainOnTrain ? 60 : 35;
  for (let i = 0; i < debrisCount; i++) {
    const angle = Math.random() * Math.PI * 2;
    const r = 0.6 + Math.random() * (isTrainOnTrain ? 8.5 : 5.2);
    debrisField.push({
      pos: [Number((poi[0] + Math.cos(angle) * r).toFixed(3)), 0.02, Number((poi[1] + Math.sin(angle) * r).toFixed(3))],
      type: Math.random() > 0.4 ? "glass_shatter" : "metal_plastic_shard"
    });
  }

  captions.push({
    t: 0.0,
    text: v2.speedKmh === 0
      ? `${v1.name} (${v1.speedKmh} km/h) approaching; ${v2.name} stalled on the railroad crossing.`
      : `${v1.name} (${v1.speedKmh} km/h) approaching; ${v2.name} (${v2.speedKmh} km/h) approaching.`
  });
  if (isBraking1) captions.push({ t: Number((impactTime - brakeDuration1).toFixed(2)), text: `${v1.name} initiates emergency braking; friction deposited.` });
  captions.push({ t: impactTime, text: `IMPACT: ${(script.crashType || "collision").replace(/_/g, " ").toUpperCase()} impact. Energy dissipated: ${Math.round(deltaE_Joules / 1000)} kJ.` });
  if (isTrainOnTrain) {
    captions.push({ t: Number((impactTime + 0.8).toFixed(2)), text: "DERAILMENT: Kinetic impact forces both locomotives off the tracks." });
  } else {
    captions.push({ t: Number((impactTime + 1.2).toFixed(2)), text: "Impulse exchange causes trajectory deflection and kinetic deceleration." });
  }
  captions.push({ t: totalDuration - 0.5, text: "All entities halted at final post-collision resting positions." });

  const exportVehicles = [{ ...spec1, ...v1, type: spec1.type }];
  if (v2 && spec2) exportVehicles.push({ ...spec2, ...v2, type: spec2.type });

  return {
    duration: totalDuration,
    scenarioTitle: script.scenarioTitle,
    crashType: script.crashType,
    weather: script.weather,
    environmentType,
    trainAxis,
    impactTime,
    poi: [poi[0], 0.02, poi[1]],
    tracks,
    skidMarks,
    debrisField,
    impacts,
    captions,
    vehicles: exportVehicles
  };
}