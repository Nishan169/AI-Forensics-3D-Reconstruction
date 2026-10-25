/**
 * Forensic 3D Navigation Grid & A* Obstacle-Avoiding Path Planner
 *
 * Recreates the exact collision and obstacle-avoidance behavior of Dummy_3D:
 * - 2D floor occupancy grid (cell size 0.1m)
 * - Furniture and solid structure detection (knee-to-head height: 0.25m - 1.70m above floor)
 * - 8-way A* path search with MinHeap priority queue
 * - Diagonal corner-cutting prevention
 * - Line-of-sight (LOS) raycast shortcut smoothing
 */
import fs from "fs";
import path from "path";

const MOVES = [
  [1, 0, 1.0],
  [-1, 0, 1.0],
  [0, 1, 1.0],
  [0, -1, 1.0],
  [1, 1, 1.414],
  [1, -1, 1.414],
  [-1, 1, 1.414],
  [-1, -1, 1.414]
];

class MinHeap {
  constructor() {
    this.heap = [];
  }
  push(node) {
    this.heap.push(node);
    let i = this.heap.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (this.heap[p].f <= this.heap[i].f) break;
      const tmp = this.heap[p];
      this.heap[p] = this.heap[i];
      this.heap[i] = tmp;
      i = p;
    }
  }
  pop() {
    if (this.heap.length === 0) return null;
    const top = this.heap[0];
    const end = this.heap.pop();
    if (this.heap.length > 0) {
      this.heap[0] = end;
      let i = 0;
      const len = this.heap.length;
      while (true) {
        let left = (i << 1) + 1;
        let right = left + 1;
        let smallest = i;
        if (left < len && this.heap[left].f < this.heap[smallest].f) smallest = left;
        if (right < len && this.heap[right].f < this.heap[smallest].f) smallest = right;
        if (smallest === i) break;
        const tmp = this.heap[i];
        this.heap[i] = this.heap[smallest];
        this.heap[smallest] = tmp;
        i = smallest;
      }
    }
    return top;
  }
  get size() {
    return this.heap.length;
  }
}

export class NavGrid {
  constructor(obs, origin, cell = 0.1, nx, nz, heights = null) {
    this.obs = obs; // Uint8Array(nx * nz), 1 = obstacle, 0 = walkable
    this.origin = [Number(origin[0]), Number(origin[1])];
    this.cell = cell;
    this.nx = nx;
    this.nz = nz;
    this.heights = heights;
  }

  getFloorY(x, z) {
    if (!this.heights || this.heights.length === 0) return 0.02;
    // Support both cell indices (cx, cz) and world coordinates (x, z)
    let ix, iz;
    if (Number.isInteger(x) && Number.isInteger(z) && x >= 0 && x < this.nx && z >= 0 && z < this.nz) {
      ix = x;
      iz = z;
    } else {
      ix = Math.floor((x - this.origin[0]) / this.cell);
      iz = Math.floor((z - this.origin[1]) / this.cell);
    }
    if (ix < 0 || ix >= this.nx || iz < 0 || iz >= this.nz) return 0.02;
    const val = this.heights[ix + iz * this.nx];
    return (val !== undefined && !isNaN(val)) ? Number(val) : 0.02;
  }

  _ij(p) {
    const ix = Math.floor((p[0] - this.origin[0]) / this.cell);
    const iz = Math.floor((p[1] - this.origin[1]) / this.cell);
    return [
      Math.min(this.nx - 1, Math.max(0, ix)),
      Math.min(this.nz - 1, Math.max(0, iz))
    ];
  }

  _xz(ix, iz) {
    return [
      Number((this.origin[0] + (ix + 0.5) * this.cell).toFixed(3)),
      Number((this.origin[1] + (iz + 0.5) * this.cell).toFixed(3))
    ];
  }

  _free(cellCoords) {
    const [cx, cz] = cellCoords;
    if (!this.obs[cx + cz * this.nx]) return cellCoords;

    // Expand search ring outward to find closest walkable cell
    for (let rad = 1; rad < 25; rad++) {
      for (let dz = -rad; dz <= rad; dz++) {
        for (let dx = -rad; dx <= rad; dx++) {
          if (Math.abs(dx) !== rad && Math.abs(dz) !== rad) continue;
          const xx = cx + dx, zz = cz + dz;
          if (xx >= 0 && xx < this.nx && zz >= 0 && zz < this.nz) {
            if (!this.obs[xx + zz * this.nx]) {
              const [wx, wz] = this._xz(xx, zz);
              if (this.isInsideFloor(wx, wz, 0.10)) {
                return [xx, zz];
              }
            }
          }
        }
      }
    }
    return cellCoords;
  }

  getFreePosition(pt) {
    const cell = this._free(this._ij(pt));
    return this._xz(cell[0], cell[1]);
  }

