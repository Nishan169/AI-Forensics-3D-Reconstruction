#!/usr/bin/env python3
import os
import sys
import math
import shutil
import subprocess
from pathlib import Path
import numpy as np
import trimesh

def main():
    root_dir = Path(__file__).resolve().parent
    model_path = root_dir / "output" / "scene_textured.glb"

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

    # 180 degrees rotation around X-axis
    matrix = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    scene.apply_transform(matrix)

    # Export flipped GLB
    scene.export(str(model_path))
    print(f"[FlipGLB] Successfully flipped and saved: {model_path}")

    # Synchronize to frontend models
    for dest_dir in [root_dir / "frontend" / "public" / "models", root_dir / "frontend" / "dist" / "models"]:
        if dest_dir.exists():
            shutil.copy2(model_path, dest_dir / "scene_textured.glb")

    # Re-calibrate compass direction and scene objects
    calib_script = root_dir / "scripts" / "calibrate_direction.py"
    if calib_script.exists():
        try:
            print("[FlipGLB] Re-calibrating compass direction...")
            subprocess.run([sys.executable, str(calib_script)], cwd=str(root_dir), check=False)
        except Exception as e:
            print(f"[FlipGLB] Calibrate notice: {e}")

    detect_script = root_dir / "scripts" / "detect_scene_objects.py"
    if detect_script.exists():
        try:
            print("[FlipGLB] Re-detecting scene objects...")
            subprocess.run([sys.executable, str(detect_script)], cwd=str(root_dir), check=False)
        except Exception as e:
            print(f"[FlipGLB] Objects notice: {e}")

if __name__ == "__main__":
    main()
