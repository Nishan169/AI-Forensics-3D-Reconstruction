import express from "express";
import multer from "multer";
import path from "path";
import fs from "fs";
import { spawn } from "child_process";
import { fileURLToPath } from "url";
import cors from "cors";
import { parseCrimeScript, resolveSceneAnchors, generateCrimePlan } from "./crime_planner.js";
import { loadPhysicalSceneObjects } from "./scene_objects.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = 3001;

app.use(cors({ origin: "http://localhost:5173" }));
app.use(express.json());

// Serve generated models statically
app.use("/models", express.static(path.join(__dirname, "frontend/public/models"), {
  setHeaders: (res) => {
    res.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
  }
}));
app.use("/reference", express.static(path.join(__dirname, "input/reference")));
app.use("/input/images", express.static(path.join(__dirname, "input/images")));

// List uploaded scene photos for threat detection pipeline
app.get("/api/scene/images", (req, res) => {
  const dir = path.join(__dirname, "input", "images");
  if (!fs.existsSync(dir)) return res.json({ images: [] });
  const files = fs.readdirSync(dir).filter(f => /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(f));
  res.json({
    images: files.map(f => ({
      name: f,
      url: `/input/images/${f}`
    }))
  });
});

// Cross-platform Python resolver
function getPythonBin() {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  const candidates = [
    path.join(__dirname, "venv", "bin", "python"),
    path.join(__dirname, "venv", "Scripts", "python.exe"),
    path.join(__dirname, ".venv", "bin", "python"),
    path.join(__dirname, ".venv", "Scripts", "python.exe"),
    path.join(__dirname, "threat_backend", "venv", "bin", "python"),
    path.join(__dirname, "threat_backend", "venv", "Scripts", "python.exe"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return process.platform === "win32" ? "python" : "python3";
}

// Ensure threat detection backend is running on port 8000
function ensureThreatBackend() {
  const threatDir = path.join(__dirname, "threat_backend");
  const venvPy = getPythonBin();
  if (fs.existsSync(venvPy) && fs.existsSync(threatDir)) {
    fetch("http://127.0.0.1:8000/api/health")
      .catch(() => {
        console.log("[ThreatBackend] Spawning self-contained threat backend on port 8000...");
        spawn(venvPy, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"], {
          cwd: threatDir,
          detached: true,
          stdio: "ignore"
        }).unref();
      });
  }
}
ensureThreatBackend();

// Threat detection proxy endpoint
const memoryUpload = multer({ storage: multer.memoryStorage() });
app.post("/api/analyze", memoryUpload.single("file"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ detail: "No file provided" });
    }
    const form = new FormData();
    const blob = new Blob([req.file.buffer], { type: req.file.mimetype || "image/jpeg" });
    form.append("file", blob, req.file.originalname);

    const backendRes = await fetch("http://127.0.0.1:8000/api/analyze", {
      method: "POST",
      body: form,
    });
    const data = await backendRes.json();
    return res.status(backendRes.status).json(data);
  } catch (err) {
    console.error("Proxy error /api/analyze:", err);
    return res.status(502).json({ detail: "Threat detection backend unreachable", error: err.message });
  }
});

// Upload storage – scene images → input/images, reference → input/reference
const inputDir = path.join(__dirname, "input", "images");
const refDir   = path.join(__dirname, "input", "reference");
const outputDir = path.join(__dirname, "output");

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    if (file.fieldname === "referenceImage") {
      fs.mkdirSync(refDir, { recursive: true });
      cb(null, refDir);
    } else {
      fs.mkdirSync(inputDir, { recursive: true });
      cb(null, inputDir);
    }
  },
  filename: (req, file, cb) => cb(null, file.originalname),
});
const upload = multer({ storage });

// Keep track of active SSE clients and reconstruction state
let sseClients = [];
let lastStatus = { phase: "idle", log: "", progress: 0, done: false, error: null };

function broadcast(data) {
  const msg = `data: ${JSON.stringify(data)}\n\n`;
  sseClients.forEach((res) => res.write(msg));
}

