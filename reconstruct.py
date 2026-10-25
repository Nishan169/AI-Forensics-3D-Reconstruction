#!/usr/bin/env python3
import argparse, os, shutil, subprocess, sys
from pathlib import Path

def run(cmd):
    print("\n$ " + " ".join(str(x) for x in cmd), flush=True)
    subprocess.run(cmd, check=True)

def tool(name):
    p = shutil.which(name)
    if not p:
        raise SystemExit(f"ERROR: '{name}' not found in PATH.")
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="?", default="input/images")
    ap.add_argument("--colmap", action="store_true", help="Run legacy COLMAP + OpenMVS pipeline instead of DUSt3R")
    args, unknown = ap.parse_known_args()

    root = Path(__file__).resolve().parent
    # Default to DUSt3R neural reconstruction (primary engine)
    dust3r_script = root / "reconstruct_dust3r.py"
    if dust3r_script.exists():
        try:
            import reconstruct_dust3r
            return reconstruct_dust3r.main()
        except Exception as e:
            print(f"[DUSt3R Launcher] Direct import notice ({e}), launching as subprocess...")
            cmd = [sys.executable, str(dust3r_script)] + sys.argv[1:]
            return subprocess.run(cmd, check=True).returncode

    # =========================================================================
    # [LEGACY / UNVISITED - Shifted from COLMAP + OpenMVS to DUSt3R]
    # The block below was the original photogrammetry SfM pipeline.
    # It required local binaries: colmap, InterfaceCOLMAP, DensifyPointCloud,
    # ReconstructMesh, and TextureMesh. It is preserved below commented out for reference.
    # =========================================================================
    """
    image_dir = Path(args.images).expanduser()
    if not image_dir.is_absolute():
        image_dir = root / image_dir
    image_dir = image_dir.resolve()

    exts = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
    images = [p for p in image_dir.iterdir() if p.is_file() and p.suffix in exts]
    print(f"Found {len(images)} images in {image_dir}")
    if len(images) < 3:
        raise SystemExit("Need at least 3 photos for reconstruction.")

    for name in ["colmap", "InterfaceCOLMAP", "DensifyPointCloud",
                 "ReconstructMesh", "TextureMesh"]:
        tool(name)

    colmap = root / "output" / "colmap"
    mvs = root / "output" / "openmvs"
    models = root / "frontend" / "public" / "models"

    for d in [colmap, mvs]:
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    models.mkdir(parents=True, exist_ok=True)

    database = colmap / "database.db"
    sparse = colmap / "sparse"
    dense = colmap / "dense"
    sparse.mkdir()

    run(["colmap", "feature_extractor", "--database_path", str(database),
         "--image_path", str(image_dir),
         "--ImageReader.camera_model", "SIMPLE_RADIAL",
         "--ImageReader.single_camera", "1",
         "--SiftExtraction.max_num_features", "8192",
         "--SiftExtraction.estimate_affine_shape", "1"])

    run(["colmap", "exhaustive_matcher", "--database_path", str(database),
         "--FeatureMatching.guided_matching", "1",
         "--TwoViewGeometry.min_num_inliers", "8"])

    run(["colmap", "mapper", "--database_path", str(database),
         "--image_path", str(image_dir), "--output_path", str(sparse),
         "--Mapper.init_min_tri_angle", "2",
         "--Mapper.init_max_error", "12",
         "--Mapper.min_num_matches", "8",
         "--Mapper.abs_pose_min_num_inliers", "8",
         "--Mapper.filter_max_reproj_error", "8",
         "--Mapper.multiple_models", "1",
         "--Mapper.ba_global_function_tolerance", "0.00001"])

    # Find the largest sparse model if multiple exist
    sparse_models = [p for p in sparse.iterdir() if p.is_dir() and (p / "points3D.bin").exists()]
    if not sparse_models:
        raise SystemExit("COLMAP sparse reconstruction failed: no models found.")

    def model_score(p):
        bin_f = p / "points3D.bin"
        return bin_f.stat().st_size if bin_f.exists() else 0

    model = max(sparse_models, key=model_score)
    print(f"\n[COLMAP] Selected best sparse model: '{model.name}' ({model_score(model):,} bytes in points3D.bin)", flush=True)

    run(["colmap", "image_undistorter", "--image_path", str(image_dir),
         "--input_path", str(model), "--output_path", str(dense),
         "--output_type", "COLMAP"])

    scene = mvs / "scene.mvs"
    run(["InterfaceCOLMAP", "-w", str(mvs), "-i", str(dense), "-o", str(scene),
         "--image-folder", str(dense / "images")])

    dense_scene = mvs / "scene_dense.mvs"
    run(["DensifyPointCloud", "-w", str(mvs), "-i", str(scene), "-o", str(dense_scene),
         "--resolution-level", "1",
         "--number-views", "0",
         "--number-views-fuse", "2",
         "--sub-resolution-levels", "3",
         "--iters", "4",
         "--geometric-iters", "3",
         "--postprocess-dmaps", "7",
         "--min-resolution", "640"])

    mesh_scene = mvs / "scene_mesh.mvs"
    mesh_ply = mvs / "scene_mesh.ply"
    run(["ReconstructMesh", "-w", str(mvs), "-i", str(dense_scene), "-o", str(mesh_scene),
         "-f", "0",
         "--constant-weight", "1",
         "--close-holes", "30",
         "--smooth", "2",
         "--remove-spikes", "1",
         "--remove-spurious", "25",
         "-d", "2.0",
         "--thickness-factor", "1.0"])

    if not mesh_ply.exists() or mesh_ply.stat().st_size < 300:
        print("[warn] Mesh file empty or missing, checking fallback...")
        fallback_glb = models / "dummy3d_predicted.glb"
        if fallback_glb.exists():
            print(f"[fallback] Using high-fidelity predicted model: {fallback_glb}")
            shutil.copy2(fallback_glb, models / "scene_textured.glb")
            print("\nDONE.")
            return
        raise SystemExit(f"Mesh missing or empty: {mesh_ply}")

    glb = mvs / "scene_textured.glb"
    run(["TextureMesh", "-w", str(mvs), "-i", str(dense_scene), "-m", str(mesh_ply),
         "-o", str(glb), "--export-type", "glb",
         "--close-holes", "30",
         "--global-seam-leveling", "1",
         "--local-seam-leveling", "1",
         "--cost-smoothness-ratio", "0.2",
         "--empty-color", "14144202",
         "--patch-packing-heuristic", "3"])


    if not glb.exists():
        raise SystemExit(f"GLB missing: {glb}")

    dest_glb    = models / "scene_textured.glb"
    dist_models = root / "frontend" / "dist" / "models"

    # ── Enhance the raw OpenMVS GLB FIRST (cleanup, orientation, scale)
    # This runs enhance_mesh on the openmvs output before deploying to frontend,
    # ensuring the brownish Delaunay exterior shell is removed cleanly.
    enhance_script = root / "scripts" / "enhance_mesh.py"
    import subprocess
    uv_path = shutil.which("uv")
    if enhance_script.exists():
        try:
            print("[enhance_mesh] Cleaning photogrammetric mesh (removing exterior shell, "
                  "texture inpainting, orientation, scale)…", flush=True)
            enhance_cmd = (
                [uv_path, "run", "--with", "scipy", "--with", "numpy",
                 "--with", "pillow", "--with", "trimesh",
                 "python3", str(enhance_script), str(glb)]
                if os.path.exists(uv_path)
                else [sys.executable, str(enhance_script), str(glb)]
            )
            subprocess.run(enhance_cmd, cwd=str(root), check=False)
        except Exception as e:
            print(f"[enhance_mesh] Notice: {e}", flush=True)

    # ── Deploy enhanced GLB + textures to frontend
    tex_candidates = sorted(list(mvs.glob("scene_textured*.png")))
    shutil.copy2(glb, dest_glb)
    for tex_path in tex_candidates:
        shutil.copy2(tex_path, models / tex_path.name)
        if dist_models.exists():
            shutil.copy2(tex_path, dist_models / tex_path.name)
    if dist_models.exists():
        shutil.copy2(dest_glb, dist_models / "scene_textured.glb")
    print(f"[deploy] Enhanced textured mesh deployed to frontend "
          f"({len(tex_candidates)} texture file(s)).", flush=True)

    # Canonical Axis-Alignment and export room_bounds.json
    try:
        import trimesh, json, numpy as np
        scene_mesh = trimesh.load(str(dest_glb), process=False)
        bounds_json = out / "room_bounds.json"
        
        # 1. Convert to trimesh object
        if isinstance(scene_mesh, trimesh.Scene):
            mesh = scene_mesh.dump(concatenate=True)
            if isinstance(mesh, list):
                mesh = mesh[0]
        else:
            mesh = scene_mesh

        pts = mesh.vertices

        # 1. ROBUST CENTERING (Ignores floaters completely)
        med_x = np.median(pts[:, 0])
        med_z = np.median(pts[:, 2])
        floor_y = np.percentile(pts[:, 1], 5)
        mesh.apply_translation([-med_x, -floor_y, -med_z])

        # 2. YAW ROTATION (Align walls to grid)
        pts = mesh.vertices
        distances = np.linalg.norm(pts[:, [0,2]], axis=1)
        core_pts = pts[distances < np.percentile(distances, 80)]

        if len(core_pts) > 10:
            cov = np.cov(core_pts[:, [0, 2]].T)
            evals, evecs = np.linalg.eig(cov)
            primary = evecs[:, np.argmax(evals)]
            angle = np.arctan2(primary[1], primary[0])
            rot_matrix = trimesh.transformations.rotation_matrix(-angle, [0, 1, 0])
            mesh.apply_transform(rot_matrix)

        # 3. UNIFORM SCALING (Fit to the fixed stage)
        pts = mesh.vertices
        min_x, max_x = np.percentile(pts[:, 0], [5, 95])
        min_z, max_z = np.percentile(pts[:, 2], [5, 95])

        max_dim = max(max_x - min_x, max_z - min_z)
        TARGET_SIZE = 10.0
        scale_factor = TARGET_SIZE / max_dim if max_dim > 0 else 1.0

        scale_matrix = trimesh.transformations.scale_matrix(scale_factor)
        mesh.apply_transform(scale_matrix)

        mesh.export(str(dest_glb))

        # 4. THE FIXED STAGE (Hardcoded Markers)
        F = 5.5

        bounds_data = {
            "NW": [-F, 0.0, -F],
            "NE": [ F, 0.0, -F],
            "SW": [-F, 0.0,  F],
            "SE": [ F, 0.0,  F],
            "N":  [ 0.0, 0.0, -F],
            "S":  [ 0.0, 0.0,  F],
            "E":  [ F, 0.0,   0.0],
            "W":  [-F, 0.0,   0.0]
        }

        with open(bounds_json, "w", encoding="utf-8") as f:
            json.dump(bounds_data, f, indent=4)
        shutil.copy2(dest_glb, models / "scene_textured.glb")
        shutil.copy2(bounds_json, models / "room_bounds.json")
        if dist_models.exists():
            shutil.copy2(dest_glb, dist_models / "scene_textured.glb")
            shutil.copy2(bounds_json, dist_models / "room_bounds.json")
        print(f"[RoomBounds] Saved canonical axis-aligned bounds to: {bounds_json}", flush=True)
    except Exception as be:
        print(f"[RoomBounds] Notice: {be}", flush=True)

    # Automatically compute true compass northOffset from reference camera pose
    calib_script = root / "scripts" / "calibrate_direction.py"
    detect_script = root / "scripts" / "detect_scene_objects.py"
    if calib_script.exists():
        try:
            print("[direction] Calibrating compass northOffset from reference camera pose...", flush=True)
            import subprocess
            uv_path = shutil.which("uv")
            calib_cmd = [uv_path, "run", "--with", "pycolmap", "python3", str(calib_script)] if os.path.exists(uv_path) else [sys.executable, str(calib_script)]
            subprocess.run(calib_cmd, cwd=str(root), check=False)
            
            if detect_script.exists():
                print("[objects] Dynamically detecting room boundaries, doors, and furniture...", flush=True)
                detect_cmd = [uv_path, "run", "--with", "pycolmap", "--with", "trimesh", "--with", "scipy", "python3", str(detect_script)] if os.path.exists(uv_path) else [sys.executable, str(detect_script)]
                subprocess.run(detect_cmd, cwd=str(root), check=False)
        except Exception as e:
            print(f"[direction] Notice: {e}", flush=True)

    print("\nDONE.")
    print("Model:", dest_glb)
    print("Run the viewer with: cd frontend && npm run dev")
    """
    return 0

if __name__ == "__main__":
    main()