  /**
   * Finds the nearest walkable cell that guarantees a physical standoff clearance (default 0.45m)
   * from any room obstacle, furniture footprint, or wall.
   */
  getFreePositionWithClearance(pt, clearance = 0.45) {
    const centerCell = this._ij(pt);
    const rCells = Math.max(1, Math.ceil(clearance / this.cell));

    const hasClearance = (cx, cz, radius) => {
      if (cx < 0 || cx >= this.nx || cz < 0 || cz >= this.nz) return false;
      if (this.obs[cx + cz * this.nx]) return false;
      const [wx, wz] = this._xz(cx, cz);
      if (!this.isInsideFloor(wx, wz, 0.15)) return false;
      const cellY = this.getFloorY(cx, cz);
      for (let dz = -radius; dz <= radius; dz++) {
        for (let dx = -radius; dx <= radius; dx++) {
          if (dx * dx + dz * dz > radius * radius) continue;
          const xx = cx + dx, zz = cz + dz;
          if (xx < 0 || xx >= this.nx || zz < 0 || zz >= this.nz) return false;
          if (this.obs[xx + zz * this.nx]) return false;
          const [nwx, nwz] = this._xz(xx, zz);
          if (!this.isInsideFloor(nwx, nwz, 0.08)) return false;
          const ny = this.getFloorY(xx, zz);
          if (Math.abs(ny - cellY) > 0.12) return false;
        }
      }
      return true;
    };

    if (hasClearance(centerCell[0], centerCell[1], rCells)) {
      return this._xz(centerCell[0], centerCell[1]);
    }

    let bestCell = null;
    let bestClearanceDist = -1;

    for (let rad = 1; rad <= 35; rad++) {
      for (let dz = -rad; dz <= rad; dz++) {
        for (let dx = -rad; dx <= rad; dx++) {
          if (Math.abs(dx) !== rad && Math.abs(dz) !== rad) continue;
          const xx = centerCell[0] + dx, zz = centerCell[1] + dz;
          if (xx < 0 || xx >= this.nx || zz < 0 || zz >= this.nz) continue;
          if (this.obs[xx + zz * this.nx]) continue;

          if (hasClearance(xx, zz, rCells)) {
            return this._xz(xx, zz);
          }

          if (!bestCell) {
            let c = 0;
            while (c < rCells && hasClearance(xx, zz, c + 1)) c++;
            if (c > bestClearanceDist) {
              bestClearanceDist = c;
              bestCell = [xx, zz];
            }
          }
        }
      }
    }

    if (bestCell) {
      return this._xz(bestCell[0], bestCell[1]);
    }

    return this.getFreePosition(pt);
  }

  /**
   * Computes the bounding box and center of all walkable cells in the room.
   */
  getWalkableBounds() {
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    let count = 0;
    for (let iz = 0; iz < this.nz; iz++) {
      for (let ix = 0; ix < this.nx; ix++) {
        if (!this.obs[ix + iz * this.nx]) {
          const [x, z] = this._xz(ix, iz);
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (z < minZ) minZ = z;
          if (z > maxZ) maxZ = z;
          count++;
        }
      }
    }
    if (count === 0) {
      const min = [this.origin[0], this.origin[1]];
      const max = [this.origin[0] + this.nx * this.cell, this.origin[1] + this.nz * this.cell];
      return {
        min,
        max,
        center: [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2],
        spanX: max[0] - min[0],
        spanZ: max[1] - min[1]
      };
    }
    return {
      min: [Number(minX.toFixed(3)), Number(minZ.toFixed(3))],
      max: [Number(maxX.toFixed(3)), Number(maxZ.toFixed(3))],
      center: [Number(((minX + maxX) / 2).toFixed(3)), Number(((minZ + maxZ) / 2).toFixed(3))],
      spanX: Number((maxX - minX).toFixed(3)),
      spanZ: Number((maxZ - minZ).toFixed(3))
    };
  }

  /**
   * Sets strict room floor bounds and impenetrable perimeter boundary polygon.
   * Any cell outside the room bounding box is permanently stamped as an obstacle.
   */
  setFloorBounds(bounds = null, boundaryMarkers = null, margin = 0.20) {
    let minX, maxX, minZ, maxZ;
    if (bounds && bounds.min && bounds.max) {
      minX = Number(bounds.min[0]);
      maxX = Number(bounds.max[0]);
      minZ = Number(bounds.min[2] !== undefined ? bounds.min[2] : bounds.min[1]);
      maxZ = Number(bounds.max[2] !== undefined ? bounds.max[2] : bounds.max[1]);
    } else {
      const wb = this.getWalkableBounds();
      minX = wb.min[0];
      maxX = wb.max[0];
      minZ = wb.min[1];
      maxZ = wb.max[1];
    }

    if (minX > maxX) { const tmp = minX; minX = maxX; maxX = tmp; }
    if (minZ > maxZ) { const tmp = minZ; minZ = maxZ; maxZ = tmp; }

    let poly = null;
    let bm = boundaryMarkers;
    if (!bm) {
      try {
        const bmPath = path.resolve(process.cwd(), "output/boundary_markers.json");
        if (fs.existsSync(bmPath)) bm = JSON.parse(fs.readFileSync(bmPath, "utf8"));
      } catch (_) {}
    }

    if (bm && bm.NW && bm.NE && bm.SE && bm.SW) {
      const markersFit = [bm.NW, bm.NE, bm.SE, bm.SW].every(pt => {
        return pt[0] >= minX - 0.75 && pt[0] <= maxX + 0.75 &&
               pt[2] >= minZ - 0.75 && pt[2] <= maxZ + 0.75;
      });
      if (markersFit) {
        poly = [
          [bm.NW[0], bm.NW[2]],
          [bm.NE[0], bm.NE[2]],
          [bm.SE[0], bm.SE[2]],
          [bm.SW[0], bm.SW[2]]
        ];
      }
    }

    this.floorBounds = {
      minX: Number(minX.toFixed(3)),
      maxX: Number(maxX.toFixed(3)),
      minZ: Number(minZ.toFixed(3)),
      maxZ: Number(maxZ.toFixed(3)),
      innerMinX: Number((minX + margin).toFixed(3)),
      innerMaxX: Number((maxX - margin).toFixed(3)),
      innerMinZ: Number((minZ + margin).toFixed(3)),
      innerMaxZ: Number((maxZ - margin).toFixed(3)),
      poly
    };

    // Permanently mask any cell outside the floor bounding box as impenetrable obstacle
    for (let iz = 0; iz < this.nz; iz++) {
      for (let ix = 0; ix < this.nx; ix++) {
        const [wx, wz] = this._xz(ix, iz);
        if (!this.isInsideFloor(wx, wz, 0.05)) {
          this.obs[ix + iz * this.nx] = 1;
        }
      }
    }
  }