// Thoroughly clean up earlier models, textures, colmap/openmvs runs, and inputs
function cleanupPreviousModels() {
  try {
    // 1. Clean frontend/public/models (except dummy avatar)
    const publicModelsDir = path.join(__dirname, "frontend", "public", "models");
    if (fs.existsSync(publicModelsDir)) {
      const files = fs.readdirSync(publicModelsDir);
      for (const f of files) {
        if (f.startsWith("scene_textured")) {
          try { fs.unlinkSync(path.join(publicModelsDir, f)); } catch (_) {}
        }
      }
    }

    // 2. Clean frontend/dist/models (if built)
    const distModelsDir = path.join(__dirname, "frontend", "dist", "models");
    if (fs.existsSync(distModelsDir)) {
      const files = fs.readdirSync(distModelsDir);
      for (const f of files) {
        if (f.startsWith("scene_textured")) {
          try { fs.unlinkSync(path.join(distModelsDir, f)); } catch (_) {}
        }
      }
    }

    // 3. Clean input directories
    for (const dir of [inputDir, refDir]) {
      if (fs.existsSync(dir)) {
        fs.rmSync(dir, { recursive: true, force: true });
        fs.mkdirSync(dir, { recursive: true });
      }
    }

    // 4. Clean output directory (colmap, openmvs, all json files)
    if (fs.existsSync(outputDir)) {
      const outFiles = fs.readdirSync(outputDir);
      for (const f of outFiles) {
        const p = path.join(outputDir, f);
        try {
          fs.rmSync(p, { recursive: true, force: true });
        } catch (_) {}
      }
      fs.mkdirSync(outputDir, { recursive: true });
    }

    lastStatus = { phase: "idle", log: "", progress: 0, done: false, error: null };
    broadcast(lastStatus);
    console.log("[Cleanup] Previous models, textures, and artifacts cleaned up successfully.");
  } catch (err) {
    console.error("[Cleanup] Error cleaning previous models:", err);
  }
}

// SSE endpoint – frontend connects here to receive live logs
app.get("/api/status", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();

  // Send current state immediately on connect
  res.write(`data: ${JSON.stringify(lastStatus)}\n\n`);
  sseClients.push(res);

  req.on("close", () => {
    sseClients = sseClients.filter((c) => c !== res);
  });
});

// Upload endpoint – accepts scene images + optional referenceImage + direction
app.post("/api/upload",
  upload.fields([
    { name: "images",         maxCount: 500 },
    { name: "referenceImage", maxCount: 1   },
  ]),
  (req, res) => {
    const sceneFiles = req.files["images"] || [];
    const refFiles   = req.files["referenceImage"] || [];
    const direction  = req.body.direction || "N";

    if (sceneFiles.length === 0) {
      return res.status(400).json({ error: "No scene images uploaded" });
    }

    const metaPath = path.join(outputDir, "direction.json");
    let existingMeta = {};
    if (fs.existsSync(metaPath)) {
      try { existingMeta = JSON.parse(fs.readFileSync(metaPath, "utf8")); } catch (_) {}
    }

    const refImageName = refFiles[0]?.originalname || existingMeta.referenceImage || (sceneFiles[0]?.originalname ?? null);

    // Persist direction metadata without destroying existing calibration
    const meta = {
      ...existingMeta,
      direction,
      referenceImage: refImageName,
      timestamp: new Date().toISOString(),
    };

    if (meta.northOffset === undefined) {
      meta.angle = { N:0,NE:45,E:90,SE:135,S:180,SW:225,W:270,NW:315 }[direction] ?? 0;
    }

    fs.mkdirSync(outputDir, { recursive: true });
    fs.writeFileSync(metaPath, JSON.stringify(meta, null, 2));

    // Auto-calibrate direction if camera poses exist from neural reconstruction or COLMAP
    const dust3rPoses = path.join(outputDir, "camera_poses.json");
    const colmapDir = path.join(outputDir, "colmap", "sparse", "0");
    if ((fs.existsSync(dust3rPoses) || fs.existsSync(colmapDir)) && refImageName) {
      const pythonCmd = getPythonBin();
      const scriptPath = path.join(__dirname, "scripts", "calibrate_direction.py");
      const py = spawn(pythonCmd, [scriptPath, refImageName, direction], { cwd: __dirname });
      py.on("close", () => {
        console.log(`[Upload] Auto-calibrated direction for ${refImageName} facing ${direction}`);
      });
    }

    res.json({
      sceneCount: sceneFiles.length,
      referenceImage: refImageName,
      direction,
      message: `${sceneFiles.length} scene images + direction "${direction}" saved`,
    });
  }
);

