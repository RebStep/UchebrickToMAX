type Point = {
  x: number;
  y: number;
};
type Rect = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};
export const didDrag = (start: Point, end: Point, moved = false) => moved || Math.hypot(end.x - start.x, end.y - start.y) >= 6;
export function pickDropTask(pointer: Point, dragged: Rect | null, tasks: (Rect & {
  id: number;
})[]) {
  const underPointer = tasks.find((r) => pointer.x >= r.left && pointer.x <= r.right && pointer.y >= r.top && pointer.y <= r.bottom);
  if (underPointer) {
    return underPointer.id;
  }
  if (!dragged) {
    return null;
  }
  let best: number | null = null;
  let score = 0;
  for (const r of tasks) {
    const area = Math.max(0, Math.min(dragged.right, r.right) - Math.max(dragged.left, r.left))
      * Math.max(0, Math.min(dragged.bottom, r.bottom) - Math.max(dragged.top, r.top));
    const ratio = area / Math.max(1, Math.min((dragged.right - dragged.left) * (dragged.bottom - dragged.top), (r.right - r.left) * (r.bottom - r.top)));
    if (ratio >= 0.2 && ratio > score) {
      score = ratio;
      best = r.id;
    }
  }
  return best;
}
