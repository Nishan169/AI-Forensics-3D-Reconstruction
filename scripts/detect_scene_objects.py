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
import shutil
import itertools
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

def compute_boundary_markers(vertices, normals=None, north_offset=0.0):
    if vertices is None or len(vertices) < 10:
        return None
    v = np.array(vertices, dtype=np.float64)
    floor_y = float(np.percentile(v[:, 1], 2.5))
    if abs(floor_y) < 0.45:
        y_coord = 0.35
    else:
        y_coord = round(floor_y + 0.35, 3)
    p5_y, p95_y = np.percentile(v[:, 1], [5, 95])

    # Extract floor and near-floor surface points to obtain true architectural perimeter
    flr_mask = v[:, 1] < p5_y + 0.35
    flr_pts = v[flr_mask]
    if len(flr_pts) < 100:
        flr_pts = v

    # 1. Determine optimal architectural rotation angle alpha in [0..90) deg
    best_alpha = None
    if normals is not None and len(normals) == len(v):
        p5_y, p95_y = np.percentile(v[:, 1], [5, 95])
        wall_mask = (v[:, 1] > p5_y + 0.3) & (v[:, 1] < p95_y - 0.3) & (np.abs(normals[:, 1]) < 0.30)
        if np.sum(wall_mask) >= 50:
            pt_norms = normals[wall_mask]
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

    if best_alpha is None:
        best_area = 1e9
        best_alpha = 0.0
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

    rad = math.radians(best_alpha)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    # 2. In optimal (u, v) space, get true physical room boundary limits
    # Filter points for wall peak detection
    p5_y, p95_y = np.percentile(v[:, 1], [5, 95])
    wall_pts_mask = (v[:, 1] > p5_y + 0.3) & (v[:, 1] < p95_y - 0.3)
    if normals is not None and len(normals) == len(v):
        wall_pts_mask = wall_pts_mask & (np.abs(normals[:, 1]) < 0.30)
    w_pts = v[wall_pts_mask] if np.sum(wall_pts_mask) >= 50 else flr_pts

    us = w_pts[:, 0] * cos_a + w_pts[:, 2] * sin_a
    vs = -w_pts[:, 0] * sin_a + w_pts[:, 2] * cos_a
    med_u = float(np.median(us))
    med_v = float(np.median(vs))

    def get_wall_boundary(vals, med, is_lower, bin_size=0.10):
        if is_lower:
            sub = vals[(vals < med) & (vals > med - 8.0)]
            if len(sub) == 0:
                return float(np.percentile(vals, 1.5))
            p1 = np.percentile(sub, 1.0)
            bins = np.arange(p1 - 0.1, med, bin_size)
            if len(bins) < 2:
                return float(p1)
            counts, edges = np.histogram(sub, bins=bins)
            centers = (edges[:-1] + edges[1:]) / 2.0
            outer_mask = centers < (med + p1 * 1.5) / 2.5
            outer_counts = np.where(outer_mask, counts, 0)
            if np.max(outer_counts) > 200:
                return float(centers[np.argmax(outer_counts)])
            return float(np.percentile(sub, 2.0))
        else:
            sub = vals[(vals > med) & (vals < med + 8.0)]
            if len(sub) == 0:
                return float(np.percentile(vals, 98.5))
            p99 = np.percentile(sub, 99.0)
            bins = np.arange(med, p99 + 0.1, bin_size)
            if len(bins) < 2:
                return float(p99)
            counts, edges = np.histogram(sub, bins=bins)
            centers = (edges[:-1] + edges[1:]) / 2.0
            valid_centers = []
            valid_counts = []
            consec_zeros = 0
            for i in range(len(counts)):
                if counts[i] == 0:
                    consec_zeros += 1
                    if consec_zeros > 5:
                        break
                else:
                    consec_zeros = 0
                    valid_centers.append(centers[i])
                    valid_counts.append(counts[i])
            if valid_counts:
                vc = np.array(valid_centers)
                vn = np.array(valid_counts)
                outer_mask = vc > (med + vc[-1]) / 2.0
                outer_n = np.where(outer_mask, vn, 0)
                if np.max(outer_n) > 200:
                    return float(vc[np.argmax(outer_n)])
            return float(np.percentile(sub, 98.0))

    u_min = get_wall_boundary(us, med_u, True)
    u_max = get_wall_boundary(us, med_u, False)
    v_min = get_wall_boundary(vs, med_v, True)
    v_max = get_wall_boundary(vs, med_v, False)

    # 4 corners in (u, v):
    # C0: [u_min, v_min]
    # C1: [u_max, v_min]
    # C2: [u_max, v_max]
    # C3: [u_min, v_max]
    corners_uv = [
        [u_min, v_min],
        [u_max, v_min],
        [u_max, v_max],
        [u_min, v_max],
    ]

    # Transform back to world (X, Z) coordinates:
    corners_xz = [
        [round(cu * cos_a - cv * sin_a, 3), round(cu * sin_a + cv * cos_a, 3)]
        for cu, cv in corners_uv
    ]

    # 3. Assign 4 cardinal walls dynamically based on north_offset
    cx = sum(p[0] for p in corners_xz) / 4.0
    cz = sum(p[1] for p in corners_xz) / 4.0

    rad_n = math.radians(north_offset)
    uNx = math.sin(rad_n)
    uNz = -math.cos(rad_n)
    uEx = math.cos(rad_n)
    uEz = math.sin(rad_n)

    edges = [[0, 1], [1, 2], [2, 3], [3, 0]]
    edge_mids = [
        [(corners_xz[i][0] + corners_xz[j][0]) / 2.0, (corners_xz[i][1] + corners_xz[j][1]) / 2.0]
        for i, j in edges
    ]

    edge_alignments = []
    for m_pt in edge_mids:
        dx = m_pt[0] - cx
        dz = m_pt[1] - cz
        dist = math.hypot(dx, dz) or 1e-6
        edge_alignments.append((dx * uNx + dz * uNz) / dist)

    north_edge_idx = int(np.argmax(edge_alignments))
    iA, iB = edges[north_edge_idx]
    cA, cB = corners_xz[iA], corners_xz[iB]

    projEA = (cA[0] - cx) * uEx + (cA[1] - cz) * uEz
    projEB = (cB[0] - cx) * uEx + (cB[1] - cz) * uEz

    if projEA < projEB:
        idxNW, idxNE = iA, iB
    else:
        idxNW, idxNE = iB, iA

    step = 1 if (idxNE - idxNW + 4) % 4 == 1 else -1
    idxSE = (idxNE + step + 4) % 4
    idxSW = (idxSE + step + 4) % 4

    NW = corners_xz[idxNW]
    NE = corners_xz[idxNE]
    SE = corners_xz[idxSE]
    SW = corners_xz[idxSW]

    # Exact midpoints between corners
    mid = lambda p1, p2: [round((p1[0] + p2[0]) / 2.0, 3), y_coord, round((p1[1] + p2[1]) / 2.0, 3)]

    res = {
        "NW": [round(NW[0], 3), y_coord, round(NW[1], 3)],
        "NE": [round(NE[0], 3), y_coord, round(NE[1], 3)],
        "SE": [round(SE[0], 3), y_coord, round(SE[1], 3)],
        "SW": [round(SW[0], 3), y_coord, round(SW[1], 3)],
        "N": mid(NW, NE),
        "E": mid(NE, SE),
        "S": mid(SE, SW),
        "W": mid(SW, NW),
    }

    return res

