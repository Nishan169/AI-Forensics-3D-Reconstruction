#!/usr/bin/env python3
"""
Direction & Compass Calibrator from COLMAP Camera Poses.
Calculates the exact viewing direction (azimuth) of the reference photo in the 3D room,
and determines the northOffset angle so the reference photo corresponds to the selected cardinal direction.
"""
import sys
import os
import json
import math
import numpy as np

def calibrate_direction(reference_name=None, target_direction="N", base_dir=None):
    if base_dir is None:
        base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    
    output_dir = os.path.join(base_dir, "output")
    dir_file = os.path.join(output_dir, "direction.json")
    colmap_dir = os.path.join(output_dir, "colmap", "sparse", "0")

    d = {}
    if os.path.exists(dir_file):
        try:
            with open(dir_file) as f:
                d = json.load(f)
        except Exception:
            pass

    if reference_name is None:
        reference_name = d.get("referenceImage")
    if not target_direction:
        target_direction = d.get("direction", "N")

    DIR_ANGLES = {
        "N": 0, "NE": 45, "E": 90, "SE": 135,
        "S": 180, "SW": 225, "W": 270, "NW": 315
    }
    target_angle = DIR_ANGLES.get(target_direction.upper(), 0)

    # 1. Primary: DUSt3R camera_poses.json from neural reconstruction
    dust3r_poses_path = os.path.join(output_dir, "camera_poses.json")
    dust3r_poses = None
    if os.path.exists(dust3r_poses_path):
        try:
            with open(dust3r_poses_path) as f:
                dust3r_poses = json.load(f)
        except Exception as e:
            print(f"[calibrate_direction] Notice camera_poses.json: {e}")
            dust3r_poses = None

    # Secondary / Fallback: COLMAP sparse reconstruction check
    rec = None
    if os.path.exists(colmap_dir):
        try:
            import pycolmap
            rec = pycolmap.Reconstruction(colmap_dir)
            if len(rec.images) == 0:
                rec = None
        except Exception as e:
            print(f"[calibrate_direction] Notice pycolmap: {e}")
            rec = None

    if not dust3r_poses and rec is None:
        print(f"[calibrate_direction] Camera poses not found in {dust3r_poses_path}.")
        d.update({
            "direction": target_direction,
            "angle": target_angle,
            "northOffset": target_angle,
            "calibrated": False,
            "method": "fallback_default"
        })
        os.makedirs(output_dir, exist_ok=True)
        with open(dir_file, "w") as f:
            json.dump(d, f, indent=2)
        return d

    found_name = None
    cam_pos_three = [0.0, 0.0, 0.0]
    fwd_three = [0.0, 0.0, -1.0]
    is_inverted = False

    # Primary: Match reference photo in DUSt3R neural camera poses
    if dust3r_poses:
        found_key = None
        if reference_name:
            clean_ref = os.path.basename(reference_name).lower()
            for k in dust3r_poses.keys():
                if clean_ref in k.lower() or k.lower() in clean_ref:
                    found_key = k
                    break
        if not found_key:
            found_key = list(dust3r_poses.keys())[0]

        found_name = found_key
        pose = np.array(dust3r_poses[found_key], dtype=np.float64)
        R = pose[:3, :3]
        t = pose[:3, 3] if pose.shape[1] > 3 else np.zeros(3)

        # In DUSt3R OpenCV frame: camera forward is +Z, up is -Y
        fwd = R @ np.array([0, 0, 1])
        up = R @ np.array([0, -1, 0])

        # Check global inversion
        all_ups = []
        for p in dust3r_poses.values():
            p_mat = np.array(p, dtype=np.float64)
            u = p_mat[:3, :3] @ np.array([0, -1, 0])
            all_ups.append(float(u[1]))
        is_inverted = np.mean(all_ups) < 0.0 if all_ups else (up[1] < 0.0)

        if is_inverted:
            fwd_three = np.array([fwd[0], -fwd[1], -fwd[2]])
            cam_pos_three = np.array([t[0], -t[1], -t[2]])
        else:
            fwd_three = fwd
            cam_pos_three = t
        method = "dust3r_camera_pose"

    elif rec is not None:
        found = None
        if reference_name:
            clean_ref = os.path.basename(reference_name).lower()
            for _, im in rec.images.items():
                im_clean = os.path.basename(im.name).lower()
                if clean_ref in im_clean or im_clean in clean_ref:
                    found = im
                    break
        if not found:
            found = list(rec.images.values())[0]

        found_name = found.name
        R = found.cam_from_world().rotation.matrix()
        t = found.cam_from_world().translation
        cam_pos = -R.T @ t
        fwd = R.T @ np.array([0, 0, 1])

        up_ys = []
        for im in rec.images.values():
            R_im = im.cam_from_world().rotation.matrix()
            up_im = R_im.T @ np.array([0, -1, 0])
            up_ys.append(up_im[1])
        is_inverted = np.mean(up_ys) < 0 if up_ys else True

        if is_inverted:
            fwd_three = np.array([fwd[0], -fwd[1], -fwd[2]])
            cam_pos_three = np.array([cam_pos[0], -cam_pos[1], -cam_pos[2]])
        else:
            fwd_three = fwd
            cam_pos_three = cam_pos
        method = "colmap_camera_pose"

    # Compute azimuth on XZ plane
    cam_azimuth = float((np.degrees(np.arctan2(fwd_three[0], -fwd_three[2])) + 360.0) % 360.0)
    north_offset = float((cam_azimuth - target_angle + 360.0) % 360.0)

    # Architectural alignment: snap northOffset to the physical wall perpendicular heading if mesh is available
    glb_candidate = None
    for cand_p in [
        os.path.join(output_dir, "scene_textured.glb"),
        os.path.join(base_dir, "frontend", "public", "models", "scene_textured.glb"),
        os.path.join(base_dir, "frontend", "dist", "models", "scene_textured.glb"),
    ]:
        if os.path.exists(cand_p):
            glb_candidate = cand_p
            break

    if glb_candidate:
        try:
            import trimesh
            mesh = trimesh.load(glb_candidate, force='mesh')
            v_pts = np.array(mesh.vertices, dtype=np.float64)
            best_alpha = None

            # 1. Consensus voting via wall surface normals (preferred for high accuracy)
            if hasattr(mesh, 'vertex_normals') and len(mesh.vertex_normals) > 0:
                norms = np.array(mesh.vertex_normals, dtype=np.float64)
                p5_y, p95_y = np.percentile(v_pts[:, 1], [5, 95])
                wall_mask = (v_pts[:, 1] > p5_y + 0.3) & (v_pts[:, 1] < p95_y - 0.3) & (np.abs(norms[:, 1]) < 0.30)
                if np.sum(wall_mask) >= 50:
                    pt_norms = norms[wall_mask]
                    best_score = -1
                    for a in np.arange(0, 90, 0.25):
                        rad = math.radians(a)
                        cos_a, sin_a = math.cos(rad), math.sin(rad)
                        nx_rot = pt_norms[:, 0] * cos_a + pt_norms[:, 2] * sin_a
                        nz_rot = -pt_norms[:, 0] * sin_a + pt_norms[:, 2] * cos_a
                        score = np.sum(np.maximum(np.abs(nx_rot), np.abs(nz_rot)) > 0.94)
                        if score > best_score:
                            best_score = score
                            best_alpha = float(a)

            # 2. Fallback: floor perimeter 2D bounding box area minimization
            if best_alpha is None:
                p5_y = np.percentile(v_pts[:, 1], 5)
                flr_pts = v_pts[v_pts[:, 1] < p5_y + 0.35]
                if len(flr_pts) < 100:
                    flr_pts = v_pts
                best_area = 1e9
                for a in np.linspace(0, 90, 180, endpoint=False):
                    rad = math.radians(a)
                    c, s = math.cos(rad), math.sin(rad)
                    u_tmp = flr_pts[:, 0] * c + flr_pts[:, 2] * s
                    v_tmp = -flr_pts[:, 0] * s + flr_pts[:, 2] * c
                    span_u = np.percentile(u_tmp, 99.0) - np.percentile(u_tmp, 1.0)
                    span_v = np.percentile(v_tmp, 99.0) - np.percentile(v_tmp, 1.0)
                    area = span_u * span_v
                    if area < best_area:
                        best_area = area
                        best_alpha = float(a)

            if best_alpha is not None:
                raw_target_heading = float((cam_azimuth - target_angle + 360.0) % 360.0)
                candidates = [(best_alpha + k * 90.0) % 360.0 for k in range(4)]
                def ang_diff(a1, a2):
                    return abs((a1 - a2 + 180.0) % 360.0 - 180.0)

                best_heading = min(candidates, key=lambda c: ang_diff(c, raw_target_heading))
                # Each wall covers a 90° quadrant (±45°), snap to closest wall normal
                if ang_diff(best_heading, raw_target_heading) <= 45.0:
                    north_offset = round(float(best_heading), 2)
                    print(f"[calibrate_direction] Snapped northOffset to physical wall outward normal: {north_offset}° (diff: {ang_diff(best_heading, raw_target_heading):.2f}°)")
                else:
                    north_offset = round(float(raw_target_heading), 2)
        except Exception as e:
            print(f"[calibrate_direction] Notice aligning with wall geometry: {e}")

    d.update({
        "direction": target_direction.upper(),
        "angle": round(north_offset, 2),
        "northOffset": round(north_offset, 2),
        "cameraAzimuth": round(cam_azimuth, 2),
        "referenceImage": found_name,
        "cameraPosition": [round(float(c), 3) for c in cam_pos_three],
        "forwardVector": [round(float(v), 3) for v in fwd_three],
        "isCOLMAPInverted": bool(is_inverted),
        "calibrated": True,
        "method": method,
        "timestamp": d.get("timestamp") or ""
    })

    os.makedirs(output_dir, exist_ok=True)
    with open(dir_file, "w") as f:
        json.dump(d, f, indent=2)

    import shutil
    for dest_dir in [os.path.join(base_dir, "frontend", "public", "models"),
                     os.path.join(base_dir, "frontend", "dist", "models")]:
        if os.path.exists(dest_dir):
            try:
                shutil.copy2(dir_file, os.path.join(dest_dir, "direction.json"))
            except Exception:
                pass

    print(f"[calibrate_direction] ({method}) Ref: '{found_name}' facing {target_direction} -> camAzimuth = {cam_azimuth:.2f}°, northOffset = {north_offset:.2f}°")
    return d

if __name__ == "__main__":
    ref = sys.argv[1] if len(sys.argv) > 1 else None
    target = sys.argv[2] if len(sys.argv) > 2 else "N"
    calibrate_direction(ref, target)
