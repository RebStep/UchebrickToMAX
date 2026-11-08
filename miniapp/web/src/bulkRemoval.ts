import type { FileItem, Task } from './types';
export function planBulkRemoval(state: {
  tasks: Task[];
  loose: FileItem[];
}, selection: {
  tasks: Task[];
  files: FileItem[];
}) {
  const taskIds = new Set(selection.tasks.map((t) => t.id));
  const fileIds = new Set(selection.files.map((f) => f.id));
  const tasks = state.tasks.filter((t) => taskIds.has(t.id)).map((t) => ({ index: state.tasks.indexOf(t), task: { ...t, files: [...t.files] } }));
  const owners = state.tasks.flatMap((t) => {
    return t.files.flatMap((file, index) => {
      if (fileIds.has(file.id)) {
        return [{ taskId: t.id, index, file }];
      }
      return [];
    });
  });
  const loose = state.loose.flatMap((file, index) => {
    if (fileIds.has(file.id)) {
      return [{ index, file }];
    }
    return [];
  });
  return {
    hide: () => {
      state.tasks = state.tasks.filter((t) => !taskIds.has(t.id));
      for (const t of state.tasks) {
        t.files = t.files.filter((f) => !fileIds.has(f.id));
      }
      state.loose = state.loose.filter((f) => !fileIds.has(f.id));
    },
    restore: () => {
      for (const { index, task } of tasks) {
        if (!state.tasks.some((t) => t.id === task.id)) {
          state.tasks.splice(index, 0, { ...task, files: [...task.files] });
        }
      }
      for (const { taskId, index, file } of owners) {
        const owner = state.tasks.find((t) => t.id === taskId);
        if (owner && !owner.files.some((f) => f.id === file.id)) {
          owner.files.splice(index, 0, file);
        }
      }
      for (const { index, file } of loose) {
        if (!state.loose.some((f) => f.id === file.id)) {
          state.loose.splice(index, 0, file);
        }
      }
    },
  };
}
