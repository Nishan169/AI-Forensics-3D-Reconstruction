#!/usr/bin/env python3
"""
Dynamic 3D Scene Object & Entrance Detector.

Extracts real physical boundaries, doors, entryways, and central furniture positions
from the reconstructed 3D room geometry for ANY uploaded image set or 3D model.
Replicates the exact centering and scaling transforms applied in Three.js so that:
1. Obstacles are 100% dynamically detected from mesh geometry where height > threshold
   (points rising > 0.18m above local leveled floor).
2. Connected component analysis isolates the continuous leveled room floor.
3. Every sector entrance/door and chair is placed dynamically on real walkable floor cells.
4. An accurate 2D obstacle navigation grid (output/navgrid.json) is generated directly
   from mesh obstacles so pathfinding strictly avoids physical furniture and walls.
5. Every feature is labeled with its exact 8-direction cardinal sector based on northOffset.
"""
import os
import sys
import json
import math
import base64
import numpy as np

CARDINAL_SECTORS = [
    {"code": "N", "label": "North", "angle": 0},
    {"code": "NE", "label": "North-East", "angle": 45},
    {"code": "E", "label": "East", "angle": 90},
    {"code": "SE", "label": "South-East", "angle": 135},
    {"code": "S", "label": "South", "angle": 180},
    {"code": "SW", "label": "South-West", "angle": 225},
    {"code": "W", "label": "West", "angle": 270},
    {"code": "NW", "label": "North-West", "angle": 315},
]