  /**
   * Tests whether world position (wx, wz) is strictly inside the floor bounding box / room polygon.
   */
  isInsideFloor(wx, wz, margin = 0.15) {
    if (!this.floorBounds) return true;
    const { minX, maxX, minZ, maxZ, poly } = this.floorBounds;
    if (wx < minX + margin || wx > maxX - margin || wz < minZ + margin || wz > maxZ - margin) {
      return false;
    }
    if (poly && poly.length >= 3) {
      let ins = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i][0], yi = poly[i][1];
        const xj = poly[j][0], yj = poly[j][1];
        const intersect = ((yi > wz) !== (yj > wz)) && (wx < (xj - xi) * (wz - yi) / (yj - yi) + xi);
        if (intersect) ins = !ins;
      }
      if (!ins) return false;
    }
    return true;
  }

  /**
   * Clamps world position (pt) strictly inside the floor bounding box with human standoff margin.
   */
  clampToFloor(pt, margin = 0.20) {
    if (!this.floorBounds) return [Number(pt[0]), Number(pt[1])];
    const { minX, maxX, minZ, maxZ, poly } = this.floorBounds;
    const effMargin = Math.min(margin, Math.min(maxX - minX, maxZ - minZ) * 0.2);
    const clampedX = Math.max(minX + effMargin, Math.min(maxX - effMargin, pt[0]));
    const clampedZ = Math.max(minZ + effMargin, Math.min(maxZ - effMargin, pt[1]));
    let res = [Number(clampedX.toFixed(3)), Number(clampedZ.toFixed(3))];

    if (poly && poly.length >= 3 && !this.isInsideFloor(res[0], res[1], 0.05)) {
      const cx = (minX + maxX) / 2;
      const cz = (minZ + maxZ) / 2;
      for (let step = 0.1; step <= 0.9; step += 0.1) {
        const testX = Number((res[0] * (1 - step) + cx * step).toFixed(3));
        const testZ = Number((res[1] * (1 - step) + cz * step).toFixed(3));
        if (this.isInsideFloor(testX, testZ, 0.05)) {
          res = [testX, testZ];
          break;
        }
      }
    }
    return res;
  }

  /**
   * Dynamically calculates safe positions for 8 directions:
   * - Pure cardinal walls: N, S, E, W
   * - Diagonal corners: NW, NE, SW, SE
   * - Center: Center
   * Stretches across the full room area, and snaps to valid walkable floor cells.
   */
  getSafeDirectionPosition(dirCode, margin = 0.25, distFraction = 1.0) {
    const code = String(dirCode || "Center").toUpperCase();
    let minX, maxX, minZ, maxZ, cx, cz;
    if (this.floorBounds) {
      minX = this.floorBounds.minX + margin;
      maxX = this.floorBounds.maxX - margin;
      minZ = this.floorBounds.minZ + margin;
      maxZ = this.floorBounds.maxZ - margin;
      cx = (minX + maxX) / 2;
      cz = (minZ + maxZ) / 2;
    } else {
      const bounds = this.getWalkableBounds();
      cx = bounds.center[0];
      cz = bounds.center[1];
      minX = bounds.min[0] + margin;
      maxX = bounds.max[0] - margin;
      minZ = bounds.min[1] + margin;
      maxZ = bounds.max[1] - margin;
    }

    let targetX = cx;
    let targetZ = cz;
    let inward = [0, 1];

    switch (code) {
      case "N":
      case "NORTH":
        targetX = cx;
        targetZ = minZ;
        inward = [0, 1];
        break;
      case "S":
      case "SOUTH":
        targetX = cx;
        targetZ = maxZ;
        inward = [0, -1];
        break;
      case "E":
      case "EAST":
        targetX = maxX;
        targetZ = cz;
        inward = [-1, 0];
        break;
      case "W":
      case "WEST":
        targetX = minX;
        targetZ = cz;
        inward = [1, 0];
        break;
      case "NW":
      case "NORTHWEST":
      case "NORTH_WEST":
        targetX = minX;
        targetZ = minZ;
        inward = [0.707, 0.707];
        break;
      case "NE":
      case "NORTHEAST":
      case "NORTH_EAST":
        targetX = maxX;
        targetZ = minZ;
        inward = [-0.707, 0.707];
        break;
      case "SW":
      case "SOUTHWEST":
      case "SOUTH_WEST":
        targetX = minX;
        targetZ = maxZ;
        inward = [0.707, -0.707];
        break;
      case "SE":
      case "SOUTHEAST":
      case "SOUTH_EAST":
        targetX = maxX;
        targetZ = maxZ;
        inward = [-0.707, -0.707];
        break;
      case "CENTER":
      case "MIDDLE":
      default:
        targetX = cx;
        targetZ = cz;
        inward = [0, -1];
        break;
    }

    if (distFraction < 1.0 && code !== "CENTER" && code !== "MIDDLE") {
      targetX = cx + (targetX - cx) * distFraction;
      targetZ = cz + (targetZ - cz) * distFraction;
    }

    targetX = Math.max(minX, Math.min(maxX, targetX));
    targetZ = Math.max(minZ, Math.min(maxZ, targetZ));

    const freePos = this.getFreePosition([targetX, targetZ]);
    const floorY = this.getFloorY(freePos[0], freePos[1]);

    return {
      pos: freePos,
      y: floorY,
      inward: inward
    };
  }

  _los(c1, c2, radiusCells = 1) {
    const dx = c2[0] - c1[0];
    const dz = c2[1] - c1[1];
    const steps = Math.max(Math.abs(dx), Math.abs(dz)) * 2 + 1;
    let prevX = c1[0], prevZ = c1[1];
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const x = Math.round(c1[0] + dx * t);
      const z = Math.round(c1[1] + dz * t);

      if (x < 0 || x >= this.nx || z < 0 || z >= this.nz) return false;
      if (this.obs[x + z * this.nx]) return false;

      // Radius-aware corridor clearance: ensure no obstacle within radiusCells around ray
      for (let rz = -radiusCells; rz <= radiusCells; rz++) {
        for (let rx = -radiusCells; rx <= radiusCells; rx++) {
          if (rx * rx + rz * rz > radiusCells * radiusCells) continue;
          const cx_chk = x + rx, cz_chk = z + rz;
          if (cx_chk >= 0 && cx_chk < this.nx && cz_chk >= 0 && cz_chk < this.nz) {
            if (this.obs[cx_chk + cz_chk * this.nx]) return false;
          }
        }
      }

      // Restrict line-of-sight corridor strictly inside room floor bounds
      const [wx, wz] = this._xz(x, z);
      if (!this.isInsideFloor(wx, wz, 0.12)) return false;

      // Prevent corner cutting diagonally across adjacent obstacles
      if (x !== prevX && z !== prevZ) {
        if (this.obs[prevX + z * this.nx] && this.obs[x + prevZ * this.nx]) {
          return false;
        }
      }

      const fromY = this.getFloorY(prevX, prevZ);
      const toY = this.getFloorY(x, z);
      if (Math.abs(toY - fromY) > 0.12) return false;

      prevX = x;
      prevZ = z;
    }
    return true;
  }

  /**
   * Plans an obstacle-free polyline from a to b in world coordinates.
   * Strictly restricted to the room floor bounding box.
   */
  path(a, b) {
    const clampedA = this.clampToFloor(a, 0.20);
    const clampedB = this.clampToFloor(b, 0.20);
    const pA = [Number(clampedA[0]), Number(clampedA[1])];
    const pB = [Number(clampedB[0]), Number(clampedB[1])];
    const dDirect = Math.hypot(pB[0] - pA[0], pB[1] - pA[1]);
    if (dDirect < 0.1) return [pA, pB];

    const s = this._free(this._ij(pA));
    const g = this._free(this._ij(pB));

    if (s[0] === g[0] && s[1] === g[1]) {
      return [pA, pB];
    }

    const startKey = s[0] + s[1] * this.nx;
    const goalKey = g[0] + g[1] * this.nx;

    const gScore = new Float32Array(this.nx * this.nz).fill(1e9);
    const cameFrom = new Int32Array(this.nx * this.nz).fill(-1);
    const closed = new Uint8Array(this.nx * this.nz);
    gScore[startKey] = 0;

    const openSet = new MinHeap();
    openSet.push({ key: startKey, f: Math.hypot(g[0] - s[0], g[1] - s[1]) });

    while (openSet.size > 0) {
      const curr = openSet.pop();
      if (!curr) break;
      if (curr.key === goalKey) break;
      if (closed[curr.key]) continue;
      closed[curr.key] = 1;

      const cx = curr.key % this.nx;
      const cz = Math.floor(curr.key / this.nx);
      const cg = gScore[curr.key];

      for (const [dx, dz, cost] of MOVES) {
        const xx = cx + dx, zz = cz + dz;
        if (xx < 0 || xx >= this.nx || zz < 0 || zz >= this.nz) continue;
        const nKey = xx + zz * this.nx;
        if (this.obs[nKey] || closed[nKey]) continue;

        // Discard any neighbor outside the room floor bounding box
        const [wx, wz] = this._xz(xx, zz);
        if (!this.isInsideFloor(wx, wz, 0.10)) continue;

        // Prevent corner cutting diagonally across adjacent obstacles
        if (dx !== 0 && dz !== 0) {
          if (this.obs[cx + dx + cz * this.nx] || this.obs[cx + (cz + dz) * this.nx]) {
            continue;
          }
        }

        const fromY = this.getFloorY(cx, cz);
        const toY = this.getFloorY(xx, zz);
        const deltaY = Math.abs(toY - fromY);

        // Strict step-height rejection: cannot step over heights > 12cm (furniture/curbs)
        if (deltaY > 0.12) continue;

        // Smooth elevation penalty:
        const elevationPenalty = deltaY * 40.0;
        const tentative = cg + cost + elevationPenalty;

        if (tentative < gScore[nKey]) {
          gScore[nKey] = tentative;
          cameFrom[nKey] = curr.key;
          const h = Math.hypot(g[0] - xx, g[1] - zz);
          openSet.push({ key: nKey, f: tentative + h });
        }
      }
    }

    if (cameFrom[goalKey] === -1 && startKey !== goalKey) {
      // If direct line cuts across an obstacle, route around via clear corridor
      let bestKey = -1;
      let bestDist = Infinity;
      for (let k = 0; k < this.nx * this.nz; k++) {
        if (closed[k]) {
          const kx = k % this.nx, kz = Math.floor(k / this.nx);
          const d = Math.hypot(g[0] - kx, g[1] - kz);
          if (d < bestDist) {
            bestDist = d;
            bestKey = k;
          }
        }
      }
      if (bestKey !== -1 && bestKey !== startKey) {
        const cells = [];
        let curr = bestKey;
        while (curr !== -1) {
          cells.push([curr % this.nx, Math.floor(curr / this.nx)]);
          if (curr === startKey) break;
          curr = cameFrom[curr];
        }
        cells.reverse();
        const waypoints = [pA];
        for (let k = 1; k < cells.length; k++) {
          waypoints.push(this._xz(cells[k][0], cells[k][1]));
        }
        return waypoints.map(wp => this.clampToFloor(wp, 0.18));
      }
      const safePos = this.getFreePosition(pA);
      return [pA, safePos];
    }

    // Trace cell path back from goal
    const cells = [];
    let curr = goalKey;
    while (curr !== -1) {
      cells.push([curr % this.nx, Math.floor(curr / this.nx)]);
      if (curr === startKey) break;
      curr = cameFrom[curr];
    }
    cells.reverse();

    if (cells.length <= 2) return [pA, pB];

    // Radius-aware Line-of-Sight (LOS) smoothing (maintains clearance corridor around obstacles)
    const keep = [cells[0]];
    let i = 0;
    while (i < cells.length - 1) {
      let j = cells.length - 1;
      while (j > i + 1 && !this._los(cells[i], cells[j], 1)) {
        j--;
      }
      keep.push(cells[j]);
      i = j;
    }

    const waypoints = [pA];
    for (let k = 1; k < keep.length - 1; k++) {
      waypoints.push(this._xz(keep[k][0], keep[k][1]));
    }
    waypoints.push(pB);

    return waypoints.map(wp => this.clampToFloor(wp, 0.18));
  }

  /**
   * Factory: rasterizes 3D point cloud into 2D obstacle navigation grid
   */
  static fromPointCloud(pts, cell = 0.1, y_lo = 0.25, y_hi = 1.70, min_pts = 4) {
    const n = Math.floor(pts.length / 3);
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (let i = 0; i < n; i++) {
      const x = pts[i * 3], z = pts[i * 3 + 2];
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
    }

    const loX = minX - 0.2;
    const loZ = minZ - 0.2;
    const nx = Math.ceil((maxX + 0.2 - loX) / cell);
    const nz = Math.ceil((maxZ + 0.2 - loZ) / cell);

    const counts = new Uint16Array(nx * nz);
    for (let i = 0; i < n; i++) {
      const x = pts[i * 3], y = pts[i * 3 + 1], z = pts[i * 3 + 2];
      if (y > y_lo && y < y_hi) {
        const ix = Math.floor((x - loX) / cell);
        const iz = Math.floor((z - loZ) / cell);
        if (ix >= 0 && ix < nx && iz >= 0 && iz < nz) {
          counts[ix + iz * nx]++;
        }
      }
    }

    const obs = new Uint8Array(nx * nz);
    for (let i = 0; i < nx * nz; i++) {
      if (counts[i] >= min_pts) obs[i] = 1;
    }

    // 1-cell dilation (0.1m human clearance)
    const dilated = new Uint8Array(nx * nz);
    for (let z = 0; z < nz; z++) {
      for (let x = 0; x < nx; x++) {
        if (obs[x + z * nx]) {
          dilated[x + z * nx] = 1;
          for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            const xx = x + dx, zz = z + dz;
            if (xx >= 0 && xx < nx && zz >= 0 && zz < nz) {
              dilated[xx + zz * nx] = 1;
            }
          }
        }
      }
    }

    return new NavGrid(dilated, [loX, loZ], cell, nx, nz);
  }

  /**
   * Load active scene navigation grid from Dummy_3D cloud or mesh data
   */
  static loadActiveSceneGrid(customPath = null) {
    const jsonPaths = [
      customPath,
      path.resolve(process.cwd(), "output/navgrid.json"),
      path.resolve(process.cwd(), "output/openmvs/navgrid.json"),
    ].filter(Boolean);

    for (const jp of jsonPaths) {
      if (fs.existsSync(jp) && jp.endsWith(".json")) {
        try {
          const data = JSON.parse(fs.readFileSync(jp, "utf8"));
          if (data.origin && data.nx && data.nz && data.obs_b64) {
            const buf = Buffer.from(data.obs_b64, "base64");
            const obs = new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength);
            const heights = data.heights ? new Float32Array(data.heights) : null;
            console.log(`[NavGrid] Loaded centered room obstacle grid (${data.nx}x${data.nz}) with elevations from ${jp}`);
            return new NavGrid(obs, data.origin, data.cell || 0.1, data.nx, data.nz, heights);
          }
        } catch (e) {
          console.warn("[NavGrid] Error reading navgrid.json:", e.message);
        }
      }
    }

    // [LEGACY / UNVISITED - Shifted from OpenMVS cloud.bin to neural navgrid.json]
    /*
    const searchDirs = [
      customPath,
      path.resolve(process.cwd(), "output/openmvs"),
      "/Users/mohammadmojijansari/Documents/Dummy_3D/out",
      path.resolve(process.cwd(), "../Dummy_3D/out")
    ].filter(Boolean);

    for (const d of searchDirs) {
      const cloudBin = path.join(d, "cloud.bin");
      if (fs.existsSync(cloudBin)) {
        try {
          const buf = fs.readFileSync(cloudBin);
          const n = Math.floor(buf.length / 12);
          const pts = new Float32Array(buf.buffer, buf.byteOffset, n * 3);
          const grid = NavGrid.fromPointCloud(pts);
          console.log(`[NavGrid] Initialized obstacle grid (${grid.nx}x${grid.nz}) from ${cloudBin}`);
          return grid;
        } catch (e) {
          console.warn("[NavGrid] Error reading cloud.bin:", e.message);
        }
      }
    }
    */

    return null;
  }

  /**
   * Factory: create synthetic grid stamped with room boundary walls & furniture footprints
   */
  static fromBoundsAndAnchors(bounds, anchors = {}, boundaryMarkers = null) {
    const min = bounds?.min || [-5, 0, -5];
    const max = bounds?.max || [5, 3.8, 5];
    const minZ = min[2] !== undefined ? min[2] : min[1];
    const maxZ = max[2] !== undefined ? max[2] : max[1];
    const cell = 0.1;

    const loX = min[0] - 0.4;
    const loZ = minZ - 0.4;
    const nx = Math.max(10, Math.ceil((max[0] + 0.4 - loX) / cell));
    const nz = Math.max(10, Math.ceil((maxZ + 0.4 - loZ) / cell));

    const obs = new Uint8Array(nx * nz);

    function stampBox(cx, cz, halfW, halfH) {
      const minX = Math.floor((cx - halfW - loX) / cell);
      const maxX = Math.ceil((cx + halfW - loX) / cell);
      const minZ = Math.floor((cz - halfH - loZ) / cell);
      const maxZ = Math.ceil((cz + halfH - loZ) / cell);

      for (let z = Math.max(0, minZ); z <= Math.min(nz - 1, maxZ); z++) {
        for (let x = Math.max(0, minX); x <= Math.min(nx - 1, maxX); x++) {
          obs[x + z * nx] = 1;
        }
      }
    }

    // 1. Stamp room outer perimeter walls
    for (let x = 0; x < nx; x++) {
      obs[x + 0 * nx] = 1;
      obs[x + (nz - 1) * nx] = 1;
    }
    for (let z = 0; z < nz; z++) {
      obs[0 + z * nx] = 1;
      obs[(nx - 1) + z * nx] = 1;
    }

    // 2. Stamp furniture footprints from anchors
    for (const [name, anc] of Object.entries(anchors)) {
      if (!anc || !anc.pos) continue;
      const type = anc.type;
      const [px, pz] = anc.pos;

      if (type === "desk") {
        stampBox(px, pz, 0.8, 0.5);
      } else if (type === "table") {
        stampBox(px, pz, 1.0, 0.7);
      } else if (type === "couch" || type === "sofa") {
        stampBox(px, pz, 1.1, 0.55);
      } else if (type === "bed") {
        stampBox(px, pz, 1.2, 0.95);
      } else if (type === "chair") {
        stampBox(px, pz, 0.38, 0.38);
      }
    }

    // Only stamp central living room table if it is an actual physical object in anchors
    for (const [name, anc] of Object.entries(anchors)) {
      if (!anc || !anc.pos) continue;
      const type = anc.type;
      const [px, pz] = anc.pos;
      if (type === "table") {
        stampBox(px, pz, (anc.size?.[0] ? anc.size[0] / 2 : 0.8), (anc.size?.[1] ? anc.size[1] / 2 : 0.55));
      }
    }

    // 3. Clear openings around doors and exits
    for (const anc of Object.values(anchors)) {
      if (anc.type === "door" || anc.type === "exit" || anc.type === "window") {
        const ix = Math.floor((anc.pos[0] - loX) / cell);
        const iz = Math.floor((anc.pos[1] - loZ) / cell);
        for (let dz = -3; dz <= 3; dz++) {
          for (let dx = -3; dx <= 3; dx++) {
            const xx = ix + dx, zz = iz + dz;
            if (xx >= 0 && xx < nx && zz >= 0 && zz < nz) {
              obs[xx + zz * nx] = 0;
            }
          }
        }
      }
    }

    const grid = new NavGrid(obs, [loX, loZ], cell, nx, nz);
    grid.setFloorBounds(bounds, boundaryMarkers, 0.20);
    return grid;
  }

  stampBox(cx, cz, halfW, halfH) {
    const minX = Math.floor((cx - halfW - this.origin[0]) / this.cell);
    const maxX = Math.ceil((cx + halfW - this.origin[0]) / this.cell);
    const minZ = Math.floor((cz - halfH - this.origin[1]) / this.cell);
    const maxZ = Math.ceil((cz + halfH - this.origin[1]) / this.cell);

    for (let z = Math.max(0, minZ); z <= Math.min(this.nz - 1, maxZ); z++) {
      for (let x = Math.max(0, minX); x <= Math.min(this.nx - 1, maxX); x++) {
        this.obs[x + z * this.nx] = 1;
      }
    }
  }

  clearBox(cx, cz, halfW, halfH) {
    const minX = Math.floor((cx - halfW - this.origin[0]) / this.cell);
    const maxX = Math.ceil((cx + halfW - this.origin[0]) / this.cell);
    const minZ = Math.floor((cz - halfH - this.origin[1]) / this.cell);
    const maxZ = Math.ceil((cz + halfH - this.origin[1]) / this.cell);

    for (let z = Math.max(0, minZ); z <= Math.min(this.nz - 1, maxZ); z++) {
      for (let x = Math.max(0, minX); x <= Math.min(this.nx - 1, maxX); x++) {
        this.obs[x + z * this.nx] = 0;
      }
    }
  }

  maskRoomBoundary(boundaryMarkers = null) {
    let bm = boundaryMarkers;
    if (!bm) {
      try {
        const bmPath = path.resolve(process.cwd(), "output/boundary_markers.json");
        if (fs.existsSync(bmPath)) bm = JSON.parse(fs.readFileSync(bmPath, "utf8"));
      } catch (_) {}
    }
    if (!bm || !bm.NW || !bm.NE || !bm.SE || !bm.SW) return;

    const poly = [
      [bm.NW[0], bm.NW[2]],
      [bm.NE[0], bm.NE[2]],
      [bm.SE[0], bm.SE[2]],
      [bm.SW[0], bm.SW[2]]
    ];

    const isInside = (pt) => {
      const x = pt[0], y = pt[1];
      let ins = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i][0], yi = poly[i][1];
        const xj = poly[j][0], yj = poly[j][1];
        const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) ins = !ins;
      }
      return ins;
    };

    for (let iz = 0; iz < this.nz; iz++) {
      for (let ix = 0; ix < this.nx; ix++) {
        const pt = this._xz(ix, iz);
        if (!isInside(pt)) {
          this.obs[ix + iz * this.nx] = 1;
        }
      }
    }
  }

  stampPhysicalObjects(physicalObjects = [], anchors = {}) {
    const allObjects = Array.isArray(physicalObjects) ? [...physicalObjects] : [];
    if (anchors && typeof anchors === "object") {
      for (const [id, anc] of Object.entries(anchors)) {
        if (!anc || !anc.pos) continue;
        const type = (anc.type || "").toLowerCase();
        // Skip query aliases and hypothetical fallbacks
        if (id.startsWith("couch_") || id.startsWith("bed_") || id.startsWith("victim_")) continue;
        if (!allObjects.some(o => o.id === id || (o.pos && Math.hypot(o.pos[0] - anc.pos[0], o.pos[1] - anc.pos[1]) < 0.25))) {
          allObjects.push({ id, ...anc });
        }
      }
    }

    // Identify doors to avoid placing obstacle chairs in front of doorways
    const doors = allObjects.filter(o => {
      const t = (o.type || "").toLowerCase();
      const i = (o.id || "").toLowerCase();
      return t === "door" || t === "entrance" || i.includes("door") || i.includes("entrance");
    });

    for (const obj of allObjects) {
      if (!obj || !obj.pos) continue;
      const type = (obj.type || "").toLowerCase();
      const id = (obj.id || "").toLowerCase();
      // Skip doors, portals, exits, windows, or center markers
      if (type === "door" || type === "entrance" || type === "exit" || type === "window" || type === "center") continue;
      if (id.includes("door") || id.includes("entrance") || id.includes("exit") || id.includes("window")) continue;

      // If synthetic directional chair and not an active occupied target, do NOT stamp as solid obstacle
      if (type === "chair" && id.startsWith("chair_") && id !== "chair_center") {
        const isOccupied = obj.occupied || (anchors && anchors[obj.id]?.occupied);
        if (!isOccupied) continue;
      }

      // If chair is close to a doorway, do not block the door corridor
      if (type === "chair" && doors.some(d => Math.hypot(d.pos[0] - obj.pos[0], d.pos[1] - obj.pos[1]) < 0.75)) {
        continue;
      }

      const [px, pz] = obj.pos;
      let halfW = 0.45, halfH = 0.45;

      if (type === "desk") {
        halfW = Math.max(0.75, (obj.size?.[0] ? obj.size[0] / 2 : 0.65) + 0.12);
        halfH = Math.max(0.55, (obj.size?.[1] ? obj.size[1] / 2 : 0.45) + 0.12);
      } else if (type === "table") {
        halfW = Math.max(0.70, (obj.size?.[0] ? obj.size[0] / 2 : 0.60) + 0.12);
        halfH = Math.max(0.50, (obj.size?.[1] ? obj.size[1] / 2 : 0.45) + 0.12);
      } else if (type === "couch" || type === "sofa") {
        halfW = Math.max(1.05, (obj.size?.[0] ? obj.size[0] / 2 : 0.90) + 0.15);
        halfH = Math.max(0.65, (obj.size?.[1] ? obj.size[1] / 2 : 0.50) + 0.15);
      } else if (type === "bed") {
        halfW = Math.max(1.15, (obj.size?.[0] ? obj.size[0] / 2 : 0.95) + 0.15);
        halfH = Math.max(0.95, (obj.size?.[1] ? obj.size[1] / 2 : 0.75) + 0.15);
      } else if (type === "chair") {
        halfW = 0.32;
        halfH = 0.32;
      } else {
        halfW = Math.max(0.45, (obj.size?.[0] ? obj.size[0] / 2 : 0.35) + 0.12);
        halfH = Math.max(0.45, (obj.size?.[1] ? obj.size[1] / 2 : 0.35) + 0.12);
      }

      this.stampBox(px, pz, halfW, halfH);
    }

    // Ensure doorway threshold is passable without wiping interior room obstacles
    for (const obj of allObjects) {
      if (!obj || !obj.pos) continue;
      const type = (obj.type || "").toLowerCase();
      const id = (obj.id || "").toLowerCase();
      if (type === "door" || type === "entrance" || type === "exit" || type === "window" || id.includes("door") || id.includes("entrance")) {
        const [px, pz] = obj.pos;
        const inw = obj.inward || [0, 0];
        this.clearBox(px, pz, 0.25, 0.25);
        for (let s = 0.1; s <= 0.25; s += 0.1) {
          this.clearBox(px + inw[0] * s, pz + inw[1] * s, 0.20, 0.20);
        }
      }
    }
  }

  /**
   * Factory: create scene navigation grid.
   * Checks compatibility of cached NavGrid against active model bounds.
   * If model bounds mismatch, constructs fresh NavGrid sized directly to active model bounds.
   * Stamped with furniture and permanently restricted to the room floor bounding box.
   */
  static createSceneGrid(bounds, anchors = {}, physicalObjects = [], boundaryMarkers = null) {
    let active = null;
    let useActive = false;

    // 1. Check if cached active NavGrid matches active model bounds
    try {
      active = NavGrid.loadActiveSceneGrid();
      if (active && active.obs && active.obs.length > 0) {
        if (!bounds) {
          useActive = true;
        } else {
          let bm = boundaryMarkers;
          if (!bm) {
            try {
              const bmPath = path.resolve(process.cwd(), "output/boundary_markers.json");
              if (fs.existsSync(bmPath)) bm = JSON.parse(fs.readFileSync(bmPath, "utf8"));
            } catch (_) {}
          }

          let bMinX = bounds.min?.[0] ?? -5;
          let bMaxX = bounds.max?.[0] ?? 5;
          let bMinZ = bounds.min?.[2] !== undefined ? bounds.min[2] : (bounds.min?.[1] ?? -5);
          let bMaxZ = bounds.max?.[2] !== undefined ? bounds.max[2] : (bounds.max?.[1] ?? 5);

          if (bm && bm.NW && bm.SE && bm.NE && bm.SW) {
            const pts = [bm.NW, bm.NE, bm.SE, bm.SW];
            bMinX = Math.min(...pts.map(p => p[0]));
            bMaxX = Math.max(...pts.map(p => p[0]));
            bMinZ = Math.min(...pts.map(p => p[2]));
            bMaxZ = Math.max(...pts.map(p => p[2]));
          }

          const bCenterX = (bMinX + bMaxX) / 2;
          const bCenterZ = (bMinZ + bMaxZ) / 2;

          const gridMinX = active.origin[0];
          const gridMaxX = active.origin[0] + active.nx * active.cell;
          const gridMinZ = active.origin[1];
          const gridMaxZ = active.origin[1] + active.nz * active.cell;
          const gridCenterX = (gridMinX + gridMaxX) / 2;
          const gridCenterZ = (gridMinZ + gridMaxZ) / 2;

          const centerDiff = Math.hypot(gridCenterX - bCenterX, gridCenterZ - bCenterZ);
          // Check spatial overlap between cached active grid and room bounds
          const overlaps = (gridMinX < bMaxX && gridMaxX > bMinX && gridMinZ < bMaxZ && gridMaxZ > bMinZ);
          const reasonableCenter = centerDiff < 2.2;

          if (reasonableCenter && overlaps) {
            useActive = true;
          } else {
            console.log(`[NavGrid] Cached active grid (${gridMinX.toFixed(2)}..${gridMaxX.toFixed(2)}, ${gridMinZ.toFixed(2)}..${gridMaxZ.toFixed(2)}) is incompatible with active model bounds (${bMinX.toFixed(2)}..${bMaxX.toFixed(2)}, ${bMinZ.toFixed(2)}..${bMaxZ.toFixed(2)}). Building fresh grid sized to active model bounds.`);
          }
        }
      }
    } catch (e) {
      console.warn("[NavGrid] Notice checking active scene grid:", e.message);
    }

    const grid = useActive ? active : NavGrid.fromBoundsAndAnchors(bounds, anchors, boundaryMarkers);
    if (grid) {
      grid.setFloorBounds(bounds, boundaryMarkers, 0.20);
      grid.maskRoomBoundary(boundaryMarkers);
      grid.stampPhysicalObjects(physicalObjects, anchors);
    }
    return grid;
  }
}


