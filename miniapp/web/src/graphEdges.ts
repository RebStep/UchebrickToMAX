type Point = {
  x: number;
  y: number;
};
type Rect = Point & {
  w: number;
  h: number;
  radius?: number;
  cornerPower?: number;
};
function anchor(rect: Rect, target: Point, fallback: number) {
  const hw = rect.w / 2;
  const hh = rect.h / 2;
  const cx = rect.x + hw;
  const cy = rect.y + hh;
  let dx = target.x - cx;
  let dy = target.y - cy;
  if (!dx && !dy) {
    dx = fallback;
  }
  const length = 1 / Math.max(Math.abs(dx) / hw, Math.abs(dy) / hh);
  const bx = dx * length;
  const by = dy * length;
  const r = Math.max(0, Math.min(rect.radius ?? 24, hw, hh));
  let t = 1;
  if (r && Math.abs(bx) > hw - r && Math.abs(by) > hh - r) {
    const power = rect.cornerPower ?? 2;
    let lo = 0;
    let hi = 1;
    for (let i = 0; i < 40; i++) {
      const mid = (lo + hi) / 2;
      const x = Math.max(0, Math.abs(bx * mid) - hw + r) / r;
      const y = Math.max(0, Math.abs(by * mid) - hh + r) / r;
      if (x ** power + y ** power > 1) {
        hi = mid;
      }
      else {
        lo = mid;
      }
    }
    t = (lo + hi) / 2;
  }
  return { x: cx + bx * t, y: cy + by * t };
}
export function graphConnection(from: Rect, to: Rect, scale = 1) {
  const source = { x: from.x + from.w / 2, y: from.y + from.h / 2 };
  const target = { x: to.x + to.w / 2, y: to.y + to.h / 2 };
  const a = anchor(from, target, 1);
  const b = anchor(to, source, -1);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const distance = Math.hypot(dx, dy);
  const sag = Math.max(10 * scale, Math.min(80 * scale, distance * 0.2));
  return {
    x1: a.x, y1: a.y, x2: b.x, y2: b.y,
    d: `M${a.x},${a.y} C${a.x + dx / 3},${a.y + dy / 3 + sag} ${b.x - dx / 3},${b.y - dy / 3 + sag} ${b.x},${b.y}`,
  };
}
