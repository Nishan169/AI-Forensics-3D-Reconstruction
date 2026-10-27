#!/usr/bin/env python3
"""
Forensic Spatial Analyzer - DUSt3R Neural 3D Reconstruction Backend
===================================================================
A self-contained, cross-platform neural 3D reconstruction script that pivots
from the fragile COLMAP + OpenMVS structure-from-motion pipeline to DUSt3R
(Dense and Unconstrained Stereo 3D Reconstruction).

Key Capabilities:
  1. Hardware-Agnostic Setup: Auto-detects NVIDIA CUDA, Apple Silicon MPS, or CPU.
  2. Neural Pairwise Inference: Predicts dense 3D pointmaps and confidence maps
     directly from sparse, unconstrained image sets.
  3. Global Alignment Optimization: Solves for globally consistent camera poses
     and fused coordinate spaces using Minimum Spanning Tree (MST) + gradient descent.
  4. Open3D Mesh Generation: Outlier removal, adaptive voxel downsampling,
     tangent-plane normal estimation, Poisson Surface Reconstruction, and fast
     KDTree photographic color transfer.
  5. Cross-Platform GLB Export: Directly writes scene_textured.glb for the
     React Three Fiber digital twin viewer.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Enable PyTorch MPS fallback for Apple Silicon before torch loads
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
# Force single-threaded OpenMP to prevent PoissonRecon multi-threading race conditions (code 134)
os.environ["OMP_NUM_THREADS"] = "1"


# =====================================================================
# 0. Auto-Switch to Local Virtual Environment (if torch is missing)
# =====================================================================
def auto_switch_venv():
    try:
        import torch  # noqa: F401
        return
    except ImportError:
        pass

    root = Path(__file__).resolve().parent
    candidates = [
        root / "venv" / "bin" / "python",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.is_file() and os.path.abspath(sys.executable) != os.path.abspath(str(cand)):
            print(f"[Launcher] Environment auto-detected: switching to {cand} ...")
            os.execv(str(cand), [str(cand)] + sys.argv)

auto_switch_venv()
import numpy as np


# =====================================================================
# 1. Self-Bootstrapping DUSt3R Dependency Loader
# =====================================================================
def ensure_dust3r(root_dir: Path):
    """
    Ensures the DUSt3R library is accessible on sys.path.
    If not installed via pip, checks local directories or clones the official
    repository with submodules automatically.
    """
    try:
        import dust3r  # noqa: F401
        return
    except ImportError:
        pass

    candidates = [
        root_dir / "dust3r",
        root_dir / "third_party" / "dust3r",
        Path.home() / "dust3r",
    ]

    for cand in candidates:
        if (cand / "dust3r").is_dir():
            print(f"[DUSt3R] Located local DUSt3R repository at: {cand}")
            sys.path.insert(0, str(cand))
            croco_dir = cand / "croco"
            if croco_dir.is_dir():
                sys.path.insert(0, str(croco_dir))
            try:
                import dust3r  # noqa: F401
                return
            except ImportError:
                pass

    # If still not found, attempt automatic recursive clone into third_party/dust3r
    clone_dest = root_dir / "third_party" / "dust3r"
    git_bin = shutil.which("git")
    if git_bin and not clone_dest.exists():
        print("[DUSt3R] DUSt3R package not found in Python path.")
        print(f"[DUSt3R] Automatically cloning naver/dust3r into: {clone_dest} ...")
        clone_dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [git_bin, "clone", "--recursive", "https://github.com/naver/dust3r.git", str(clone_dest)],
                check=True,
            )
            sys.path.insert(0, str(clone_dest))
            croco_dir = clone_dest / "croco"
            if croco_dir.is_dir():
                sys.path.insert(0, str(croco_dir))
            import dust3r  # noqa: F401
            print("[DUSt3R] Repository cloned and imported successfully.")
            return
        except Exception as e:
            print(f"[DUSt3R] Notice: Automatic clone failed ({e}).")

    print("[DUSt3R] WARNING: 'dust3r' is not imported. Please install via:")
    print("         git clone --recursive https://github.com/naver/dust3r.git third_party/dust3r")
    print("         pip install -r requirements.txt")


# =====================================================================
# 2. Hardware-Agnostic Device Detection
# =====================================================================
def detect_device(preferred: str = "auto"):
    """
    Dynamically detects the best available PyTorch compute device:
      1. NVIDIA CUDA ('cuda')
      2. Apple Silicon Metal Performance Shaders ('mps')
      3. Fallback CPU ('cpu')
    """
    import torch

    pref = preferred.lower().strip()
    if pref != "auto":
        dev = torch.device(pref)
        print(f"[Device] User specified override: {dev}")
        return dev

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        dev = torch.device("cuda")
        print(f"[Device] NVIDIA CUDA detected: {gpu_name} ({vram_gb:.1f} GB VRAM)")
        return dev

    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        try:
            # Perform a quick allocation test to guarantee MPS backend responsiveness
            _test = torch.zeros((1,), device="mps")
            dev = torch.device("mps")
            print("[Device] Apple Silicon Metal Performance Shaders (MPS) detected.")
            return dev
        except Exception as e:
            print(f"[Device] MPS available but allocation check failed ({e}); falling back to CPU.")

    dev = torch.device("cpu")
    print("[Device] No hardware accelerator detected; running on CPU.")
    return dev


# =====================================================================
# 3. Open3D Poisson Mesh Reconstruction
# =====================================================================
def generate_poisson_mesh(
    point_cloud_xyz,
    point_cloud_rgb,
    poisson_depth: int = 9,
    density_quantile: float = 0.03,
    voxel_size: float = 0.0,
):
    """
    Passes fused 3D points and RGB colors into Open3D:
      - Statistical outlier removal
      - Adaptive voxel downsampling
      - Consistent tangent-plane normal estimation
      - Watertight Poisson surface reconstruction
      - Low-density artifact trimming
      - Fast KDTree photographic color transfer
    """
    import numpy as np
    import open3d as o3d
    from scipy.spatial import cKDTree

    print(f"[Open3D] Initializing point cloud with {len(point_cloud_xyz):,} points...")
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(point_cloud_xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(point_cloud_rgb.astype(np.float64))

    # Remove non-finite entries and stray statistical outliers
    pcd.remove_non_finite_points()
    print("[Open3D] Removing statistical outliers (nb_neighbors=25, std_ratio=2.0)...")
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=25, std_ratio=2.0)
    print(f"[Open3D] Cleaned point cloud: {len(pcd.points):,} points.")

    # 1. Preserve Dense Cloud: Save an un-downsampled copy for high-fidelity color transfer
    dense_pcd = o3d.geometry.PointCloud(pcd)
    print(f"[Open3D Color] Preserved un-downsampled dense point cloud ({len(dense_pcd.points):,} points) for color transfer.")

    # Adaptive voxel downsampling
    bbox = pcd.get_axis_aligned_bounding_box()
    extent = bbox.get_extent()
    diag = float(np.linalg.norm(extent))
    if voxel_size <= 0.0:
        voxel_size = max(0.008, diag / 250.0)
    print(f"[Open3D] Downsampling point cloud with voxel_size={voxel_size:.4f}...")
    pcd_down = pcd.voxel_down_sample(voxel_size=voxel_size)
    print(f"[Open3D] Downsampled point cloud: {len(pcd_down.points):,} points.")

    # Normal estimation
    radius_normal = voxel_size * 3.0
    print(f"[Open3D] Estimating point normals (radius={radius_normal:.4f}, max_nn=30)...")
    pcd_down.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=radius_normal, max_nn=30)
    )
    pcd_down.normalize_normals()

    print("[Open3D] Orienting normals consistently using tangent planes (k=15)...")
    try:
        pcd_down.orient_normals_consistent_tangent_plane(k=15)
    except Exception as e:
        print(f"[Open3D] Tangent plane orientation notice ({e}); orienting towards centroid...")
        pcd_down.orient_normals_towards_camera_location(pcd_down.get_center())

    # Poisson Surface Reconstruction with single-threaded stability (n_threads=1, linear_fit=False avoids PoissonRecon code 134 race conditions)
    mesh = None
    densities = None
    depth_candidates = [poisson_depth]
    for fallback_d in [8, 7]:
        if fallback_d not in depth_candidates and fallback_d <= poisson_depth:
            depth_candidates.append(fallback_d)

    for depth_val in depth_candidates:
        try:
            print(f"[Open3D] Running Poisson Surface Reconstruction (depth={depth_val}, scale=1.1, linear_fit=False, n_threads=1)...")
            m, d = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                pcd_down,
                depth=depth_val,
                scale=1.1,
                linear_fit=False,
                n_threads=1,
            )
            if len(m.vertices) > 0 and len(m.triangles) > 0:
                mesh, densities = m, d
                print(f"[Open3D] Poisson reconstruction succeeded at depth={depth_val}: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} faces.")
                break
        except Exception as err:
            print(f"[Open3D] Notice: Poisson at depth={depth_val} encountered error ({err}). Trying fallback...")

    # Fallback to Ball Pivoting if Poisson fails
    if mesh is None or len(mesh.triangles) == 0:
        print("[Open3D] Falling back to robust Ball Pivoting Algorithm (BPA)...")
        radii = [voxel_size * 1.5, voxel_size * 2.5, voxel_size * 4.0]
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd_down, o3d.utility.DoubleVector(radii)
        )
        densities = np.array([])

    # Trim Poisson Extrapolation: cut away unobserved/melted artificial geometry (e.g. ceilings, voids)
    densities_arr = np.asarray(densities)
    if len(densities_arr) > 0 and density_quantile > 0.0:
        threshold = float(np.quantile(densities_arr, density_quantile))
        print(f"[Open3D] Trimming Poisson extrapolation (density threshold @ quantile {density_quantile:.2f} = {threshold:.3f})...")
        vertices_to_remove = densities_arr < threshold
        mesh.remove_vertices_by_mask(vertices_to_remove)
        print(f"[Open3D] Trimmed mesh: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} faces.")

    # Remove any detached zero-area faces or degenerate triangles
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()

    # 2. KDTree Color Transfer from Dense Point Cloud
    print(f"[Open3D Color] Transferring high-fidelity colors from dense cloud ({len(dense_pcd.points):,} points)...")
    mesh_verts = np.asarray(mesh.vertices)
    dense_pts = np.asarray(dense_pcd.points)
    dense_cols = np.asarray(dense_pcd.colors)

    if len(dense_cols) > 0 and len(mesh_verts) > 0:
        # Query nearest color from the un-downsampled dense point cloud
        try:
            tree = cKDTree(dense_pts)
            _, nn_indices = tree.query(mesh_verts, k=1)
            raw_colors = dense_cols[nn_indices]
        except Exception:
            kdtree = o3d.geometry.KDTreeFlann(dense_pcd)
            raw_colors = np.zeros((len(mesh_verts), 3), dtype=np.float64)
            for i, v in enumerate(mesh_verts):
                _, idx, _ = kdtree.search_knn_vector_3d(v, 1)
                raw_colors[i] = dense_cols[idx[0]]

        # Strictly format as float64 and clip between [0.0, 1.0] without gamma distortion
        # (DUSt3R image colors are already in sRGB space)
        final_colors = np.clip(raw_colors.astype(np.float64), 0.0, 1.0)
        mesh.vertex_colors = o3d.utility.Vector3dVector(final_colors)
        print(f"[Open3D Color] Assigned natural photographic colors to all {len(mesh_verts):,} mesh vertices.")

    # 3. GLTF Material Fix: Compute vertex normals for proper lighting interaction
    mesh.compute_vertex_normals()
    return mesh


# =====================================================================
# 4. GLB Model Exporter
# =====================================================================
def align_and_export_room(scene, glb_output_path, json_output_path):
    if isinstance(scene, trimesh.Scene):
        dumped = scene.dump(concatenate=True)
        mesh = dumped[0] if isinstance(dumped, list) else dumped
    elif hasattr(scene, 'triangles') and hasattr(scene, 'vertices') and not isinstance(scene, trimesh.Trimesh):
        mesh = trimesh.Trimesh(vertices=np.asarray(scene.vertices), faces=np.asarray(scene.triangles))
    else:
        mesh = scene

    pts = mesh.vertices

    # 1. ROBUST CENTERING (Ignores floaters completely)
    # Median completely ignores extreme floating vertices
    med_x = np.median(pts[:, 0])
    med_z = np.median(pts[:, 2])
    # 5th percentile finds the true floor ignoring downward noise spikes
    floor_y = np.percentile(pts[:, 1], 5)
    mesh.apply_translation([-med_x, -floor_y, -med_z])

    # 2. YAW ROTATION (Align walls to grid)
    # Filter points to only use the dense inner 80% of the room for rotation
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
    # Find the true walls using 5th and 95th percentiles
    min_x, max_x = np.percentile(pts[:, 0], [5, 95])
    min_z, max_z = np.percentile(pts[:, 2], [5, 95])

    max_dim = max(max_x - min_x, max_z - min_z)
    TARGET_SIZE = 10.0 # Force the room to be exactly 10 units max
    scale_factor = TARGET_SIZE / max_dim if max_dim > 0 else 1.0

    # Scale uniformly to preserve forensic proportions
    scale_matrix = trimesh.transformations.scale_matrix(scale_factor)
    mesh.apply_transform(scale_matrix)

    # Export normalized model
    mesh.export(glb_output_path)

    # 4. THE FIXED STAGE (Hardcoded Markers)
    # Because the room is now perfectly scaled to 10 units, we can hardcode 
    # the markers at 5.5 to create a permanent, beautiful perimeter.
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

    out_json = Path(json_output_path)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, 'w') as f:
        json.dump(bounds_data, f, indent=4)
    print(f"[RoomBounds] Saved fixed stage bounds to: {out_json}")
    return bounds_data


def export_glb(mesh, dest_path: Path, root_dir: Path):
    """
    Exports the Open3D triangle mesh with vertex colors as a standard binary GLTF (.glb).
    Synchronizes the file to frontend/public/models and frontend/dist/models.
    """
    import numpy as np

    dest_path = dest_path.resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    normals = np.asarray(mesh.vertex_normals) if mesh.has_vertex_normals() else None
    colors = None

    if mesh.has_vertex_colors():
        vc = np.asarray(mesh.vertex_colors)
        if vc.max() <= 1.0:
            colors = (vc * 255.0).clip(0, 255).astype(np.uint8)
        else:
            colors = vc.clip(0, 255).astype(np.uint8)
        # Append alpha channel if RGB
        if colors.shape[-1] == 3:
            alpha = np.full((len(colors), 1), 255, dtype=np.uint8)
            colors = np.hstack([colors, alpha])

    exported = False

    # Primary export via trimesh (produces self-contained standard GLB with vertex colors)
    try:
        import trimesh
        t_mesh = trimesh.Trimesh(
            vertices=vertices,
            faces=faces,
            vertex_normals=normals,
            vertex_colors=colors,
            process=False,
        )
        t_mesh.export(str(dest_path), file_type="glb")
        exported = True
        print(f"[Export] Saved GLB via Trimesh: {dest_path} ({dest_path.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"[Export] Trimesh export notice ({e}); trying Open3D native writer...")

    # Fallback export via Open3D
    if not exported:
        try:
            import open3d as o3d
            o3d.io.write_triangle_mesh(str(dest_path), mesh)
            exported = True
            print(f"[Export] Saved GLB via Open3D: {dest_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to export GLB model: {e}")

    # Synchronize to dist/models if production build exists
    dist_models = root_dir / "frontend" / "dist" / "models"
    if dist_models.exists():
        dist_dest = dist_models / dest_path.name
        shutil.copy2(dest_path, dist_dest)
        print(f"[Export] Synchronized model to frontend build: {dist_dest}")

    # Also archive to output/ directory
    archive_dir = root_dir / "output"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_glb = archive_dir / "scene_textured.glb"
    shutil.copy2(dest_path, archive_glb)
    print(f"[Export] Archived copy to: {archive_glb}")

    # Also export scene_textured.ply across all targets
    ply_dest = dest_path.with_suffix(".ply")
    try:
        import open3d as o3d
        o3d.io.write_triangle_mesh(str(ply_dest), mesh, write_vertex_colors=True)
        print(f"[Export] Saved PLY: {ply_dest}")
        if dist_models.exists():
            shutil.copy2(ply_dest, dist_models / ply_dest.name)
        shutil.copy2(ply_dest, archive_dir / "scene_textured.ply")
    except Exception as e:
        print(f"[Export] PLY export notice ({e})")

    # Copy GLB to frontend models directories
    for dest_dir in [root_dir / "frontend" / "public" / "models", root_dir / "frontend" / "dist" / "models"]:
        if dest_dir.exists():
            shutil.copy2(archive_glb, dest_dir / "scene_textured.glb")


# =====================================================================
# 5. Main Reconstruction Pipeline
# =====================================================================
def main():
    parser = argparse.ArgumentParser(
        description="DUSt3R Neural 3D Reconstruction Pipeline for Forensic Spatial Analyzer"
    )
    parser.add_argument("images", nargs="?", default="input/images", help="Path to input scene photos directory")
    parser.add_argument("--device", default="auto", help="Compute device ('auto', 'cuda', 'mps', 'cpu')")
    parser.add_argument(
        "--model_name",
        default="naver/DUSt3R_ViTLarge_BaseDecoder_512_dpt",
        help="Pretrained DUSt3R Hugging Face model checkpoint",
    )
    parser.add_argument("--image_size", type=int, default=512, help="Image resolution for inference (e.g. 512 or 224)")
    parser.add_argument("--batch_size", type=int, default=1, help="Inference batch size (1 recommended for MPS/CPU)")
    parser.add_argument(
        "--scene_graph",
        default="auto",
        choices=["auto", "complete", "swin-3", "swin-4", "oneref"],
        help="Pairwise connectivity graph ('auto' selects 'swin-3' for >5 images to prevent overheating)",
    )
    parser.add_argument("--niter", type=int, default=100, help="Number of global alignment optimization iterations")
    parser.add_argument("--min_conf_thr", type=float, default=1.0, help="Minimum confidence threshold for point pruning")
    parser.add_argument(
        "--poisson_depth",
        type=int,
        default=9,
        help="Octree depth for Open3D Poisson Reconstruction (default: 9 for high-polygon sharp texture resolution; use 10 for fine detail)",
    )
    parser.add_argument(
        "--density_quantile",
        type=float,
        default=0.05,
        help="Quantile cutoff for trimming Poisson extrapolation / melted ceiling artifacts (default: 0.05)",
    )
    parser.add_argument("--voxel_size", type=float, default=0.0, help="Voxel size (0.0 = adaptively computed)")
    parser.add_argument(
        "--target_size",
        type=float,
        default=15.0,
        help="Target bounding extent size in Three.js units (default: 15.0)",
    )
    parser.add_argument(
        "--output",
        default="frontend/public/models/scene_textured.glb",
        help="Destination path for final GLB mesh",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    image_dir = Path(args.images).expanduser()
    if not image_dir.is_absolute():
        image_dir = root_dir / image_dir
    image_dir = image_dir.resolve()

    print("=================================================================")
    print("   FORENSIC SPATIAL ANALYZER: DUSt3R 3D RECONSTRUCTION ENGINE   ")
    print("=================================================================")
    print(f"Working Directory: {root_dir}")
    print(f"Image Directory:   {image_dir}")

    # Gather image files
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".JPG", ".JPEG", ".PNG"}
    if not image_dir.exists():
        raise SystemExit(f"ERROR: Image directory '{image_dir}' does not exist.")

    image_paths = sorted([p for p in image_dir.iterdir() if p.is_file() and p.suffix in valid_exts])
    print(f"Found {len(image_paths)} valid evidence photo(s) in {image_dir.name}/")

    if len(image_paths) < 2:
        raise SystemExit("ERROR: DUSt3R requires at least 2 photos for 3D stereoscopic reconstruction.")

    # Ensure DUSt3R is available
    ensure_dust3r(root_dir)

    try:
        import numpy as np
        import torch
        from dust3r.cloud_opt import GlobalAlignerMode, global_aligner
        from dust3r.image_pairs import make_pairs
        from dust3r.inference import inference
        from dust3r.model import AsymmetricCroCo3DStereo
        from dust3r.utils.image import load_images
    except ImportError as err:
        print("\nERROR: Required neural reconstruction libraries could not be loaded.")
        print(f"Details: {err}")
        print("\nPlease run:")
        print("  pip install -r requirements.txt")
        print("  git clone --recursive https://github.com/naver/dust3r.git third_party/dust3r")
        sys.exit(1)

    # 1. Hardware-Agnostic Device Setup
    device = detect_device(args.device)

    # 2. DUSt3R Model Initialization
    print(f"\n[DUSt3R] Loading model checkpoint '{args.model_name}'...")
    try:
        model = AsymmetricCroCo3DStereo.from_pretrained(args.model_name).to(device)
        model.eval()
        print("[DUSt3R] Model weights loaded and ready on target device.")
    except Exception as e:
        print(f"ERROR: Failed to load DUSt3R model '{args.model_name}': {e}")
        print("Tip: Check your internet connection or verify Hugging Face cache.")
        sys.exit(1)

    # 3. Image Preprocessing & Pairwise Inference
    print(f"[DUSt3R] Preprocessing {len(image_paths)} images (resolution: {args.image_size})...")
    loaded_images = load_images([str(p) for p in image_paths], size=args.image_size, verbose=False)

    # Select scene graph (adaptive sliding window for >5 images to protect against overheating on fanless Macs)
    actual_scene_graph = args.scene_graph
    if actual_scene_graph == "auto":
        actual_scene_graph = "complete" if len(image_paths) <= 5 else "swin-3"
        print(f"[Thermal Profile] Selected adaptive scene_graph='{actual_scene_graph}' ({len(image_paths)} images).")

    print(f"[DUSt3R] Constructing image pairs (scene_graph='{actual_scene_graph}', symmetrize=True)...")
    pairs = make_pairs(loaded_images, scene_graph=actual_scene_graph, symmetrize=True)
    print(f"[DUSt3R] Generated {len(pairs)} view pair(s) for pairwise geometric prediction.")

    print(f"[DUSt3R] Running pairwise neural inference (batch_size={args.batch_size})...")
    with torch.no_grad():
        output = inference(pairs, model, device, batch_size=args.batch_size, verbose=True)

    # Immediately release ViT-Large model weights from unified memory before global alignment
    del model
    if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()

    # 4. Global Alignment & Coordinate Fusion
    print(f"\n[Global Alignment] Initializing GlobalAligner (mode=PointCloudOptimizer)...")
    scene = global_aligner(output, device=device, mode=GlobalAlignerMode.PointCloudOptimizer)

    print(f"[Global Alignment] Optimizing scene graph (niter={args.niter}, init='mst', schedule='cosine')...")
    loss = scene.compute_global_alignment(init="mst", niter=args.niter, schedule="cosine", lr=0.01)
    try:
        print(f"[Global Alignment] Optimization converged. Final loss: {float(loss):.5f}")
    except Exception:
        print("[Global Alignment] Optimization completed.")

    if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()

    # Apply minimum confidence threshold
    scene.min_conf_thr = args.min_conf_thr
    pts3d = scene.get_pts3d()
    masks = scene.get_masks()
    imgs = scene.imgs

    # Fuse point clouds and RGB photographic colors
    print(f"[Global Alignment] Extracting dense pointmaps with confidence threshold >= {args.min_conf_thr}...")
    all_points = []
    all_colors = []

    for idx, (img, pts, mask) in enumerate(zip(imgs, pts3d, masks)):
        pts_np = pts.detach().cpu().numpy() if isinstance(pts, torch.Tensor) else np.asarray(pts)
        mask_np = mask.detach().cpu().numpy() if isinstance(mask, torch.Tensor) else np.asarray(mask)
        img_np = img.detach().cpu().numpy() if isinstance(img, torch.Tensor) else np.asarray(img)

        # Standardize image array to (H, W, 3) in [0.0, 1.0]
        if img_np.ndim == 3 and img_np.shape[0] == 3 and img_np.shape[2] != 3:
            img_np = np.transpose(img_np, (1, 2, 0))
        if img_np.max() > 1.0:
            img_np = img_np / 255.0
        img_np = np.clip(img_np, 0.0, 1.0)

        pts_flat = pts_np.reshape(-1, 3)
        colors_flat = img_np.reshape(-1, 3)
        mask_flat = mask_np.reshape(-1).astype(bool)

        finite_mask = np.isfinite(pts_flat).all(axis=-1)
        valid = mask_flat & finite_mask

        valid_pts = pts_flat[valid]
        valid_cols = colors_flat[valid]

        if len(valid_pts) > 0:
            all_points.append(valid_pts)
            all_colors.append(valid_cols)

    if not all_points:
        raise RuntimeError(
            f"No valid points remained above confidence threshold {args.min_conf_thr}. "
            "Please try again with a lower --min_conf_thr (e.g. 0.5)."
        )

    fused_points = np.vstack(all_points)
    fused_colors = np.vstack(all_colors)
    print(f"[Global Alignment] Fused dense point cloud: {len(fused_points):,} total 3D points.")

    # ── Extract Camera Poses & Dynamic Inversion Check ────────────────
    # 1. Extract Camera Poses: After DUSt3R completes global alignment, extract camera-to-world poses
    is_inverted = False
    mean_y = 1.0
    try:
        poses = scene.get_im_poses()
        poses_np = poses.detach().cpu().numpy() if hasattr(poses, "detach") else np.asarray(poses)

        # 2. Dynamic Inversion Math:
        # In the OpenCV coordinate system (used by DUSt3R), the local camera "Up" vector is [0, -1, 0].
        # For each pose, extract the 3x3 rotation matrix and multiply by [0, -1, 0] to find where
        # the top of the camera is pointing in global 3D space.
        cam_up_local = np.array([0.0, -1.0, 0.0], dtype=np.float64)
        up_y_components = []

        for pose in poses_np:
            R = pose[:3, :3]
            world_up = R @ cam_up_local
            up_y_components.append(float(world_up[1]))

        if up_y_components:
            mean_y = float(np.mean(up_y_components))
            # If the mean Y-component is negative, the room was reconstructed upside down
            if mean_y < 0.0:
                is_inverted = True

        print(f"[Pose Analysis] Evaluated {len(up_y_components)} camera pose(s). Mean camera Up Y = {mean_y:+.4f}")
        if is_inverted:
            print("[Pose Analysis] Inversion detected (mean_y < 0): scene is upside down. Will apply 180° X-axis rotation.")
        else:
            print("[Pose Analysis] Scene orientation upright (mean_y >= 0): no rotation needed.")

        pose_dict = {image_paths[i].name: poses_np[i].tolist() for i in range(min(len(image_paths), len(poses_np)))}
        poses_path = root_dir / "output" / "camera_poses.json"
        poses_path.parent.mkdir(parents=True, exist_ok=True)
        with open(poses_path, "w") as f:
            json.dump(pose_dict, f, indent=2)
        print(f"[DUSt3R] Saved camera trajectories for {len(pose_dict)} views to: {poses_path.name}")
    except Exception as e:
        print(f"[DUSt3R] Notice: Could not compute camera pose inversion: {e}")

    # 5. Open3D Poisson Mesh Reconstruction
    print("\n-----------------------------------------------------------------")
    print("                     OPEN3D MESH GENERATION                     ")
    print("-----------------------------------------------------------------")
    mesh = generate_poisson_mesh(
        point_cloud_xyz=fused_points,
        point_cloud_rgb=fused_colors,
        poisson_depth=args.poisson_depth,
        density_quantile=args.density_quantile,
        voxel_size=args.voxel_size,
    )

    # ── 3. Conditional 180° X-Axis Inversion Rotation ─────────────────
    # Must happen before scaling and AABB corner extraction
    if is_inverted:
        print("[Open3D Orient] is_inverted is True: applying 180° X-axis rotation...")
        mesh.rotate(mesh.get_rotation_matrix_from_xyz((np.pi, 0, 0)), center=mesh.get_center())
        if poses_path.exists():
            try:
                with open(poses_path, "r", encoding="utf-8") as pf:
                    c_poses = json.load(pf)
                M3 = np.diag([1.0, -1.0, -1.0])
                for k, p in c_poses.items():
                    p_mat = np.array(p, dtype=np.float64)
                    p_mat[:3, :3] = M3 @ p_mat[:3, :3]
                    p_mat[:3, 3] = M3 @ p_mat[:3, 3]
                    c_poses[k] = p_mat.tolist()
                with open(poses_path, "w", encoding="utf-8") as pf:
                    json.dump(c_poses, pf, indent=2)
                print(f"[DUSt3R] Inverted {len(c_poses)} camera poses to match 180° mesh flip.")
            except Exception as e:
                print(f"[DUSt3R] Notice inverting camera poses: {e}")
        print("[Open3D Orient] Corrective 180° flip applied successfully.")
    else:
        print("[Open3D Orient] is_inverted is False: keeping original mesh orientation.")

    # ── Dynamic Scaling & Centering to Origin ─────────────────────────
    # Compute Axis-Aligned Bounding Box (AABB) and longest dimension
    aabb = mesh.get_axis_aligned_bounding_box()
    extent = aabb.get_extent()  # [extent_x, extent_y, extent_z]
    max_extent = float(np.max(extent))
    print(f"[Open3D Norm] Raw mesh bounding box extent: [{extent[0]:.3f}, {extent[1]:.3f}, {extent[2]:.3f}] (max dimension: {max_extent:.4f})")

    # Apply dynamic scaling so the longest dimension matches target size (e.g. 15.0 Three.js units)
    TARGET_SIZE = getattr(args, "target_size", 15.0)
    scale_factor = 1.0
    if max_extent > 1e-6:
        scale_factor = float(TARGET_SIZE / max_extent)
        print(f"[Open3D Norm] Scaling mesh by factor {scale_factor:.4f} to match TARGET_SIZE = {TARGET_SIZE}...")
        mesh.scale(scale_factor, center=mesh.get_center())

    # Translate so the geometric center rests exactly at the origin (0, 0, 0)
    center = mesh.get_center()
    print(f"[Open3D Norm] Centering mesh: translating from [{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}] to (0, 0, 0)...")
    mesh.translate(-center, relative=True)

    if poses_path.exists():
        try:
            with open(poses_path, "r", encoding="utf-8") as pf:
                c_poses = json.load(pf)
            for k, p in c_poses.items():
                p_mat = np.array(p, dtype=np.float64)
                p_mat[:3, 3] = (p_mat[:3, 3] - center) * scale_factor
                c_poses[k] = p_mat.tolist()
            with open(poses_path, "w", encoding="utf-8") as pf:
                json.dump(c_poses, pf, indent=2)
            print(f"[DUSt3R] Scaled & centered {len(c_poses)} camera poses to match mesh origin.")
        except Exception as e:
            print(f"[DUSt3R] Notice scaling/translating camera poses: {e}")

    # Verification of final scaled & centered dimensions & AABB corner extraction
    final_aabb = mesh.get_axis_aligned_bounding_box()
    final_extent = final_aabb.get_extent()
    final_center = mesh.get_center()
    box_corners = np.asarray(final_aabb.get_box_points()).tolist()
    print(f"[Open3D Norm] Final normalized extent: [{final_extent[0]:.2f}, {final_extent[1]:.2f}, {final_extent[2]:.2f}], Center: [{final_center[0]:.3f}, {final_center[1]:.3f}, {final_center[2]:.3f}]")

    # 6. GLB Export
    print("\n-----------------------------------------------------------------")
    print("                           GLB EXPORT                            ")
    print("-----------------------------------------------------------------")
    output_glb_path = Path(args.output).expanduser()
    if not output_glb_path.is_absolute():
        output_glb_path = root_dir / output_glb_path

    export_glb(mesh, output_glb_path, root_dir)

    # Automatically enhance mesh (prune floaters, level floor, and clean textures)
    enhance_script = root_dir / "scripts" / "enhance_mesh.py"
    if enhance_script.exists():
        try:
            print("[Enhance] Pruning floaters, leveling floor, and cleaning mesh...")
            subprocess.run([sys.executable, str(enhance_script), str(output_glb_path)], cwd=str(root_dir), check=False)
        except Exception as e:
            print(f"[Enhance] Notice: {e}")

    # Automatically calibrate compass direction and detect scene objects
    calib_script = root_dir / "scripts" / "calibrate_direction.py"
    if calib_script.exists():
        try:
            print("[Direction] Calibrating compass northOffset from camera poses...")
            subprocess.run([sys.executable, str(calib_script)], cwd=str(root_dir), check=False)
        except Exception as e:
            print(f"[Direction] Notice: {e}")

    detect_script = root_dir / "scripts" / "detect_scene_objects.py"
    if detect_script.exists():
        try:
            print("[Objects] Updating dynamic room boundaries and navigation grid...")
            subprocess.run([sys.executable, str(detect_script)], cwd=str(root_dir), check=False)
        except Exception as e:
            print(f"[Objects] Notice: {e}")

    # Synchronize all output artifacts to frontend public and dist models directories
    sync_files = [
        "scene_textured.glb",
        "boundary_markers.json",
        "direction.json",
        "scene_objects.json",
        "navgrid.json",
        "camera_poses.json",
        "room_bounds.json"
    ]
    for dest_dir in [root_dir / "frontend" / "public" / "models", root_dir / "frontend" / "dist" / "models"]:
        if dest_dir.exists():
            for fname in sync_files:
                src_f = root_dir / "output" / fname
                if src_f.exists():
                    shutil.copy2(src_f, dest_dir / fname)
            print(f"[DUSt3R Deploy] Synchronized pipeline artifacts to: {dest_dir.name}")

    print("\n=================================================================")
    print("DONE. 3D Digital Twin successfully generated via DUSt3R!")
    print(f"Target Model: {output_glb_path}")
    print("=================================================================")


if __name__ == "__main__":
    main()