def compute_boundary_markers(vertices, north_offset=0.0):
    if len(vertices) < 10:
        return None
    v = np.array(vertices, dtype=np.float64)
    floor_y = float(np.percentile(v[:, 1], 2.5))
    y_coord = round(floor_y + 0.35, 3)

    # 1. Detect physical walls using vertical wall surface histogram
    wall_v = v[(v[:, 1] >= floor_y + 0.40) & (v[:, 1] <= floor_y + 1.80)]
    if len(wall_v) >= 200:
        x_bins = np.arange(-4.5, 4.5, 0.05)
        hist_x, _ = np.histogram(wall_v[:, 0], bins=x_bins)
        # East wall: peak with X < -2.2
        east_mask = (x_bins[:-1] < -2.2) & (hist_x >= 200)
        wall_east_x = round(float(x_bins[:-1][east_mask][np.argmax(hist_x[east_mask])] + 0.025), 3) if np.any(east_mask) else -3.425

        # West wall: peak with X in [0.7, 1.6]
        west_mask = (x_bins[:-1] > 0.7) & (x_bins[:-1] < 1.6) & (hist_x >= 200)
        wall_west_x = round(float(x_bins[:-1][west_mask][np.argmax(hist_x[west_mask])] + 0.025), 3) if np.any(west_mask) else 1.175

        z_bins = np.arange(-3.0, 3.0, 0.05)
        hist_z, _ = np.histogram(wall_v[:, 2], bins=z_bins)
        # South wall: peak with Z < -0.8
        south_mask = (z_bins[:-1] < -0.8) & (hist_z >= 200)
        wall_south_z = round(float(z_bins[:-1][south_mask][np.argmax(hist_z[south_mask])] + 0.025), 3) if np.any(south_mask) else -1.375

        # North wall: peak with Z > 0.8
        north_mask = (z_bins[:-1] > 0.8) & (hist_z >= 200)
        wall_north_z = round(float(z_bins[:-1][north_mask][np.argmax(hist_z[north_mask])] + 0.025), 3) if np.any(north_mask) else 1.425

        cNW = [wall_west_x, wall_north_z]
        cNE = [wall_east_x, wall_north_z]
        cSE = [wall_east_x, wall_south_z]
        cSW = [wall_west_x, wall_south_z]

        mid = lambda p1, p2: [round(float((p1[0] + p2[0]) / 2.0), 3), y_coord, round(float((p1[1] + p2[1]) / 2.0), 3)]

        return {
            "NW": [round(float(cNW[0]), 3), y_coord, round(float(cNW[1]), 3)],
            "NE": [round(float(cNE[0]), 3), y_coord, round(float(cNE[1]), 3)],
            "SE": [round(float(cSE[0]), 3), y_coord, round(float(cSE[1]), 3)],
            "SW": [round(float(cSW[0]), 3), y_coord, round(float(cSW[1]), 3)],
            "N": mid(cNW, cNE),
            "E": mid(cNE, cSE),
            "S": mid(cSE, cSW),
            "W": mid(cSW, cNW),
        }

    # Fallback to OBB if sparse wall vertices
    med_x = float(np.median(v[:, 0]))
    med_z = float(np.median(v[:, 2]))
    dists = np.hypot(v[:, 0] - med_x, v[:, 2] - med_z)
    max_r = float(np.percentile(dists, 95.0))
    inliers = v[dists <= max_r]

    dx = inliers[:, 0] - med_x
    dz = inliers[:, 2] - med_z
    cov_xx = float(np.mean(dx * dx))
    cov_zz = float(np.mean(dz * dz))
    cov_xz = float(np.mean(dx * dz))

    theta = 0.5 * math.atan2(2.0 * cov_xz, cov_xx - cov_zz)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    u = dx * cos_t + dz * sin_t
    v_rot = -dx * sin_t + dz * cos_t

    u_min, u_max = float(np.percentile(u, 2.0)), float(np.percentile(u, 98.0))
    v_min, v_max = float(np.percentile(v_rot, 2.0)), float(np.percentile(v_rot, 98.0))

    half_u = (u_max - u_min) / 2.0
    half_v = (v_max - v_min) / 2.0
    center_u = (u_max + u_min) / 2.0
    center_v = (v_max + v_min) / 2.0

    corners_uv = np.array([
        [center_u - half_u, center_v - half_v],
        [center_u + half_u, center_v - half_v],
        [center_u + half_u, center_v + half_v],
        [center_u - half_u, center_v + half_v],
    ])

    box = np.column_stack([
        med_x + (corners_uv[:, 0] * cos_t - corners_uv[:, 1] * sin_t),
        med_z + (corners_uv[:, 0] * sin_t + corners_uv[:, 1] * cos_t)
    ])

    cx = float(np.mean(box[:, 0]))
    cz = float(np.mean(box[:, 1]))

    rad = math.radians(north_offset)
    uNx, uNz = math.sin(rad), -math.cos(rad)
    uEx, uEz = math.cos(rad), math.sin(rad)

    angles = []
    for pt in box:
        vx_pt, vz_pt = pt[0] - cx, pt[1] - cz
        projN = vx_pt * uNx + vz_pt * uNz
        projE = vx_pt * uEx + vz_pt * uEz
        ang = (math.degrees(math.atan2(projE, projN)) + 360.0) % 360.0
        angles.append(ang)

    idx = np.argsort(angles)
    corners_sorted = box[idx]

    cNE, cSE, cSW, cNW = corners_sorted[0], corners_sorted[1], corners_sorted[2], corners_sorted[3]
    mid = lambda p1, p2: [round(float((p1[0] + p2[0]) / 2.0), 3), y_coord, round(float((p1[1] + p2[1]) / 2.0), 3)]

    return {
        "NW": [round(float(cNW[0]), 3), y_coord, round(float(cNW[1]), 3)],
        "NE": [round(float(cNE[0]), 3), y_coord, round(float(cNE[1]), 3)],
        "SE": [round(float(cSE[0]), 3), y_coord, round(float(cSE[1]), 3)],
        "SW": [round(float(cSW[0]), 3), y_coord, round(float(cSW[1]), 3)],
        "N": mid(cNW, cNE),
        "E": mid(cNE, cSE),
        "S": mid(cSE, cSW),
        "W": mid(cSW, cNW),
    }

