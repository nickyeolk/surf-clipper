// Image <-> pool homography from four role-ordered corners (mirrors src/surfclip/zone/geometry.py).
export type Pt = [number, number]

export interface Corners {
  back_a: Pt
  back_b: Pt
  front_a: Pt
  front_b: Pt
}

function solve(a: number[][], b: number[]): number[] {
  const n = b.length
  const m = a.map((row, i) => [...row, b[i]])
  for (let c = 0; c < n; c++) {
    let p = c
    for (let r = c + 1; r < n; r++) if (Math.abs(m[r][c]) > Math.abs(m[p][c])) p = r
    ;[m[c], m[p]] = [m[p], m[c]]
    if (Math.abs(m[c][c]) < 1e-12) throw new Error('degenerate corners')
    for (let r = 0; r < n; r++) {
      if (r === c) continue
      const f = m[r][c] / m[c][c]
      for (let k = c; k <= n; k++) m[r][k] -= f * m[c][k]
    }
  }
  return m.map((row, i) => row[n] / row[i])
}

/** 3x3 matrix mapping pool (u, v) in [0,1]^2 to image points. */
export function poolToImage(c: Corners): number[] {
  const src: Pt[] = [[0, 0], [1, 0], [1, 1], [0, 1]]
  const dst: Pt[] = [c.back_a, c.back_b, c.front_b, c.front_a]
  const a: number[][] = []
  const b: number[] = []
  src.forEach(([x, y], i) => {
    const [u, v] = dst[i]
    a.push([x, y, 1, 0, 0, 0, -u * x, -u * y])
    b.push(u)
    a.push([0, 0, 0, x, y, 1, -v * x, -v * y])
    b.push(v)
  })
  return [...solve(a, b), 1]
}

/** Image point for a pool point, or null if it lies beyond the zone's horizon. */
export function apply(h: number[], [x, y]: Pt): Pt | null {
  const w = h[6] * x + h[7] * y + h[8]
  if (w <= 1e-9) return null
  return [(h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w]
}

/** True when the four corners form a simple (non-crossing) quadrilateral. */
export function isSimple(c: Corners): boolean {
  const q = [c.back_a, c.back_b, c.front_b, c.front_a]
  const cross = (o: Pt, p: Pt, r: Pt) => (p[0] - o[0]) * (r[1] - o[1]) - (p[1] - o[1]) * (r[0] - o[0])
  const segs = (p1: Pt, p2: Pt, q1: Pt, q2: Pt) =>
    cross(q1, q2, p1) * cross(q1, q2, p2) < 0 && cross(p1, p2, q1) * cross(p1, p2, q2) < 0
  return !segs(q[0], q[1], q[2], q[3]) && !segs(q[1], q[2], q[3], q[0])
}
