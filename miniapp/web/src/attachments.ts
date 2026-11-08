import type { FileItem, Task } from './types';
export function createAttachmentQueue() {
  const pending = new Map<number, Promise<void>>();
  return {
    get size() { return pending.size; },
    enqueue(id: number, work: () => Promise<void>) {
      const job = (pending.get(id) ?? Promise.resolve()).catch(() => { }).then(work);
      pending.set(id, job);
      const cleanup = () => {
        if (pending.get(id) === job) {
          pending.delete(id);
        }
      };
      job.then(cleanup, cleanup);
      return job;
    },
  };
}
export function linkAttachmentLocally(state: {
  tasks: Task[];
  loose: FileItem[];
}, file: FileItem, taskId: number) {
  const target = state.tasks.find((t) => t.id === taskId);
  if (!target) {
    return null;
  }
  const owners: { id: number; index: number; file: FileItem }[] = [];
  for (const task of state.tasks) {
    for (let index = 0; index < task.files.length; index++) {
      const taskFile = task.files[index];
      if (taskFile.id === file.id) {
        owners.push({ id: task.id, index, file: taskFile });
      }
    }
  }
  const looseIndex = state.loose.findIndex((f) => f.id === file.id);
  const loose = state.loose[looseIndex];
  const alreadyAttached = target.files.some((f) => f.id === file.id);
  state.loose = state.loose.filter((f) => f.id !== file.id);
  if (file.type === 'note' || file.type === 'link') {
    for (const t of state.tasks) {
      if (t.id !== taskId) {
        t.files = t.files.filter((f) => f.id !== file.id);
      }
    }
  }
  if (!alreadyAttached) {
    target.files.push({ ...file, task_id: taskId });
  }
  return {
    file: target.files.find((f) => f.id === file.id)!, alreadyAttached,
    rollback() {
      for (const t of state.tasks) {
        t.files = t.files.filter((f) => f.id !== file.id);
      }
      for (const owner of owners) {
        const t = state.tasks.find((t) => t.id === owner.id);
        t?.files.splice(Math.min(owner.index, t.files.length), 0, owner.file);
      }
      state.loose = state.loose.filter((f) => f.id !== file.id);
      if (loose) {
        state.loose.splice(Math.min(looseIndex, state.loose.length), 0, loose);
      }
    },
  };
}
