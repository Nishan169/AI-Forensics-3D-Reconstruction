#!/usr/bin/env python3
import os
import sys
import math
import json
import shutil
import subprocess
from pathlib import Path
import numpy as np
import trimesh

def ground_mesh_scene(scene, root_dir):
    """Ground the floor at Y = 0.00 and center the room at (0, 0)."""
    if isinstance(scene, trimesh.Scene):
        meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
        mesh = trimesh.util.concatenate(meshes) if meshes else None
    else:
        mesh = scene

    if mesh is None or len(mesh.vertices) < 100:
        return np.zeros(3)

    from scripts.detect_scene_objects import compute_boundary_markers
    sample_count = min(350000, max(150000, len(mesh.faces) * 3))
    pts, face_indices = trimesh.sample.sample_surface(mesh, sample_count)
    face_normals = mesh.face_normals[face_indices]

    bm = compute_boundary_markers(pts, face_normals, north_offset=0.0)
    if bm:
        all_x = [pt[0] for pt in bm.values()]
        all_z = [pt[2] for pt in bm.values()]
        room_cx = float(np.mean(all_x))
        room_cz = float(np.mean(all_z))
        in_room = (pts[:, 0] >= min(all_x)) & (pts[:, 0] <= max(all_x)) & (pts[:, 2] >= min(all_z)) & (pts[:, 2] <= max(all_z))
    else:
        p1_x, p99_x = np.percentile(pts[:, 0], [1.5, 98.5])
        p1_z, p99_z = np.percentile(pts[:, 2], [1.5, 98.5])
        room_cx = float((p1_x + p99_x) / 2.0)
        room_cz = float((p1_z + p99_z) / 2.0)
        in_room = np.ones(len(pts), dtype=bool)

    p2_y = np.percentile(pts[in_room, 1], 2.5)
    flr_pts = pts[in_room & (face_normals[:, 1] > 0.5) & (pts[:, 1] < p2_y + 0.35) & (pts[:, 1] > p2_y - 0.15)]
    flr_y = float(np.median(flr_pts[:, 1])) if len(flr_pts) > 20 else float(np.percentile(pts[:, 1], 2.5))

    shift = np.array([room_cx, flr_y, room_cz], dtype=np.float64)
    if isinstance(scene, trimesh.Scene):
        for geom in scene.geometry.values():
            geom.vertices -= shift
    else:
        scene.vertices -= shift

    # Shift camera poses
    poses_path = root_dir / "output" / "camera_poses.json"
    if poses_path.exists():
        try:
            with open(poses_path) as f:
                poses = json.load(f)
            new_poses = {}
            for k, mat in poses.items():
                arr = np.array(mat, dtype=np.float64)
                if arr.shape[1] > 3:
                    arr[:3, 3] -= shift
                new_poses[k] = arr.tolist()
            with open(poses_path, "w") as f:
                json.dump(new_poses, f, indent=2)
        except Exception as e:
            print(f"[FlipGLB] Notice shifting camera poses: {e}")

    print(f"[FlipGLB] Grounded and centered mesh (shifted by -[{room_cx:.3f}, {flr_y:.3f}, {room_cz:.3f}])")
    return shift

def main():
    root_dir = Path(__file__).resolve().parent
    model_path = root_dir / "output" / "scene_textured.glb"
    ground_only = "--ground-only" in sys.argv

    if not model_path.exists() or model_path.stat().st_size == 0:
        fallback = root_dir / "frontend" / "public" / "models" / "scene_textured.glb"
        if fallback.exists():
            model_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fallback, model_path)
        else:
            print(f"[FlipGLB Error] Neither {model_path} nor fallback found.")
            sys.exit(1)

    print(f"[FlipGLB] Loading: {model_path}")
    scene = trimesh.load(str(model_path), process=False)

    if not ground_only:
        # 1. 180 degrees rotation around X-axis applied to all mesh geometries
        matrix = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
        if isinstance(scene, trimesh.Scene):
            for geom in scene.geometry.values():
                geom.apply_transform(matrix)
        else:
            scene.apply_transform(matrix)
        print(f"[FlipGLB] Successfully flipped geometry upside down.")

        # 2. Invert camera poses in camera_poses.json
        poses_path = root_dir / "output" / "camera_poses.json"
        if poses_path.exists():
            try:
                with open(poses_path) as f:
                    poses = json.load(f)
                M3 = np.diag([1.0, -1.0, -1.0])
                flipped_poses = {}
                for k, p in poses.items():
                    p_mat = np.array(p, dtype=np.float64)
                    p_mat[:3, :3] = M3 @ p_mat[:3, :3]
                    p_mat[:3, 3] = M3 @ p_mat[:3, 3]
                    flipped_poses[k] = p_mat.tolist()
                with open(poses_path, "w") as f:
                    json.dump(flipped_poses, f, indent=2)
                print(f"[FlipGLB] Successfully flipped camera poses in: {poses_path}")
            except Exception as e:
                print(f"[FlipGLB] Notice flipping camera poses: {e}")

    # 3. Ground the floor at Y = 0.00 and center the room at (0, 0)
    ground_mesh_scene(scene, root_dir)

    # Export grounded & centered GLB
    scene.export(str(model_path))
    print(f"[FlipGLB] Successfully saved grounded & centered GLB: {model_path}")

    # 3. Recalibrate direction metadata using calibrate_direction
    try:
        from scripts.calibrate_direction import calibrate_direction
        dir_res = calibrate_direction(reference_name="IMG_20261019_110330.jpg", target_direction="N", base_dir=str(root_dir))
        print(f"[FlipGLB] Re-calibrated direction metadata: northOffset {dir_res.get('northOffset')}°")
    except Exception as e:
        print(f"[FlipGLB] Notice re-calibrating direction: {e}")

    # 4. Re-detect scene objects and boundary markers
    try:
        print("[FlipGLB] Re-detecting scene objects and reassigning boundary markers...")
        from scripts.detect_scene_objects import detect_scene_objects
        detect_scene_objects(base_dir=str(root_dir))
    except Exception as e:
        print(f"[FlipGLB] Objects notice: {e}")

    # 5. Synchronize all generated output artifacts to frontend models directories
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
            print(f"[FlipGLB] Synchronized artifacts to: {dest_dir}")

if __name__ == "__main__":
    main()
