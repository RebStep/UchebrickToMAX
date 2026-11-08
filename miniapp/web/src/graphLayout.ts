type Size = {
  w: number;
  h: number;
};
type Rect = Size & {
  x: number;
  y: number;
};
type LayoutTask = {
  key: string;
  group: string;
  due: number;
  files: string[];
};
type Block = {
  group: string;
  w: number;
  h: number;
  items: Map<string, Rect>;
};
const overlaps = (a: Rect, b: Rect, gap: number) => {
  return a.x < b.x + b.w + gap && a.x + a.w + gap > b.x && a.y < b.y + b.h + gap && a.y + a.h + gap > b.y;
};
function blocksRadius(x: number, y: number, rect: Rect) {
  let lo = 0;
  let hi = 1;
  for (const [end, min, max] of [[x, rect.x - 10, rect.x + rect.w + 10], [y, rect.y - 10, rect.y + rect.h + 10]]) {
    if (Math.abs(end) < 1e-9) {
      if (min > 0 || max < 0) {
        return false;
      }
    }
    else {
      lo = Math.max(lo, Math.min(min / end, max / end));
      hi = Math.min(hi, Math.max(min / end, max / end));
      if (lo > hi) {
        return false;
      }
    }
  }
  return true;
}
export function arrangeGraph(options: {
  tasks: LayoutTask[];
  loose: string[];
  sizes: Record<string, Size>;
  left: number;
  top: number;
  maxWidth: number;
  obstacles: Rect[];
}) {
  const { sizes, left, top, maxWidth, obstacles } = options;
  const size = (key: string) => sizes[key] ?? (key.startsWith('t') ? { w: 252, h: 160 } : { w: 190, h: 64 });
  const groups = [...new Set(options.tasks.map((t) => t.group))];
  const tasks = [...options.tasks].sort((a, b) => groups.indexOf(a.group) - groups.indexOf(b.group) || a.due - b.due);
  const owners = new Map<string, LayoutTask[]>();
  for (const task of tasks) {
    for (const file of task.files) {
      if (!owners.has(file)) {
        owners.set(file, []);
      }
      owners.get(file)!.push(task);
    }
  }
  const visited = new Set<string>();
  const usedFiles = new Set<string>();
  const blocks: Block[] = [];
  for (const first of tasks) {
    if (visited.has(first.key)) {
      continue;
    }
    const parents: LayoutTask[] = [];
    const files = new Set<string>();
    const queue = [first];
    while (queue.length) {
      const task = queue.pop()!;
      if (visited.has(task.key)) {
        continue;
      }
      visited.add(task.key);
      parents.push(task);
      for (const file of task.files) {
        files.add(file);
        for (const owner of owners.get(file) ?? []) {
          if (!visited.has(owner.key)) {
            queue.push(owner);
          }
        }
      }
    }
    parents.sort((a, b) => tasks.indexOf(a) - tasks.indexOf(b));
    const parentKeys = parents.map((t) => t.key);
    const fileKeys = [...files];
    fileKeys.forEach((key) => usedFiles.add(key));
    const height = (keys: string[], gap: number) => keys.reduce((h, key) => h + size(key).h, 0) + Math.max(0, keys.length - 1) * gap;
    const parentHeight = height(parentKeys, 28);
    const parentWidth = Math.max(...parentKeys.map((key) => size(key).w));
    const fileWidth = Math.max(0, ...fileKeys.map((key) => size(key).w));
    const fileHeight = Math.max(0, ...fileKeys.map((key) => size(key).h));
    const items = new Map<string, Rect>();
    let parentY = -parentHeight / 2;
    for (const key of parentKeys) {
      items.set(key, { x: -size(key).w / 2, y: parentY, ...size(key) });
      parentY += size(key).h + 28;
    }
    const core = { x: -parentWidth / 2, y: -parentHeight / 2, w: parentWidth, h: parentHeight };
    const rx = (parentWidth + fileWidth) / 2 + 32;
    const ry = (parentHeight + fileHeight) / 2 + 32;
    let spread = 1;
    while (fileKeys.length) {
      const ring = fileKeys.map((key, i) => {
        const angle = (fileKeys.length <= 2 ? 0 : -Math.PI / 2) + i * 2 * Math.PI / fileKeys.length;
        const sz = size(key);
        return { key, x: Math.cos(angle) * rx * spread - sz.w / 2, y: Math.sin(angle) * ry * spread - sz.h / 2, ...sz };
      });
      const crowded = ring.some((r, i) => {
        return overlaps(core, r, 24) || ring.some((other, j) => i !== j && (overlaps(r, other, 28) || blocksRadius(r.x + r.w / 2, r.y + r.h / 2, other)));
      });
      if (!crowded) {
        for (let pass = 0; pass < 2; pass++) {
          for (const r of ring) {
            const cx = r.x + r.w / 2;
            const cy = r.y + r.h / 2;
            let lo = 0;
            let hi = 1;
            for (let step = 0; step < 20; step++) {
              const factor = (lo + hi) / 2;
              r.x = cx * factor - r.w / 2;
              r.y = cy * factor - r.h / 2;
              const blocked = overlaps(core, r, 24) || ring.some((other) => {
                return r !== other && (overlaps(r, other, 28) || blocksRadius(r.x + r.w / 2, r.y + r.h / 2, other)
                  || blocksRadius(other.x + other.w / 2, other.y + other.h / 2, r));
              });
              if (blocked) {
                lo = factor;
              }
              else {
                hi = factor;
              }
            }
            r.x = cx * hi - r.w / 2;
            r.y = cy * hi - r.h / 2;
          }
        }
        for (const { key, ...rect } of ring) {
          items.set(key, rect);
        }
        break;
      }
      spread *= 1.1;
    }
    const rects = [...items.values()];
    const x0 = Math.min(...rects.map((r) => r.x));
    const y0 = Math.min(...rects.map((r) => r.y));
    const w = Math.max(...rects.map((r) => r.x + r.w)) - x0;
    const h = Math.max(...rects.map((r) => r.y + r.h)) - y0;
    for (const r of items.values()) {
      r.x -= x0;
      r.y -= y0;
    }
    blocks.push({ group: first.group, w, h, items });
  }
  const standalone = [...new Set(options.loose)].filter((key) => !usedFiles.has(key));
  if (standalone.length) {
    const items = new Map<string, Rect>();
    let y = 0;
    for (const key of standalone) {
      items.set(key, { x: 0, y, ...size(key) });
      y += size(key).h + 20;
    }
    blocks.push({ group: '\0loose', w: Math.max(...standalone.map((key) => size(key).w)), h: y - 20, items });
  }
  const columns = new Map<string, Block[]>();
  for (const block of blocks) {
    if (!columns.has(block.group)) {
      columns.set(block.group, []);
    }
    columns.get(block.group)!.push(block);
  }
  const positions = new Map<string, {
    x: number;
    y: number;
  }>();
  let x = left;
  let rowTop = top;
  let rowBottom = top;
  for (const column of columns.values()) {
    const w = Math.max(...column.map((block) => block.w));
    const h = column.reduce((sum, block) => sum + block.h, 0) + (column.length - 1) * 56;
    if (x > left && x + w > left + maxWidth) {
      x = left;
      rowTop = rowBottom + 72;
    }
    let y = rowTop;
    while (true) {
      const collisions = obstacles.filter((r) => x < r.x + r.w + 24 && x + w + 24 > r.x && y < r.y + r.h + 24 && y + h + 24 > r.y);
      if (!collisions.length) {
        break;
      }
      y = Math.max(...collisions.map((r) => r.y + r.h + 24));
    }
    for (const block of column) {
      for (const [key, p] of block.items) {
        positions.set(key, { x: Math.round(x + p.x), y: Math.round(y + p.y) });
      }
      y += block.h + 56;
    }
    rowBottom = Math.max(rowBottom, y - 56);
    x += w + 72;
  }
  return positions;
}
import { findGraphSpot } from './graphPlacement';
export function arrangeAttachments(owner: Rect & {
  key: string;
}, files: string[], sizes: Record<string, Size>, obstacles: (Rect & {
  key: string;
})[]) {
  const layout = arrangeGraph({
    tasks: [{ key: owner.key, group: '', due: 0, files }], loose: [],
    sizes: { ...sizes, [owner.key]: { w: owner.w, h: owner.h } },
    left: 0, top: 0, maxWidth: Infinity, obstacles: [],
  });
  const origin = layout.get(owner.key)!;
  const reserved = [...obstacles];
  const positions = new Map<string, {
    x: number;
    y: number;
  }>();
  for (const key of new Set(files)) {
    const p = layout.get(key)!;
    const size = sizes[key] ?? { w: 190, h: 64 };
    const preferred = { x: owner.x + p.x - origin.x, y: owner.y + p.y - origin.y };
    const clear = reserved.every((r) => {
      return preferred.x + size.w + 20 <= r.x || r.x + r.w + 20 <= preferred.x || preferred.y + size.h + 20 <= r.y || r.y + r.h + 20 <= preferred.y;
    });
    const target = clear ? preferred : findGraphSpot(size, reserved, preferred, owner);
    positions.set(key, target);
    reserved.push({ key, ...target, ...size });
  }
  return positions;
}