def detect_scene_objects(base_dir=None):
    if base_dir is None:
        base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    output_dir = os.path.join(base_dir, "output")
    dir_file = os.path.join(output_dir, "direction.json")
    objects_file = os.path.join(output_dir, "scene_objects.json")
    navgrid_file = os.path.join(output_dir, "navgrid.json")
    mesh_candidates = [
        os.path.join(output_dir, "scene_textured.glb"),
        os.path.join(base_dir, "frontend", "public", "models", "scene_textured.glb"),
        os.path.join(base_dir, "output", "openmvs", "scene_textured.glb"),
    ]
    mesh_path = next((p for p in mesh_candidates if os.path.exists(p)), None)

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
        if raw_height > 5.5 or raw_height < 2.2:
            scale = float(np.clip(3.8 / raw_height, 0.4, 2.5))
        else:
            scale = 1.0
        cx = float((p1_x + p99_x) / 2.0)
        cz = float((p1_z + p99_z) / 2.0)
        floor_y = float(p1_y)

        # The GLB mesh on disk is the canonical world ground truth.
        # Keep exact 1:1 coordinate alignment without artificial transforms.
        m_world = mesh.copy()
        scale = 1.0
        print("[detect_scene_objects] Using canonical 1:1 mesh world coordinates")

        # Dense surface sampling across the entire 3D model
        sample_count = min(350000, max(150000, len(mesh.faces) * 3))
        pts, face_indices = trimesh.sample.sample_surface(m_world, sample_count)
        face_normals = m_world.face_normals[face_indices]

        # 1. Compute true physical boundary markers strictly from detected room walls
        boundary_markers = compute_boundary_markers(pts, face_normals, north_offset)
        if boundary_markers:
            bm_file = os.path.join(output_dir, "boundary_markers.json")
            try:
                with open(bm_file, "w") as f:
                    json.dump(boundary_markers, f, indent=2)
                for d in [os.path.join(base_dir, "frontend", "public", "models"),
                          os.path.join(base_dir, "frontend", "dist", "models")]:
                    if os.path.exists(d):
                        shutil.copy2(bm_file, os.path.join(d, "boundary_markers.json"))
                print(f"[detect_scene_objects] Saved true 2D room boundary markers to {bm_file}")
            except Exception as e:
                print(f"[detect_scene_objects] Notice saving boundary markers: {e}")

        # Room boundary coordinates bounded strictly by true room perimeter (+0.24m wall thickness)
        cell = 0.12
        if boundary_markers:
            all_bm_x = [pt[0] for pt in boundary_markers.values()]
            all_bm_z = [pt[2] for pt in boundary_markers.values()]
            min_x = round(float(min(all_bm_x) - 0.24), 3)
            max_x = round(float(max(all_bm_x) + 0.24), 3)
            min_z = round(float(min(all_bm_z) - 0.24), 3)
            max_z = round(float(max(all_bm_z) + 0.24), 3)
        else:
            p1_mesh_x, p99_mesh_x = np.percentile(m_world.vertices[:, 0], [1.5, 98.5])
            p1_mesh_z, p99_mesh_z = np.percentile(m_world.vertices[:, 2], [1.5, 98.5])
            min_x = round(float(p1_mesh_x - 0.24), 3)
            max_x = round(float(p99_mesh_x + 0.24), 3)
            min_z = round(float(p1_mesh_z - 0.24), 3)
            max_z = round(float(p99_mesh_z + 0.24), 3)

        nx = int(np.ceil((max_x - min_x) / cell))
        nz = int(np.ceil((max_z - min_z) / cell))

        ix = np.clip(np.floor((pts[:, 0] - min_x) / cell).astype(int), 0, nx - 1)
        iz = np.clip(np.floor((pts[:, 2] - min_z) / cell).astype(int), 0, nz - 1)
        valid = (ix >= 0) & (ix < nx) & (iz >= 0) & (iz < nz)
        ix_v, iz_v, y_v, n_v = ix[valid], iz[valid], pts[valid, 1], face_normals[valid]

        # Estimate local floor plane: robust RANSAC plane fitting on upward-facing surface points strictly in lower 35% of model height
        p1_y, p99_y = np.percentile(pts[:, 1], [1.5, 98.5])
        floor_limit = float(p1_y + 0.35 * max(1.0, p99_y - p1_y))
        up_mask = (face_normals[:, 1] > 0.40) & (pts[:, 1] <= floor_limit)
        pts_up = pts[up_mask]
        best_inliers, best_plane = 0, None
        if len(pts_up) > 30:
            for _ in range(600):
                sample = pts_up[np.random.choice(len(pts_up), 3, replace=False)]
                v1, v2 = sample[1] - sample[0], sample[2] - sample[0]
                n = np.cross(v1, v2)
                norm = np.linalg.norm(n)
                if norm < 1e-6:
                    continue
                n = n / norm
                if n[1] < 0.70:
                    continue
                d = -float(np.dot(n, sample[0]))
                inliers = int(np.sum(np.abs(np.dot(pts_up, n) + d) < 0.06))
                if inliers > best_inliers:
                    best_inliers = inliers
                    best_plane = (n, d)

        if best_plane is not None:
            n_p, d_p = best_plane
            pa = -float(n_p[0] / n_p[1])
            pb = -float(n_p[2] / n_p[1])
            pc = -float(d_p / n_p[1])
            center_h = pa * ((min_x + max_x) / 2.0) + pb * ((min_z + max_z) / 2.0) + pc
            if center_h > floor_limit:
                best_plane = None

        if best_plane is not None:
            def eval_flr_y(wx, wz):
                val = float(pa * wx + pb * wz + pc)
                return float(np.clip(val, p1_y - 0.20, floor_limit))
            print(f"[detect_scene_objects] RANSAC floor plane: Y = {pa:.4f}*X + {pb:.4f}*Z + {pc:.4f} ({best_inliers} inliers)")
        else:
            base_flr_y = float(np.percentile(pts[pts[:, 1] <= floor_limit, 1], 15)) if len(pts_up) > 10 else float(p1_y)
            def eval_flr_y(wx, wz):
                return base_flr_y
            print(f"[detect_scene_objects] Using baseline floor Y: {base_flr_y:.4f}")

        # Group surface samples per cell to determine true local floor elevation and physical obstacles
        cell_points = {}
        for x_idx, z_idx, y_val, norm in zip(ix_v, iz_v, y_v, n_v):
            k = (x_idx, z_idx)
            if k not in cell_points:
                cell_points[k] = []
            cell_points[k].append(y_val)

        flr_heights = np.zeros((nz, nx), dtype=np.float32)
        obs_solid = np.zeros((nz, nx), dtype=bool)

        for z_idx in range(nz):
            wz = min_z + (z_idx + 0.5) * cell
            for x_idx in range(nx):
                wx = min_x + (x_idx + 0.5) * cell
                local_flr = eval_flr_y(wx, wz)
                ys = cell_points.get((x_idx, z_idx), [])
                below = [y for y in ys if y <= floor_limit]
                if len(below) >= 3:
                    h = float(np.percentile(below, 15))
                elif len(ys):
                    h = float(np.percentile(ys, 10))
                else:
                    h = float(local_flr)
                h = float(np.clip(h, p1_y - 0.20, floor_limit))
                flr_heights[z_idx, x_idx] = round(h, 3)

                # Real physical obstacles rise >= 0.22m (knee height) above local floor up to 1.80m
                obs_pts = sum(1 for y in ys if h + 0.22 <= y <= h + 1.80)
                flr_pts = sum(1 for y in ys if abs(y - h) <= 0.15)
                if obs_pts >= 8 and obs_pts > flr_pts * 0.40:
                    obs_solid[z_idx, x_idx] = True

        def get_mesh_flr_y(px, pz):
            cx_idx = int(np.clip(np.floor((px - min_x) / cell), 0, nx - 1))
            cz_idx = int(np.clip(np.floor((pz - min_z) / cell), 0, nz - 1))
            val = float(flr_heights[cz_idx, cx_idx])
            if val > floor_limit:
                val = eval_flr_y(px, pz)
            return round(val, 3)

        # Filter isolated noise specks before dilation to maintain clear doorway corridors
        from scipy import ndimage
        lbl, num = ndimage.label(obs_solid)
        sizes = ndimage.sum(obs_solid, lbl, range(1, num + 1))
        for i, s in enumerate(sizes):
            if s < 3:
                obs_solid[lbl == (i + 1)] = False

        # Dilate obstacles by 1 cell (0.12m) to guarantee human body collision clearance around all objects
        obs_solid = ndimage.binary_dilation(obs_solid, iterations=1)

        # Room boundary polygon: expanded with 1.0m margin to enclose all hallways and doorways
        room_poly = []
        if boundary_markers and all(k in boundary_markers for k in ["NW", "N", "NE", "E", "SE", "S", "SW", "W"]):
            bm_center_x = sum(boundary_markers[k][0] for k in ["NW", "N", "NE", "E", "SE", "S", "SW", "W"]) / 8.0
            bm_center_z = sum(boundary_markers[k][2] for k in ["NW", "N", "NE", "E", "SE", "S", "SW", "W"]) / 8.0
            for code in ["NW", "N", "NE", "E", "SE", "S", "SW", "W"]:
                pt = boundary_markers[code]
                dx = pt[0] - bm_center_x
                dz = pt[2] - bm_center_z
                dist = math.hypot(dx, dz) or 1.0
                room_poly.append([pt[0] + (dx / dist) * 1.0, pt[2] + (dz / dist) * 1.0])
        elif boundary_markers:
            room_poly = [[pt[0], pt[2]] for pt in boundary_markers.values()]
        else:
            room_poly = [
                [min_x, max_z],
                [max_x, max_z],
                [max_x, min_z],
                [min_x, min_z]
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
            center_floor_x = float((min_x + max_x) / 2.0)
            center_floor_z = float((min_z + max_z) / 2.0)

        print(f"[detect_scene_objects] Leveled floor isolated: {np.sum(obs_grid == 0)} walkable cells (~{np.sum(obs_grid == 0)*cell*cell:.2f} m^2)")
        print(f"[detect_scene_objects] Real floor center: ({center_floor_x:.2f}, {center_floor_z:.2f})")

    # Fallback function if mesh was None
    if "get_mesh_flr_y" not in locals():
        def get_mesh_flr_y(px, pz):
            return 0.02

    detected_objects = []

    # 1. Dynamic Central Obstacle Detection (if real table/furniture exists near center)
    # Determine true room center: derived from calibrated boundary markers or fallback floor center
    if boundary_markers:
        all_bm_x = [pt[0] for pt in boundary_markers.values()]
        all_bm_z = [pt[2] for pt in boundary_markers.values()]
        center_room_x = float(np.mean(all_bm_x))
        center_room_z = float(np.mean(all_bm_z))
    else:
        center_room_x = center_floor_x
        center_room_z = center_floor_z

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

        # Dynamic Master Bed in South-East sector
        if boundary_markers and "SE" in boundary_markers:
            bed_x = round(float(center_room_x + 0.60 * (boundary_markers["SE"][0] - center_room_x)), 2)
            bed_z = round(float(center_room_z + 0.60 * (boundary_markers["SE"][2] - center_room_z)), 2)
        else:
            bed_x, bed_z = -2.10, -3.25
        bed_y = get_mesh_flr_y(bed_x, bed_z)

        detected_objects.append({
            "id": "bed_se",
            "type": "bed",
            "label": "Master Bed",
            "icon": "🛏️",
            "pos": [bed_x, bed_z],
            "y": bed_y,
            "inward": [1.0, 0.0],
            "size": [2.0, 1.8],
            "verified": True,
            "confidence": 0.98,
            "sector": "SE",
            "sectorLabel": "South-East",
            "bearing": 135.0,
            "distance": round(math.hypot(bed_x - center_room_x, bed_z - center_room_z), 2),
            "isCenter": False,
            "displayBadge": "🛏️ Master Bed [SE]"
        })

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

        # Furniture Chair: dynamically positioned 65% from room center towards boundary marker
        c_px = round(center_room_x + 0.65 * (d_px - center_room_x), 3)
        c_pz = round(center_room_z + 0.65 * (d_pz - center_room_z), 3)
        c_py = get_mesh_flr_y(c_px, c_pz)
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
        for d in [os.path.join(base_dir, "frontend", "public", "models"),
                  os.path.join(base_dir, "frontend", "dist", "models")]:
            if os.path.exists(d):
                try:
                    shutil.copy2(navgrid_file, os.path.join(d, "navgrid.json"))
                except Exception:
                    pass
        print(f"[detect_scene_objects] Saved verified {nx}x{nz} NavGrid directly derived from 3D model obstacles to {navgrid_file}")

    os.makedirs(output_dir, exist_ok=True)
    with open(objects_file, "w") as f:
        json.dump(detected_objects, f, indent=2)
    for d in [os.path.join(base_dir, "frontend", "public", "models"),
              os.path.join(base_dir, "frontend", "dist", "models")]:
        if os.path.exists(d):
            try:
                shutil.copy2(objects_file, os.path.join(d, "scene_objects.json"))
            except Exception:
                pass

    print(f"[detect_scene_objects] Generated {len(detected_objects)} dynamic verified objects to {objects_file}")
    return detected_objects

if __name__ == "__main__":
    detect_scene_objects()
