export type UndoAction = {
  title: string;
  detail: string;
  revert: () => void | Promise<void>;
  commit?: () => void | Promise<void>;
};
export type UndoEntry = UndoAction & {
  until: number;
};
export function createUndoQueue(options: {
  duration: number;
  changed: (entry: UndoEntry | null) => void;
  failed: (error: unknown) => void;
  now?: () => number;
  schedule?: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  cancel?: (timer: ReturnType<typeof setTimeout>) => void;
}) {
  const now = options.now ?? Date.now;
  const schedule = options.schedule ?? setTimeout;
  const cancel = options.cancel ?? clearTimeout;
  const pending: {
    entry: UndoEntry;
    timer: ReturnType<typeof setTimeout>;
  }[] = [];
  const running = new Set<Promise<void>>();
  const publish = () => options.changed(pending.at(-1)?.entry ?? null);
  function take(entry: UndoEntry) {
    const index = pending.findIndex((p) => p.entry === entry);
    if (index < 0) {
      return false;
    }
    cancel(pending[index]!.timer);
    pending.splice(index, 1);
    publish();
    return true;
  }
  function finish(entry: UndoEntry) {
    if (!take(entry)) {
      return;
    }
    try {
      const work = Promise.resolve(entry.commit?.()).catch(options.failed).then(() => { });
      running.add(work);
      void work.finally(() => running.delete(work));
    }
    catch (e) {
      options.failed(e);
    }
  }
  function expire() {
    for (const { entry } of [...pending]) {
      if (entry.until <= now()) {
        finish(entry);
      }
    }
  }
  function add(action: UndoAction) {
    expire();
    const entry = { ...action, until: now() + options.duration };
    const timer = schedule(() => finish(entry), options.duration);
    pending.push({ entry, timer });
    publish();
  }
  async function undo() {
    expire();
    const entry = pending.at(-1)?.entry;
    if (entry && take(entry)) {
      await entry.revert();
    }
  }
  function flush() {
    for (const { entry } of [...pending]) {
      finish(entry);
    }
    return Promise.all([...running]).then(() => { });
  }
  return { add, undo, expire, flush };
}
