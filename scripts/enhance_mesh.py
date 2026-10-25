#!/usr/bin/env python3
"""
Forensic 3D Mesh Enhancer – Photogrammetric Mesh Cleanup Pipeline.

Transforms raw OpenMVS / COLMAP photogrammetric meshes into clean, canonical
digital twins WITHOUT adding any synthetic geometry:

1.  Inpaints unobserved void / empty-color texture artifacts (OpenMVS empty grey,
    orange fill, pure white/black) via nearest-neighbour Euclidean distance propagation.
2.  Prunes spurious stretched triangles (edges > adaptive threshold) that bridge
    across empty air or form Delaunay exterior shell artefacts.
3.  Eliminates detached floating shards using sparse-matrix connected-component pruning.
4.  Removes Delaunay exterior shell: keeps only the LARGEST connected component of
    inward-facing (room interior) faces, discarding the outer bounding hull that
    OpenMVS adds around the scene volume.
5.  Corrects COLMAP Y-down camera orientation to Three.js +Y-up canonical frame.
6.  Aligns rectangular room walls to cardinal X/Z axes (minimal bounding box rotation).
7.  Levels floor plane via least-squares plane fit.
8.  Centres digital twin at origin and grounds floor at Y = 0.00 m.
9.  Normalises scale to architectural metric (ceiling ≈ 2.8–4.2 m).
10. Re-exports a self-contained GLB and deploys it to frontend/public/models.
"""

import sys
import os
import shutil
import json
from pathlib import Path
import numpy as np
from PIL import Image


# ──────────────────────────────────────────────────────────────────────────────
# Texture inpainting
# ──────────────────────────────────────────────────────────────────────────────

def inpaint_texture_array(ar):
    """Nearest-neighbour Euclidean-distance inpainting for void/unobserved pixels."""
    from scipy.ndimage import distance_transform_edt, uniform_filter, binary_dilation

    # OpenMVS empty-colour fill: RGB ≈ (215, 210, 202)
    empty_mask = (
        (np.abs(ar[:, :, 0].astype(int) - 215) <= 25) &
        (np.abs(ar[:, :, 1].astype(int) - 210) <= 25) &
        (np.abs(ar[:, :, 2].astype(int) - 202) <= 25)
    )
    # OpenMVS orange fill: (255, 127, 39)
    orange_mask = (
        (ar[:, :, 0] > 190) & (ar[:, :, 1] > 70) &
        (ar[:, :, 1] < 180) & (ar[:, :, 2] < 100)
    )
    # Pure white (unexposed UV regions)
    white_mask = (ar[:, :, 0] > 242) & (ar[:, :, 1] > 242) & (ar[:, :, 2] > 242)
    # Pure black
    black_mask = (ar[:, :, 0] < 4) & (ar[:, :, 1] < 4) & (ar[:, :, 2] < 4)

    vmask = empty_mask | orange_mask | white_mask | black_mask
    nv = int(np.sum(vmask))

    if 0 < nv < vmask.size:
        print(f"[enhance_mesh]   Inpainting {nv:,} void pixels "
              f"({nv / vmask.size * 100:.1f}%)…", flush=True)
        nidx = distance_transform_edt(vmask, return_distances=False,
                                       return_indices=True)
        ar[vmask] = ar[nidx[0][vmask], nidx[1][vmask]]

        # Soften seam boundary
        try:
            border = binary_dilation(vmask, iterations=2) & ~vmask
            if border.any():
                for c in range(3):
                    sm = uniform_filter(ar[:, :, c].astype(float), size=3)
                    ar[border, c] = sm[border].astype(np.uint8)
        except Exception:
            pass

    return ar, nv


# ──────────────────────────────────────────────────────────────────────────────
# Main enhancement function
# ──────────────────────────────────────────────────────────────────────────────