// Direction metadata endpoint
app.get("/api/direction", (req, res) => {
  const metaPath = path.join(outputDir, "direction.json");
  if (!fs.existsSync(metaPath)) {
    return res.status(404).json({ error: "No direction metadata found" });
  }
  try {
    const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
    if (meta.referenceImage) {
      const refFileOnDisk = path.join(refDir, meta.referenceImage);
      const inputFileOnDisk = path.join(inputDir, meta.referenceImage);
      if (fs.existsSync(refFileOnDisk) || fs.existsSync(inputFileOnDisk)) {
        meta.referenceImageUrl = `/reference/${meta.referenceImage}`;
      }
    }
    res.json(meta);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Calibrate direction from reference photo or manual compass azimuth
app.post("/api/direction/calibrate", (req, res) => {
  try {
    const { referenceImage, direction, northOffset } = req.body;
    const metaPath = path.join(outputDir, "direction.json");
    let dirMeta = {};
    if (fs.existsSync(metaPath)) {
      try { dirMeta = JSON.parse(fs.readFileSync(metaPath, "utf8")); } catch (_) {}
    }
    if (direction) dirMeta.direction = direction;
    if (referenceImage) dirMeta.referenceImage = referenceImage;
    if (northOffset !== undefined) {
      dirMeta.northOffset = Number(northOffset);
      dirMeta.angle = Number(northOffset);
      dirMeta.calibrated = true;
      dirMeta.timestamp = new Date().toISOString();
      fs.writeFileSync(metaPath, JSON.stringify(dirMeta, null, 2));
      return res.json(dirMeta);
    }
    // Run python camera pose calibrator
    const pythonCmd = getPythonBin();
    const scriptPath = path.join(__dirname, "scripts", "calibrate_direction.py");
    const detectPath = path.join(__dirname, "scripts", "detect_scene_objects.py");
    const py = spawn(pythonCmd, [scriptPath, dirMeta.referenceImage || "", dirMeta.direction || "N"], { cwd: __dirname });
    py.on("close", () => {
      // Refresh dynamic scene objects with new northOffset
      if (fs.existsSync(detectPath)) {
        const detectPy = spawn(pythonCmd, [detectPath], { cwd: __dirname });
        detectPy.on("close", () => {
          let updated = dirMeta;
          if (fs.existsSync(metaPath)) {
            try { updated = JSON.parse(fs.readFileSync(metaPath, "utf8")); } catch (_) {}
          }
          res.json(updated);
        });
      } else {
        let updated = dirMeta;
        if (fs.existsSync(metaPath)) {
          try { updated = JSON.parse(fs.readFileSync(metaPath, "utf8")); } catch (_) {}
        }
        res.json(updated);
      }
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Scene physical objects & 8-direction labels endpoint
app.get("/api/scene/objects", (req, res) => {
  try {
    const dirPath = path.join(outputDir, "direction.json");
    let dirMeta = {};
    if (fs.existsSync(dirPath)) {
      try { dirMeta = JSON.parse(fs.readFileSync(dirPath, "utf8")); } catch (_) {}
    }
    const northOffset = dirMeta.northOffset ?? dirMeta.angle ?? 0;
    const bmPath = path.join(outputDir, "boundary_markers.json");
    let boundaryMarkers = null;
    if (fs.existsSync(bmPath)) {
      try { boundaryMarkers = JSON.parse(fs.readFileSync(bmPath, "utf8")); } catch (_) {}
    }
    const objects = loadPhysicalSceneObjects(null, null, northOffset, boundaryMarkers);
    res.json({ objects, northOffset, direction: dirMeta.direction || "N", boundaryMarkers });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── 3D Mesh Enhancement & Artifact Purge Endpoint ─────────────────────
app.post("/api/mesh/enhance", (req, res) => {
  try {
    const pythonCmd = getPythonBin();
    const scriptPath = path.join(__dirname, "scripts", "enhance_mesh.py");
    const glbPath = path.join(__dirname, "frontend", "public", "models", "scene_textured.glb");

    const py = spawn(pythonCmd, [scriptPath, glbPath], {
      cwd: __dirname
    });

    let stdout = "";
    let stderr = "";
    py.stdout.on("data", (d) => stdout += d.toString());
    py.stderr.on("data", (d) => stderr += d.toString());

    py.on("close", (code) => {
      if (code !== 0) {
        return res.status(500).json({ error: `Mesh enhancement failed: ${stderr}` });
      }

      // Automatically detect room boundaries and regenerate navgrid + scene objects for the enhanced mesh
      const detectPath = path.join(__dirname, "scripts", "detect_scene_objects.py");
      if (fs.existsSync(detectPath)) {
        spawn(pythonCmd, [detectPath], { cwd: __dirname });
      }

      try {
        // Find last json output
        const lines = stdout.trim().split("\n");
        const jsonStart = lines.findIndex(l => l.trim().startsWith("{"));
        const report = jsonStart >= 0 ? JSON.parse(lines.slice(jsonStart).join("\n")) : { success: true };
        res.json({ success: true, report });
      } catch (_) {
        res.json({ success: true, stdout });
      }
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Reconstruct endpoint – runs reconstruct.py and streams output
app.post("/api/reconstruct", (req, res) => {
  // Purge any earlier models before building new mesh
  const publicModelsDir = path.join(__dirname, "frontend", "public", "models");
  if (fs.existsSync(publicModelsDir)) {
    for (const f of fs.readdirSync(publicModelsDir)) {
      if (f.startsWith("scene_textured")) {
        try { fs.unlinkSync(path.join(publicModelsDir, f)); } catch (_) {}
      }
    }
  }
  const distModelsDir = path.join(__dirname, "frontend", "dist", "models");
  if (fs.existsSync(distModelsDir)) {
    for (const f of fs.readdirSync(distModelsDir)) {
      if (f.startsWith("scene_textured")) {
        try { fs.unlinkSync(path.join(distModelsDir, f)); } catch (_) {}
      }
    }
  }

  lastStatus = { phase: "starting", log: "Starting reconstruction…", progress: 0, done: false, error: null };
  broadcast(lastStatus);

  res.json({ message: "Reconstruction started" });

  const pythonCmd = getPythonBin();
  const scriptPath = fs.existsSync(path.join(__dirname, "reconstruct_dust3r.py"))
    ? path.join(__dirname, "reconstruct_dust3r.py")
    : path.join(__dirname, "reconstruct.py");

  const python = spawn(pythonCmd, [scriptPath], {
    cwd: __dirname,
  });

  const PHASES = [
    // DUSt3R Neural Reconstruction Phases
    { match: "[Device]", label: "Detecting hardware accelerator", progress: 5 },
    { match: "[DUSt3R] Loading model", label: "Loading DUSt3R neural weights", progress: 15 },
    { match: "[DUSt3R] Constructing image pairs", label: "Constructing image pairs", progress: 25 },
    { match: "[DUSt3R] Running pairwise", label: "Predicting dense 3D pointmaps", progress: 40 },
    { match: "[Global Alignment] Optimizing", label: "Global alignment & coordinate fusion", progress: 65 },
    { match: "[Open3D] Initializing point cloud", label: "Open3D point cloud filtering", progress: 75 },
    { match: "[Open3D] Running Poisson", label: "Poisson surface reconstruction", progress: 85 },
    { match: "[Open3D] Transferring photographic", label: "Transferring photographic colors", progress: 92 },
    { match: "[Export]", label: "Exporting textured GLB digital twin", progress: 98 },

    // COLMAP / OpenMVS SfM Phases
    { match: "feature_extractor", label: "Extracting features", progress: 10 },
    { match: "exhaustive_matcher", label: "Matching features", progress: 20 },
    { match: "mapper", label: "Sparse reconstruction (COLMAP)", progress: 35 },
    { match: "image_undistorter", label: "Undistorting images", progress: 45 },
    { match: "InterfaceCOLMAP", label: "Interfacing COLMAP → OpenMVS", progress: 55 },
    { match: "DensifyPointCloud", label: "Densifying point cloud", progress: 68 },
    { match: "ReconstructMesh", label: "Reconstructing mesh", progress: 80 },
    { match: "TextureMesh", label: "Texturing mesh", progress: 90 },
    { match: "enhance_mesh", label: "Predicting & smoothing room geometry", progress: 96 },
    { match: "DONE", label: "Done!", progress: 100 },
  ];

  function handleLine(line) {
    let update = { ...lastStatus, log: line };
    for (const p of PHASES) {
      if (line.includes(p.match)) {
        update.phase = p.label;
        update.progress = p.progress;
        break;
      }
    }
    lastStatus = update;
    broadcast(lastStatus);
  }

  python.stdout.on("data", (chunk) => {
    chunk.toString().split("\n").filter(Boolean).forEach(handleLine);
  });
  python.stderr.on("data", (chunk) => {
    chunk.toString().split("\n").filter(Boolean).forEach(handleLine);
  });

  python.on("close", (code) => {
    if (code === 0) {
      // Auto-calibrate direction right after reconstruction completes
      const scriptPath = path.join(__dirname, "scripts", "calibrate_direction.py");
      const metaPath = path.join(outputDir, "direction.json");
      let dMeta = {};
      if (fs.existsSync(metaPath)) {
        try { dMeta = JSON.parse(fs.readFileSync(metaPath, "utf8")); } catch (_) {}
      }
      const calibPy = spawn(pythonCmd, [scriptPath, dMeta.referenceImage || "", dMeta.direction || "N"], { cwd: __dirname });
      const detectPath = path.join(__dirname, "scripts", "detect_scene_objects.py");
      const finalizeReconstruction = () => {
        try {
          const syncFiles = [
            "scene_textured.glb",
            "boundary_markers.json",
            "direction.json",
            "scene_objects.json",
            "navgrid.json",
            "camera_poses.json",
            "room_bounds.json"
          ];
          for (const fname of syncFiles) {
            const srcFile = path.join(outputDir, fname);
            const pubFile = path.join(__dirname, "frontend", "public", "models", fname);
            const distFile = path.join(__dirname, "frontend", "dist", "models", fname);
            if (fs.existsSync(srcFile)) {
              fs.mkdirSync(path.dirname(pubFile), { recursive: true });
              fs.copyFileSync(srcFile, pubFile);
              if (fs.existsSync(path.dirname(distFile))) {
                fs.copyFileSync(srcFile, distFile);
              }
            }
          }

          const dirPath = path.join(outputDir, "direction.json");
          let dirMeta = {};
          if (fs.existsSync(dirPath)) {
            try { dirMeta = JSON.parse(fs.readFileSync(dirPath, "utf8")); } catch (_) {}
          }
          const northOffset = dirMeta.northOffset ?? dirMeta.angle ?? 0;

          const bmPath = path.join(outputDir, "boundary_markers.json");
          let boundaryMarkers = null;
          if (fs.existsSync(bmPath)) {
            try { boundaryMarkers = JSON.parse(fs.readFileSync(bmPath, "utf8")); } catch (_) {}
          }

          const objects = loadPhysicalSceneObjects(null, null, northOffset, boundaryMarkers);

          lastStatus = {
            phase: "complete",
            log: "Reconstruction complete, compass calibrated, and room objects detected!",
            progress: 100,
            done: true,
            error: null,
            boundaryMarkers,
            northOffset,
            direction: dirMeta.direction || "N",
            objects
          };
          broadcast(lastStatus);
          console.log(`[Reconstruct Complete] Synchronized models and broadcasted aligned markers (northOffset: ${northOffset}°).`);
        } catch (fErr) {
          console.error("[Reconstruct Complete] Notice during artifact finalization:", fErr);
          lastStatus = {
            phase: "complete",
            log: "Reconstruction complete!",
            progress: 100,
            done: true,
            error: null,
          };
          broadcast(lastStatus);
        }
      };

      calibPy.on("close", () => {
        if (fs.existsSync(detectPath)) {
          const detectPy = spawn(pythonCmd, [detectPath], { cwd: __dirname });
          detectPy.on("close", () => {
            finalizeReconstruction();
          });
        } else {
          finalizeReconstruction();
        }
      });
    } else {
      lastStatus = {
        phase: "error",
        log: `Process exited with code ${code}`,
        progress: 0,
        done: false,
        error: `Reconstruction failed (exit code ${code})`,
      };
      broadcast(lastStatus);
    }
  });
});

// Reset endpoint – thoroughly cleans up previous models, textures, colmap/openmvs, input and metadata
app.post("/api/reset", (req, res) => {
  try {
    cleanupPreviousModels();
    res.json({ message: "Reset and cleanup complete" });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});


// ── Manual Room Orientation Flip Endpoint ────────────────────────────
app.post("/api/flip-model", (req, res) => {
  const pythonCmd = getPythonBin();
  const scriptPath = path.join(__dirname, "flip_glb.py");

  if (!fs.existsSync(scriptPath)) {
    return res.status(500).json({ success: false, error: "flip_glb.py script not found" });
  }

  console.log(`[FlipModel] Running: ${pythonCmd} ${scriptPath}`);
  const py = spawn(pythonCmd, [scriptPath], { cwd: __dirname });

  let stderr = "";
  py.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  py.on("close", (code) => {
    if (code !== 0) {
      console.error(`[FlipModel] Exited with code ${code}: ${stderr}`);
      return res.status(500).json({ success: false, error: `flip_glb.py failed: ${stderr}` });
    }

    try {
      const syncFiles = [
        "scene_textured.glb",
        "boundary_markers.json",
        "direction.json",
        "scene_objects.json",
        "navgrid.json",
        "room_bounds.json"
      ];

      for (const fname of syncFiles) {
        const srcFile = path.join(outputDir, fname);
        const pubFile = path.join(__dirname, "frontend", "public", "models", fname);
        const distFile = path.join(__dirname, "frontend", "dist", "models", fname);

        if (fs.existsSync(srcFile)) {
          fs.mkdirSync(path.dirname(pubFile), { recursive: true });
          fs.copyFileSync(srcFile, pubFile);
          if (fs.existsSync(path.dirname(distFile))) {
            fs.copyFileSync(srcFile, distFile);
          }
        }
      }

      const dirPath = path.join(outputDir, "direction.json");
      let dirMeta = {};
      if (fs.existsSync(dirPath)) {
        try { dirMeta = JSON.parse(fs.readFileSync(dirPath, "utf8")); } catch (_) {}
      }
      const northOffset = dirMeta.northOffset ?? dirMeta.angle ?? 0;

      const bmPath = path.join(outputDir, "boundary_markers.json");
      let boundaryMarkers = null;
      if (fs.existsSync(bmPath)) {
        try { boundaryMarkers = JSON.parse(fs.readFileSync(bmPath, "utf8")); } catch (_) {}
      }

      const objects = loadPhysicalSceneObjects(null, null, northOffset, boundaryMarkers);

      console.log(`[FlipModel] Flipped successfully: northOffset = ${northOffset}°, markers updated.`);
      return res.status(200).json({
        success: true,
        message: "Model flipped and directions reassigned successfully",
        northOffset,
        direction: dirMeta.direction || "N",
        boundaryMarkers,
        objects
      });
    } catch (copyErr) {
      console.error("[FlipModel] Error synchronizing flipped model:", copyErr);
      return res.status(500).json({ success: false, error: copyErr.message });
    }
  });

  py.on("error", (err) => {
    console.error("[FlipModel] Spawn error:", err);
    return res.status(500).json({ success: false, error: err.message });
  });
});

// ── Forensic Crime Scene Recreation & Video Planning Endpoint ────────
app.post("/api/recreation/plan", async (req, res) => {
  try {
    const { prompt, apiKey, bounds, directionMeta, boundaryMarkers } = req.body;
    if (!prompt || typeof prompt !== "string") {
      return res.status(400).json({ error: "Missing or invalid prompt string" });
    }

    // Persist incoming boundaryMarkers matching active 3D model only if not already present on disk
    const bmFile = path.join(outputDir, "boundary_markers.json");
    if (!fs.existsSync(bmFile) && boundaryMarkers && typeof boundaryMarkers === "object" && Object.keys(boundaryMarkers).length > 0) {
      try {
        fs.mkdirSync(outputDir, { recursive: true });
        fs.writeFileSync(bmFile, JSON.stringify(boundaryMarkers, null, 2));
      } catch (bmErr) {
        console.warn("[server] Could not persist boundary_markers.json:", bmErr.message);
      }
    }

    // Load saved direction metadata if none passed
    let effectiveDirMeta = directionMeta;
    if (!effectiveDirMeta) {
      const dirPath = path.join(outputDir, "direction.json");
      if (fs.existsSync(dirPath)) {
        try {
          effectiveDirMeta = JSON.parse(fs.readFileSync(dirPath, "utf8"));
        } catch (_) {}
      }
    }

    // 1. Parse prompt into structured action script (Gemini or Rule-based)
    const { script, source } = await parseCrimeScript(prompt, apiKey);

    // 2. Resolve 3D anchors given scene bounds, cardinal compass calibration, and physical boundary markers
    const { anchors, bounds: effectiveBounds, center, verificationReport, physicalObjects, northOffset, boundaryMarkers: resolvedMarkers } = resolveSceneAnchors(script, bounds, effectiveDirMeta, null, boundaryMarkers);

    // 3. Generate kinematic simulation tracks, timed impacts, and captions
    const plan = generateCrimePlan(script, anchors, effectiveBounds, center, null, verificationReport, physicalObjects, resolvedMarkers);

    const result = {
      success: true,
      prompt,
      source,
      script,
      anchors,
      plan,
      bounds: effectiveBounds,
      center,
      boundaryMarkers: resolvedMarkers,
      verificationReport,
      physicalObjects,
      northOffset,
      timestamp: new Date().toISOString()
    };

    // Persist recreation plan
    fs.mkdirSync(outputDir, { recursive: true });
    fs.writeFileSync(path.join(outputDir, "recreation_plan.json"), JSON.stringify(result, null, 2));

    res.json(result);
  } catch (err) {
    console.error("Crime recreation planning error:", err);
    res.status(500).json({ error: err.message || "Failed to generate crime recreation plan" });
  }
});

// Retrieve latest recreation plan
app.get("/api/recreation/plan", (req, res) => {
  const planPath = path.join(outputDir, "recreation_plan.json");
  if (!fs.existsSync(planPath)) {
    return res.status(404).json({ error: "No recreation plan found" });
  }
  try {
    const data = JSON.parse(fs.readFileSync(planPath, "utf8"));
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: "Failed to read recreation plan" });
  }
});

app.listen(PORT, () => {
  console.log(`Forensic 3D backend running at http://localhost:${PORT}`);
});