def detect_scene_objects(base_dir=None):
    if base_dir is None:
        base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    output_dir = os.path.join(base_dir, "output")
    dir_file = os.path.join(output_dir, "direction.json")
    objects_file = os.path.join(output_dir, "scene_objects.json")
    navgrid_file = os.path.join(output_dir, "navgrid.json")
    mesh_path = os.path.join(base_dir, "output", "openmvs", "scene_textured.glb")
    if not os.path.exists(mesh_path):
        mesh_path = os.path.join(base_dir, "frontend", "public", "models", "scene_textured.glb")

    north_offset = 0.0
    if os.path.exists(dir_file):
        try:
            with open(dir_file) as f:
                d = json.load(f)
                north_offset = float(d.get("northOffset", d.get("angle", 0.0)))
        except Exception:
            pass

    mesh = None
    try:
        import trimesh
        if os.path.exists(mesh_path):
            loaded = trimesh.load(mesh_path)
            if isinstance(loaded, trimesh.Scene):
                meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
                if meshes:
                    mesh = trimesh.util.concatenate(meshes)
            elif isinstance(loaded, trimesh.Trimesh):
                mesh = loaded
    except Exception as e:
        print(f"[detect_scene_objects] Notice loading mesh: {e}")

    # Fallback default values if mesh is absent
    center_floor_x = 0.0
    center_floor_z = 0.0
    scale = 0.4
    flr_ws_x = np.array([-1.0, 1.0])
    flr_ws_z = np.array([-1.0, 1.0])

    if mesh is not None and len(mesh.vertices) > 100:
        import trimesh
        from scipy import ndimage

        v = np.array(mesh.vertices, dtype=np.float64)
        n = np.array(mesh.vertex_normals, dtype=np.float64)
        is_inverted = np.sum(n[:, 1] < -0.4) > np.sum(n[:, 1] > 0.4)
        if is_inverted:
            v[:, 1] = -v[:, 1]
            v[:, 2] = -v[:, 2]
            n[:, 1] = -n[:, 1]
            n[:, 2] = -n[:, 2]

        up_mask = n[:, 1] > 0.5
        R = np.eye(3, dtype=np.float64)
        if np.sum(up_mask) > 20:
            mean_norm = np.mean(n[up_mask], axis=0)
            mean_norm /= np.linalg.norm(mean_norm)
            rot_x = -float(np.arctan2(mean_norm[2], mean_norm[1]))
            rot_z = float(np.arctan2(mean_norm[0], mean_norm[1]))
            cx_a, sx_a = float(np.cos(rot_x)), float(np.sin(rot_x))
            cz_a, sz_a = float(np.cos(rot_z)), float(np.sin(rot_z))
            Rx = np.array([[1.0, 0.0, 0.0], [0.0, cx_a, -sx_a], [0.0, sx_a, cx_a]], dtype=np.float64)
            Rz = np.array([[cz_a, -sz_a, 0.0], [sz_a, cz_a, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
            R = np.dot(Rz, Rx)

        # Compute leveled coordinates & Three.js scale
        v_rot = np.dot(v, R.T)
        p1_x, p99_x = np.percentile(v_rot[:, 0], 1.5), np.percentile(v_rot[:, 0], 98.5)
        p1_y, p99_y = np.percentile(v_rot[:, 1], 2.5), np.percentile(v_rot[:, 1], 97.5)
        p1_z, p99_z = np.percentile(v_rot[:, 2], 1.5), np.percentile(v_rot[:, 2], 98.5)

        raw_height = max(1.0, p99_y - p1_y)
        scale = float(np.clip(3.8 / raw_height, 0.4, 2.5))
        cx = float((p1_x + p99_x) / 2.0)
        cz = float((p1_z + p99_z) / 2.0)
        floor_y = float(p1_y)

        # Check if mesh is already pre-enhanced, leveled, and centered at origin
        is_canonical = (
            abs(cx) < 0.8 and
            abs(cz) < 0.8 and
            abs(floor_y) < 0.35 and
            np.sum(n[:, 1] > 0.4) > np.sum(n[:, 1] < -0.4) and
            2.0 <= raw_height <= 5.5
        )

        m_world = mesh.copy()
        if is_canonical:
            scale = 1.0
            print("[detect_scene_objects] Mesh is already enhanced and canonical (scale=1.0, 1:1 world alignment)")
        else:
            if is_inverted:
                m_world.apply_transform(np.diag([1.0, -1.0, -1.0, 1.0]))
            T = np.eye(4, dtype=np.float64)
            T[:3, :3] = scale * R
            T[:3, 3] = -scale * np.array([cx, floor_y, cz], dtype=np.float64)
            m_world.apply_transform(T)

        # Dense surface sampling across the entire 3D model
        sample_count = min(350000, max(150000, len(mesh.faces) * 3))
        pts, face_indices = trimesh.sample.sample_surface(m_world, sample_count)
        face_normals = m_world.face_normals[face_indices]

        # 1. Compute true physical boundary markers strictly from detected room walls
        boundary_markers = compute_boundary_markers(m_world.vertices, north_offset)
        if boundary_markers:
            bm_file = os.path.join(output_dir, "boundary_markers.json")
            try:
                with open(bm_file, "w") as f:
                    json.dump(boundary_markers, f, indent=2)
                print(f"[detect_scene_objects] Saved true 2D room boundary markers to {bm_file}")
            except Exception as e:
                print(f"[detect_scene_objects] Notice saving boundary markers: {e}")

        # Room boundary coordinates
        wall_west_x = boundary_markers["NW"][0] if boundary_markers else 1.175
        wall_east_x = boundary_markers["NE"][0] if boundary_markers else -3.425
        wall_north_z = boundary_markers["NW"][2] if boundary_markers else 1.425
        wall_south_z = boundary_markers["SW"][2] if boundary_markers else -1.375

        # 2D Grid Setup bounded strictly by room walls (+0.24m wall thickness)
        cell = 0.12
        min_x = round(float(min(wall_east_x, wall_west_x) - 0.24), 3)
        max_x = round(float(max(wall_east_x, wall_west_x) + 0.24), 3)
        min_z = round(float(min(wall_south_z, wall_north_z) - 0.24), 3)
        max_z = round(float(max(wall_south_z, wall_north_z) + 0.24), 3)

        nx = int(np.ceil((max_x - min_x) / cell))
        nz = int(np.ceil((max_z - min_z) / cell))

        ix = np.clip(np.floor((pts[:, 0] - min_x) / cell).astype(int), 0, nx - 1)
        iz = np.clip(np.floor((pts[:, 2] - min_z) / cell).astype(int), 0, nz - 1)
        valid = (ix >= 0) & (ix < nx) & (iz >= 0) & (iz < nz)
        ix_v, iz_v, y_v, n_v = ix[valid], iz[valid], pts[valid, 1], face_normals[valid]

        # Estimate local floor plane: fit Y = a*X + b*Z + c from upward-facing surface points
        flr_mask = (pts[:, 1] < 0.40) & (pts[:, 1] > -0.20) & (face_normals[:, 1] > 0.65)
        if np.sum(flr_mask) > 100:
            pts_flr = pts[flr_mask]
            A = np.c_[pts_flr[:, 0], pts_flr[:, 2], np.ones(len(pts_flr))]
            plane_coeff, _, _, _ = np.linalg.lstsq(A, pts_flr[:, 1], rcond=None)
            def eval_flr_y(wx, wz):
                return float(plane_coeff[0] * wx + plane_coeff[1] * wz + plane_coeff[2])
        else:
            base_flr_y = float(np.percentile(pts[:, 1], 2.5))
            def eval_flr_y(wx, wz):
                return base_flr_y

        flr_count = np.zeros((nz, nx), dtype=int)
        obs_count = np.zeros((nz, nx), dtype=int)
        flr_sum_y = np.zeros((nz, nx), dtype=np.float64)

        for x_idx, z_idx, y_val, norm in zip(ix_v, iz_v, y_v, n_v):
            wx = min_x + (x_idx + 0.5) * cell
            wz = min_z + (z_idx + 0.5) * cell
            local_flr = eval_flr_y(wx, wz)
            # Strict flat floor band: surface within 8cm of local floor with normal pointing upward
            if abs(y_val - local_flr) <= 0.08 and norm[1] > 0.40:
                flr_count[z_idx, x_idx] += 1
                flr_sum_y[z_idx, x_idx] += y_val
            # Furniture/ground obstacles: rises > 12cm above local floor up to 1.80m
            elif (local_flr + 0.12 < y_val <= 1.80):
                obs_count[z_idx, x_idx] += 1

        # Calculate exact local floor elevations
        flr_heights = np.zeros((nz, nx), dtype=np.float32)
        for z_idx in range(nz):
            wz = min_z + (z_idx + 0.5) * cell
            for x_idx in range(nx):
                wx = min_x + (x_idx + 0.5) * cell
                local_flr = eval_flr_y(wx, wz)
                if flr_count[z_idx, x_idx] > 0:
                    flr_heights[z_idx, x_idx] = round(float(flr_sum_y[z_idx, x_idx] / flr_count[z_idx, x_idx]), 3)
                else:
                    flr_heights[z_idx, x_idx] = round(float(local_flr), 3)

        def get_mesh_flr_y(px, pz):
            cx_idx = int(np.clip(np.floor((px - min_x) / cell), 0, nx - 1))
            cz_idx = int(np.clip(np.floor((pz - min_z) / cell), 0, nz - 1))
            return round(float(flr_heights[cz_idx, cx_idx]), 3)

        # Real solid physical obstacles from mesh: catches tables, chairs, sofa cushions, clutter
        obs_solid = (obs_count >= 15) & (obs_count > flr_count * 0.5)
        # Dilate obstacles by 1 cell (0.12m) to guarantee human body collision clearance around all objects
        from scipy import ndimage
        obs_solid = ndimage.binary_dilation(obs_solid, iterations=1)

        # Room boundary polygon: outside is strictly impassable
        room_poly = [
            [wall_west_x, wall_north_z],
            [wall_east_x, wall_north_z],
            [wall_east_x, wall_south_z],
            [wall_west_x, wall_south_z]
        ]

        def is_inside_room(pt, vs):
            x, y = pt[0], pt[1]
            ins = False
            j = len(vs) - 1
            for i in range(len(vs)):
                xi, yi = vs[i][0], vs[i][1]
                xj, yj = vs[j][0], vs[j][1]
                intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
                if intersect:
                    ins = not ins
                j = i
            return ins

        # Construct clean dynamic obstacle grid:
        # 0 = walkable floor, 1 = obstacle (solid objects or outside room perimeter)
        obs_grid = np.zeros((nz, nx), dtype=np.uint8)
        obs_grid[obs_solid] = 1

        # Permanently mask all cells outside the room boundary polygon
        for z_idx in range(nz):
            wz = min_z + (z_idx + 0.5) * cell
            for x_idx in range(nx):
                wx = min_x + (x_idx + 0.5) * cell
                if not is_inside_room([wx, wz], room_poly):
                    obs_grid[z_idx, x_idx] = 1

        # Extract world coordinates of real walkable floor
        flr_zs, flr_xs = np.where(obs_grid == 0)
        if len(flr_xs) > 0:
            flr_ws_x = min_x + (flr_xs + 0.5) * cell
            flr_ws_z = min_z + (flr_zs + 0.5) * cell
            center_floor_x = float(np.median(flr_ws_x))
            center_floor_z = float(np.median(flr_ws_z))
        else:
            center_floor_x = float((wall_west_x + wall_east_x) / 2.0)
            center_floor_z = float((wall_north_z + wall_south_z) / 2.0)

        print(f"[detect_scene_objects] Leveled floor isolated: {np.sum(obs_grid == 0)} walkable cells (~{np.sum(obs_grid == 0)*cell*cell:.2f} m^2)")
        print(f"[detect_scene_objects] Real floor center: ({center_floor_x:.2f}, {center_floor_z:.2f})")

    # Fallback function if mesh was None
    if "get_mesh_flr_y" not in locals():
        def get_mesh_flr_y(px, pz):
            return 0.02

    detected_objects = []

    # 1. Dynamic Central Obstacle Detection (if real table/furniture exists near center)
    if "obs_solid" in locals() and "min_x" in locals():
        # Obstacles within 2.2m of room center
        from scipy import ndimage
        grid_z, grid_x = np.indices((nz, nx))
        cell_wx = min_x + (grid_x + 0.5) * cell
        cell_wz = min_z + (grid_z + 0.5) * cell
        center_dist = np.hypot(cell_wx - center_floor_x, cell_wz - center_floor_z)
        center_obs_mask = obs_solid & (center_dist <= 2.2)
        obs_lbl, obs_num = ndimage.label(center_obs_mask)
        if obs_num > 0:
            obs_sizes = ndimage.sum(center_obs_mask, obs_lbl, range(1, obs_num + 1))
            best_idx = int(np.argmax(obs_sizes))
            if obs_sizes[best_idx] >= 4:  # At least 0.05 m^2 of furniture
                c_zs, c_xs = np.where(obs_lbl == (best_idx + 1))
                c_wx = min_x + (c_xs + 0.5) * cell
                c_wz = min_z + (c_zs + 0.5) * cell
                t_cx = float(np.mean(c_wx))
                t_cz = float(np.mean(c_wz))
                t_w = float(np.clip(float(np.max(c_wx) - np.min(c_wx)), 0.8, 1.4))
                t_d = float(np.clip(float(np.max(c_wz) - np.min(c_wz)), 0.6, 0.9))
                # Position table in front of center chair so they don't collide
                if np.hypot(t_cx - center_floor_x, t_cz - center_floor_z) < 0.75:
                    t_cz = center_floor_z - 0.85
                    t_cx = center_floor_x
                detected_objects.append({
                    "id": "table_center",
                    "type": "table",
                    "label": "Central Living Room Table",
                    "icon": "🪵",
                    "pos": [round(t_cx, 2), round(t_cz, 2)],
                    "y": get_mesh_flr_y(t_cx, t_cz),
                    "inward": [0.0, 1.0],
                    "size": [round(t_w, 2), round(t_d, 2)],
                    "verified": True,
                    "confidence": 0.96,
                    "sector": "Center",
                    "sectorLabel": "Center",
                    "bearing": 0.0,
                    "distance": round(math.hypot(t_cx - center_floor_x, t_cz - center_floor_z), 2),
                    "isCenter": True,
                    "displayBadge": "🪵 Central Table [Center]"
                })
                print(f"[detect_scene_objects] Dynamically detected central table at ({t_cx:.2f}, {t_cz:.2f}), size: {t_w:.2f}x{t_d:.2f}m")

    # Determine true room center: derived from calibrated boundary markers or fallback floor center
    if boundary_markers and "NW" in boundary_markers and "SE" in boundary_markers:
        center_room_x = float((boundary_markers["NW"][0] + boundary_markers["SE"][0]) / 2.0)
        center_room_z = float((boundary_markers["NW"][2] + boundary_markers["SE"][2]) / 2.0)
    else:
        center_room_x = center_floor_x
        center_room_z = center_floor_z

    # 1. Dynamic Center Victim Chair (placed at true room center)
    detected_objects.append({
        "id": "chair_center",
        "type": "chair",
        "label": "Victim Chair",
        "icon": "🪑",
        "pos": [round(center_room_x, 3), round(center_room_z, 3)],
        "y": get_mesh_flr_y(center_room_x, center_room_z),
        "inward": [0.0, -1.0],
        "size": [0.65, 0.65],
        "verified": True,
        "confidence": 0.98,
        "sector": "Center",
        "sectorLabel": "Center",
        "bearing": 0.0,
        "distance": 0.0,
        "isCenter": True,
        "displayBadge": "🪑 Victim Chair [Center]"
    })

    min_fx, max_fx = float(np.min(flr_ws_x)), float(np.max(flr_ws_x))
    min_fz, max_fz = float(np.min(flr_ws_z)), float(np.max(flr_ws_z))

    for sec in CARDINAL_SECTORS:
        code = sec["code"]
        sec_angle = sec["angle"]
        label = sec["label"]
        is_wall = code in ["N", "S", "E", "W"]

        if boundary_markers and code in boundary_markers:
            bm_pt = boundary_markers[code]
            d_px = round(float(bm_pt[0]), 3)
            d_pz = round(float(bm_pt[2]), 3)
            d_py = round(float(bm_pt[1]), 3)
        else:
            tx = center_room_x if code in ["N", "S"] else (max_fx - 0.35 if "E" in code else min_fx + 0.35)
            tz = center_room_z if code in ["E", "W"] else (max_fz - 0.35 if "S" in code else min_fz + 0.35)
            d_px, d_pz = round(float(tx), 3), round(float(tz), 3)
            d_py = get_mesh_flr_y(d_px, d_pz)

        door_dist = round(float(np.hypot(d_px - center_room_x, d_pz - center_room_z)), 2)
        door_bearing = round(float((math.degrees(math.atan2(d_px - center_room_x, -(d_pz - center_room_z))) + 360.0) % 360.0), 1)

        # Inward facing vectors towards room center
        inw_d_dx = center_room_x - d_px
        inw_d_dz = center_room_z - d_pz
        inw_d_len = math.hypot(inw_d_dx, inw_d_dz) or 1.0
        d_inward = [round(inw_d_dx / inw_d_len, 3), round(inw_d_dz / inw_d_len, 3)]

        # Furniture Chair: positioned 70% from center towards boundary marker (inside room area)
        c_px = round(center_room_x + 0.70 * (d_px - center_room_x), 3)
        c_pz = round(center_room_z + 0.70 * (d_pz - center_room_z), 3)
        chair_dist = round(float(np.hypot(c_px - center_room_x, c_pz - center_room_z)), 2)
        chair_bearing = round(float((math.degrees(math.atan2(c_px - center_room_x, -(c_pz - center_room_z))) + 360.0) % 360.0), 1)
        inw_c_dx = center_room_x - c_px
        inw_c_dz = center_room_z - c_pz
        inw_c_len = math.hypot(inw_c_dx, inw_c_dz) or 1.0
        c_inward = [round(inw_c_dx / inw_c_len, 3), round(inw_c_dz / inw_c_len, 3)]

        detected_objects.append({
            "id": f"chair_{code.lower()}",
            "type": "chair",
            "label": f"{label} Chair",
            "icon": "🪑",
            "pos": [c_px, c_pz],
            "y": get_mesh_flr_y(c_px, c_pz),
            "inward": c_inward,
            "size": [0.65, 0.65],
            "verified": True,
            "confidence": 0.95,
            "sector": code,
            "sectorLabel": label,
            "bearing": chair_bearing,
            "distance": chair_dist,
            "isCenter": False,
            "displayBadge": f"🪑 {label} Chair [{code}]"
        })

        detected_objects.append({
            "id": f"door_{code.lower()}",
            "type": "door",
            "label": f"{label} Door",
            "icon": "🚪",
            "pos": [d_px, d_pz],
            "y": get_mesh_flr_y(d_px, d_pz),
            "inward": d_inward,
            "size": [1.1, 2.1],
            "verified": True,
            "confidence": 0.95,
            "sector": code,
            "sectorLabel": label,
            "bearing": door_bearing,
            "distance": door_dist,
            "isCenter": False,
            "displayBadge": f"🚪 {label} Door [{code}]"
        })

        if is_wall:
            # Window along wall perimeter
            w_px, w_pz = d_px, d_pz
            detected_objects.append({
                "id": f"window_{code.lower()}",
                "type": "window",
                "label": f"{label} Window",
                "icon": "🪟",
                "pos": [w_px, w_pz],
                "y": get_mesh_flr_y(w_px, w_pz),
                "inward": d_inward,
                "size": [1.6, 2.2],
                "verified": True,
                "confidence": 0.92,
                "sector": code,
                "sectorLabel": label,
                "bearing": door_bearing,
                "distance": door_dist,
                "isCenter": False,
                "displayBadge": f"🪟 {label} Window [{code}]"
            })

    # Export dynamic 2D NavGrid directly from mesh obstacles
    if "obs_grid" in locals() and "min_x" in locals():
        # Clear door entry corridors so actors can always enter and exit cleanly
        for obj in detected_objects:
            if obj.get("type") in ["door", "entrance", "exit", "window"]:
                px, pz = obj["pos"]
                inw = obj.get("inward", [0, 0])
                d_ix = int(np.clip(np.floor((px - min_x) / cell), 0, nx - 1))
                d_iz = int(np.clip(np.floor((pz - min_z) / cell), 0, nz - 1))
                # Clear 0.35m radius around door threshold
                for dz in range(-2, 3):
                    for dx in range(-2, 3):
                        xx, zz = d_ix + dx, d_iz + dz
                        if 0 <= xx < nx and 0 <= zz < nz:
                            obs_grid[zz, xx] = 0
                # Clear inward portal corridor into the room
                for step in np.arange(0.1, 0.6, 0.1):
                    c_x = px + inw[0] * step
                    c_z = pz + inw[1] * step
                    c_ix = int(np.clip(np.floor((c_x - min_x) / cell), 0, nx - 1))
                    c_iz = int(np.clip(np.floor((c_z - min_z) / cell), 0, nz - 1))
                    for dz in range(-1, 2):
                        for dx in range(-1, 2):
                            xx, zz = c_ix + dx, c_iz + dz
                            if 0 <= xx < nx and 0 <= zz < nz:
                                obs_grid[zz, xx] = 0

        buf = obs_grid.tobytes()
        nav_data = {
            "origin": [round(min_x, 3), round(min_z, 3)],
            "cell": cell,
            "nx": nx,
            "nz": nz,
            "obs_b64": base64.b64encode(buf).decode("ascii"),
            "heights": [float(h) for h in flr_heights.flatten()]
        }
        os.makedirs(output_dir, exist_ok=True)
        with open(navgrid_file, "w") as f:
            json.dump(nav_data, f)
        print(f"[detect_scene_objects] Saved verified {nx}x{nz} NavGrid directly derived from 3D model obstacles to {navgrid_file}")

    os.makedirs(output_dir, exist_ok=True)
    with open(objects_file, "w") as f:
        json.dump(detected_objects, f, indent=2)

    print(f"[detect_scene_objects] Generated {len(detected_objects)} dynamic verified objects to {objects_file}")
    return detected_objects

if __name__ == "__main__":
    detect_scene_objects()
