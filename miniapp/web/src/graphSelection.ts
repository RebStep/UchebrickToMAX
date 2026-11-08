import type { FileItem, Task } from './types';
export function planGraphSelection(tasks: Task[], loose: FileItem[], selected: ReadonlySet<string>) {
  const movingTasks = tasks.filter((t) => selected.has(`t${t.id}`));
  const files = new Map<number, FileItem>();
  for (const t of movingTasks) {
    for (const f of t.files) {
      files.set(f.id, f);
    }
  }
  const anchored: {
    task: Task;
    files: FileItem[];
  }[] = [];
  for (const task of tasks) {
    const chosen = task.files.filter((f) => selected.has(`f${f.id}`) && !files.has(f.id));
    if (!chosen.length) {
      continue;
    }
    const uniqueFiles = new Map<number, FileItem>();
    for (const file of chosen) {
      uniqueFiles.set(file.id, file);
    }
    const unique = [...uniqueFiles.values()];
    anchored.push({ task, files: unique });
    for (const f of unique) {
      files.set(f.id, f);
    }
  }
  const standalone = loose.filter((f) => selected.has(`f${f.id}`) && !files.has(f.id));
  for (const f of standalone) {
    files.set(f.id, f);
  }
  return {
    tasks: movingTasks, files: [...files.values()], anchored, loose: standalone,
    canArrange: movingTasks.length > 0 || anchored.length > 0 || standalone.length > 1,
  };
}