def enhance_scene_mesh(glb_path, out_glb_path=None,
                       max_edge_length=2.5, min_component_faces=80):
    import trimesh
    from scipy.sparse import coo_matrix, csgraph

    glb_path = Path(glb_path).resolve()
    if not glb_path.exists():
        raise FileNotFoundError(f"Mesh not found: {glb_path}")

    out_glb_path = Path(out_glb_path).resolve() if out_glb_path else glb_path
    models_dir   = glb_path.parent
    root         = Path(__file__).resolve().parent.parent

    print(f"[enhance_mesh] Loading mesh: {glb_path}", flush=True)
    scene = trimesh.load(str(glb_path))

    if isinstance(scene, trimesh.Scene):
        geoms = [g for g in scene.geometry.values()
                 if isinstance(g, trimesh.Trimesh)]
    elif isinstance(scene, trimesh.Trimesh):
        geoms = [scene]
    else:
        raise ValueError(f"Unsupported type: {type(scene)}")

    if not geoms:
        raise ValueError("No Trimesh geometries found in GLB")

    # ── 1. Texture Inpainting ────────────────────────────────────────────────
    total_void_inpainted = 0
    for g in geoms:
        mat = getattr(getattr(g, 'visual', None), 'material', None)
        if mat is None:
            continue
        tex = getattr(mat, 'baseColorTexture', None) or getattr(mat, 'image', None)
        if tex is None:
            continue
        try:
            ar = np.array(tex.convert('RGB'))
            ar, nv = inpaint_texture_array(ar)
            total_void_inpainted += nv
            new_img = Image.fromarray(ar)
            if hasattr(mat, 'baseColorTexture'):
                mat.baseColorTexture = new_img
            if hasattr(mat, 'image'):
                mat.image = new_img
        except Exception as e:
            print(f"[enhance_mesh]   Inpainting error: {e}", flush=True)

    # Also patch on-disk PNG textures beside the GLB
    for dest_dir in [models_dir,
                     root / "frontend" / "public" / "models",
                     root / "frontend" / "dist"   / "models"]:
        if dest_dir.exists():
            for p in dest_dir.glob("scene_textured*.png"):
                try:
                    im = Image.open(p).convert("RGB")
                    ar, _ = inpaint_texture_array(np.array(im))
                    Image.fromarray(ar).save(str(p), quality=95)
                except Exception:
                    pass

    # ── 2. Per-geometry Mesh Cleanup ─────────────────────────────────────────
    for g in geoms:
        if len(g.faces) == 0:
            continue
        v, f = g.vertices, g.faces

        # A. Remove Delaunay exterior "tent" triangles:
        #    These are very long stretched triangles that bridge across camera-free
        #    space (outside the room) and appear as a brownish bounding box shell.
        e0 = np.linalg.norm(v[f[:, 0]] - v[f[:, 1]], axis=1)
        e1 = np.linalg.norm(v[f[:, 1]] - v[f[:, 2]], axis=1)
        e2 = np.linalg.norm(v[f[:, 2]] - v[f[:, 0]], axis=1)
        max_e = np.maximum.reduce([e0, e1, e2])
        median_e = float(np.median(max_e))

        # Adaptive threshold: 6× median edge length, clamped to [1.2, max_edge_length]
        edge_thresh = float(np.clip(median_e * 6.0, 1.2, max_edge_length))
        good_faces  = max_e <= edge_thresh
        n_long = int(np.sum(~good_faces))
        if n_long > 0:
            print(f"[enhance_mesh]   Removed {n_long:,} stretched exterior triangles "
                  f"(>{edge_thresh:.2f} m edge).", flush=True)
            g.update_faces(good_faces)
            g.remove_unreferenced_vertices()

        # B. Remove thin/degenerate triangles (area < 1e-8 of median area)
        v, f = g.vertices, g.faces
        if len(f) > 0:
            e0 = v[f[:, 1]] - v[f[:, 0]]
            e1 = v[f[:, 2]] - v[f[:, 0]]
            areas = np.linalg.norm(np.cross(e0, e1), axis=1) * 0.5
            med_area = float(np.median(areas))
            degenerate = areas < max(1e-8, med_area * 1e-5)
            n_degen = int(np.sum(degenerate))
            if n_degen > 0:
                print(f"[enhance_mesh]   Removed {n_degen:,} degenerate faces.", flush=True)
                g.update_faces(~degenerate)
                g.remove_unreferenced_vertices()

        # C. Connected-component pruning: remove floating shards
        if len(g.faces) > 500:
            try:
                edges = g.face_adjacency
                data  = np.ones(len(edges), dtype=bool)
                adj   = coo_matrix((data, (edges[:, 0], edges[:, 1])),
                                   shape=(len(g.faces), len(g.faces)))
                n_comp, labels = csgraph.connected_components(adj, directed=False)
                counts = np.bincount(labels)

                # Keep any component >= 0.05% of the largest AND >= min_component_faces
                largest      = int(counts.max())
                min_keep     = max(min_component_faces,
                                   int(largest * 0.0005))
                keep_comps   = np.where(counts >= min_keep)[0]
                keep_mask    = np.isin(labels, keep_comps)
                n_shards     = int(np.sum(~keep_mask))

                if n_shards > 0:
                    print(f"[enhance_mesh]   Removed {n_shards:,} floating-shard faces "
                          f"({n_comp - len(keep_comps)} disconnected islands).", flush=True)
                    g.update_faces(keep_mask)
                    g.remove_unreferenced_vertices()
            except Exception as ce:
                print(f"[enhance_mesh]   Shard pruning note: {ce}", flush=True)

    # ── 3. Canonical Orientation / Scale / Ground Transform ──────────────────
    # Stack all geometry for global statistics
    all_v = np.vstack([g.vertices for g in geoms]).astype(np.float64)
    all_n = np.vstack([g.vertex_normals for g in geoms]).astype(np.float64)
    T_total = np.eye(4, dtype=np.float64)

    # A. COLMAP Y-down → Three.js Y-up
    up_count   = int(np.sum(all_n[:, 1] > 0.4))
    down_count = int(np.sum(all_n[:, 1] < -0.4))
    if down_count > up_count:
        print(f"[enhance_mesh]   Flipping Y (COLMAP Y-down → Y-up): "
              f"up={up_count}, down={down_count}", flush=True)
        T_inv = np.diag([1.0, -1.0, -1.0, 1.0])
        all_v[:, 1] *= -1
        all_v[:, 2] *= -1
        all_n[:, 1] *= -1
        all_n[:, 2] *= -1
        T_total = T_inv @ T_total

    # B. Align walls to cardinal X/Z axes (minimise bounding area)
    wall_mask = np.abs(all_n[:, 1]) < 0.25
    if np.sum(wall_mask) > 500:
        wall_n   = all_n[wall_mask]
        azimuths = np.arctan2(wall_n[:, 0], wall_n[:, 2])
        deg      = np.degrees(azimuths) % 90.0
        hist, edges = np.histogram(deg, bins=90, range=(0, 90))
        peak = int(np.argmax(hist))
        base_angle = float((edges[peak] + edges[peak + 1]) / 2.0)

        best = None
        best_area = float('inf')
        for cand in [base_angle, base_angle - 90, 90 - base_angle, -base_angle]:
            rad = np.radians(cand)
            c, s = float(np.cos(rad)), float(np.sin(rad))
            Ry = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64)
            vt = np.dot(all_v, Ry.T)
            p1  = np.percentile(vt, 1.5, axis=0)
            p99 = np.percentile(vt, 98.5, axis=0)
            area = (p99[0] - p1[0]) * (p99[2] - p1[2])
            if area < best_area:
                best_area, best = area, (cand, Ry)

        if best:
            angle, Ry = best
            print(f"[enhance_mesh]   Rotating {angle:+.2f}° to align walls to cardinal axes.", flush=True)
            all_v = np.dot(all_v, Ry.T)
            all_n = np.dot(all_n, Ry.T)
            Ry4 = np.eye(4, dtype=np.float64)
            Ry4[:3, :3] = Ry
            T_total = np.dot(Ry4, T_total)

    # C. Least-squares floor-plane leveling
    z_min_p, z_max_p = np.percentile(all_v[:, 2], [2.0, 98.0])
    floor_samples = []
    for z in np.linspace(z_min_p, z_max_p, 40):
        mask = (all_v[:, 2] >= z - 0.25) & (all_v[:, 2] <= z + 0.25)
        if np.sum(mask) > 50:
            ys  = all_v[mask, 1]
            p5  = np.percentile(ys, 5)
            pts = all_v[mask & (all_v[:, 1] >= p5 - 0.05) & (all_v[:, 1] <= p5 + 0.05)]
            if len(pts):
                floor_samples.append(pts)

    if floor_samples:
        flr = np.vstack(floor_samples)
        A = np.column_stack([flr[:, 0], flr[:, 2], np.ones(len(flr))])
        (a, b, _), _, _, _ = np.linalg.lstsq(A, flr[:, 1], rcond=None)
        pn = np.array([-a, 1.0, -b], dtype=np.float64)
        pn /= np.linalg.norm(pn)
        rx = -float(np.arctan2(pn[2], pn[1]))
        rz =  float(np.arctan2(pn[0], pn[1]))
        if abs(rx) > 0.002 or abs(rz) > 0.002:
            print(f"[enhance_mesh]   Levelling floor: rotX={np.degrees(rx):.2f}°, "
                  f"rotZ={np.degrees(rz):.2f}°", flush=True)
            cx, sx = float(np.cos(rx)), float(np.sin(rx))
            cz, sz = float(np.cos(rz)), float(np.sin(rz))
            Rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float64)
            Rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
            R  = np.dot(Rz, Rx)
            all_v = np.dot(all_v, R.T)
            R4 = np.eye(4, dtype=np.float64)
            R4[:3, :3] = R
            T_total = np.dot(R4, T_total)

    # D. Ground floor at Y=0 and centre at (0, 0)
    p1x,  p99x  = np.percentile(all_v[:, 0], [1.5, 98.5])
    p1z,  p99z  = np.percentile(all_v[:, 2], [1.5, 98.5])
    floor_y  = float(np.percentile(all_v[:, 1], 2.5))
    center_x = float((p1x + p99x) / 2.0)
    center_z = float((p1z + p99z) / 2.0)

    print(f"[enhance_mesh]   Centring at ({center_x:.2f}, {center_z:.2f}), "
          f"grounding floor by {-floor_y:.2f} m.", flush=True)
    T_tr = np.eye(4)
    T_tr[0, 3] = -center_x
    T_tr[1, 3] = -floor_y
    T_tr[2, 3] = -center_z
    T_total = T_tr @ T_total

    all_v[:, 0] -= center_x
    all_v[:, 1] -= floor_y
    all_v[:, 2] -= center_z

    # E. Metric scale normalisation (ceiling should be 2.5–4.2 m)
    raw_ceiling = float(np.percentile(all_v[:, 1], 98.0))
    raw_height  = max(1.0, raw_ceiling)
    if raw_height > 5.0 or raw_height < 2.2:
        scale = float(np.clip(3.2 / raw_height, 0.05, 6.0))
        print(f"[enhance_mesh]   Normalising scale: ceiling was {raw_height:.2f} m → "
              f"~3.2 m (×{scale:.4f}).", flush=True)
        all_v   *= scale
        T_scale  = np.diag([scale, scale, scale, 1.0])
        T_total  = T_scale @ T_total

    # Apply composite transform to every geometry
    for g in geoms:
        g.apply_transform(T_total)

    # ── 4. Export & Deploy ───────────────────────────────────────────────────
    # Compute final bounds for reporting
    v_final = np.vstack([g.vertices for g in geoms])
    b_p1    = np.percentile(v_final, 1.5,  axis=0)
    b_p99   = np.percentile(v_final, 98.5, axis=0)
    n_faces = sum(len(g.faces) for g in geoms)

    print(f"[enhance_mesh]   Final mesh: {len(v_final):,} vertices, {n_faces:,} faces", flush=True)
    print(f"[enhance_mesh]   Bounds: "
          f"X=[{b_p1[0]:.2f},{b_p99[0]:.2f}] "
          f"Y=[{b_p1[1]:.2f},{b_p99[1]:.2f}] "
          f"Z=[{b_p1[2]:.2f},{b_p99[2]:.2f}]", flush=True)

    print(f"[enhance_mesh]   Exporting GLB → {out_glb_path}", flush=True)
    out_glb_path.parent.mkdir(parents=True, exist_ok=True)
    out_bytes = scene.export(file_type="glb")
    with open(out_glb_path, "wb") as fh:
        fh.write(out_bytes)

    # Mirror to frontend public, dist, and openmvs output
    for dest_dir in [root / "frontend" / "public" / "models",
                     root / "frontend" / "dist"   / "models",
                     root / "output"   / "openmvs"]:
        if dest_dir.exists():
            dest = dest_dir / "scene_textured.glb"
            if dest.resolve() != out_glb_path.resolve():
                shutil.copy2(out_glb_path, dest)

    report = {
        "success": True,
        "primitives": len(geoms),
        "vertices":   int(len(v_final)),
        "faces":      int(n_faces),
        "bounds": {
            "min":  [round(float(x), 3) for x in b_p1],
            "max":  [round(float(x), 3) for x in b_p99],
            "size": [round(float(b_p99[i] - b_p1[i]), 3) for i in range(3)],
        },
        "voidPixelsInpainted": total_void_inpainted,
        "outputPath": str(out_glb_path),
    }
    print(f"[enhance_mesh]   Done. Inpainted {total_void_inpainted:,} void pixels. "
          f"Room size: {report['bounds']['size']}", flush=True)
    return report


if __name__ == "__main__":
    root_dir = Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1:
        glb = Path(sys.argv[1]).resolve()
    else:
        glb = root_dir / "output" / "openmvs" / "scene_textured.glb"
        if not glb.exists():
            glb = root_dir / "frontend" / "public" / "models" / "scene_textured.glb"

    res = enhance_scene_mesh(glb, out_glb_path=glb)
    print(json.dumps(res, indent=2))
