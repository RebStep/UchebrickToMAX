import type { FileItem, FileType, Task } from './types';
type Point = {
  x: number;
  y: number;
};
type Size = {
  w: number;
  h: number;
};
export type GraphObstacle = Point & Size & {
  key: string;
};
export const fileCardSize = (type: FileType): Size => {
  if (type === 'photo') {
    return { w: 154, h: 150 };
  }
  if (type === 'note') {
    return { w: 190, h: 126 };
  }
  return { w: 170, h: type === 'link' ? 33 : 64 };
};
export function graphObstacles(tasks: Task[], loose: FileItem[], sizes: Record<string, Size> = {}): GraphObstacle[] {
  const out: GraphObstacle[] = [];
  const seen = new Set<number>();
  const active = tasks.filter((t) => t.status !== 'done');
  for (const [i, t] of active.entries()) {
    const x = t.x ?? 40 + i % 2 * 290;
    const y = t.y ?? 140 + Math.floor(i / 2) * 220;
    out.push({ key: `t${t.id}`, x, y, ...(sizes[`t${t.id}`] ?? { w: 252, h: 240 }) });
    for (const [j, f] of t.files.entries()) {
      if (seen.has(f.id)) {
        continue;
      }
      seen.add(f.id);
      out.push({ key: `f${f.id}`, x: f.x ?? x + 290, y: f.y ?? y + j * 80, ...(sizes[`f${f.id}`] ?? fileCardSize(f.type)) });
    }
  }
  for (const f of loose) {
    if (!seen.has(f.id)) {
      out.push({ key: `f${f.id}`, x: f.x ?? 620, y: f.y ?? 140, ...(sizes[`f${f.id}`] ?? fileCardSize(f.type)) });
      seen.add(f.id);
    }
  }
  return out;
}
export function findGraphSpot(size: Size, obstacles: GraphObstacle[], preferred: Point, owner?: GraphObstacle): Point {
  const gap = 24;
  const candidates: Point[] = owner ? [] : [{ ...preferred }];
  if (owner) {
    for (let ring = 1; ring <= 6; ring++) {
      for (let i = 0; i < 24; i++) {
        const angle = i * Math.PI / 12;
        const dx = Math.cos(angle);
        const dy = Math.sin(angle);
        const distance = Math.min(((owner.w + size.w) / 2 + gap * ring) / Math.max(1e-9, Math.abs(dx)), ((owner.h + size.h) / 2 + gap * ring) / Math.max(1e-9, Math.abs(dy)));
        candidates.push({ x: owner.x + owner.w / 2 + dx * distance - size.w / 2, y: owner.y + owner.h / 2 + dy * distance - size.h / 2 });
      }
    }
  }
  for (const r of obstacles) {
    const xs = [r.x - size.w - gap, r.x + r.w + gap];
    const ys = [r.y - size.h - gap, r.y + r.h + gap];
    for (const x of xs) {
      candidates.push({ x, y: preferred.y });
      for (const y of ys) {
        candidates.push({ x, y });
      }
    }
    for (const y of ys) {
      candidates.push({ x: preferred.x, y });
    }
  }
  const score = (p: Point) => {
    const distance = (p.x - preferred.x) ** 2 + (p.y - preferred.y) ** 2;
    if (!owner) {
      return distance;
    }
    const dx = Math.max(owner.x - p.x - size.w, p.x - owner.x - owner.w, 0);
    const dy = Math.max(owner.y - p.y - size.h, p.y - owner.y - owner.h, 0);
    return (dx ** 2 + dy ** 2) * 10000 + distance;
  };
  const clear = (p: Point) => {
    return obstacles.every((r) => {
      return p.x + size.w + 20 <= r.x || r.x + r.w + 20 <= p.x || p.y + size.h + 20 <= r.y || r.y + r.h + 20 <= p.y;
    });
  };
  candidates.sort((a, b) => score(a) - score(b));
  const p = candidates.find(clear) ?? { x: Math.max(preferred.x, ...obstacles.map((r) => r.x + r.w)) + gap, y: preferred.y };
  return { x: Math.round(p.x), y: Math.round(p.y) };
}
