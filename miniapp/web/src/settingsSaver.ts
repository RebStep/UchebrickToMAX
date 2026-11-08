import type { Settings, SettingsPatch } from './api';
const inFlight = new Set<Promise<boolean>>();
export async function waitForSettingsSaves() {
  while (inFlight.size) {
    await Promise.all([...inFlight]);
  }
}
export function createSettingsSaver(options: {
  request: (patch: SettingsPatch) => Promise<Settings>;
  accepted: (settings: Settings, pending: SettingsPatch) => void;
  failed: () => void;
  busy: (value: boolean) => void;
}) {
  let pending: SettingsPatch = {};
  let running: Promise<boolean> | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  async function flush(): Promise<boolean> {
    clearTimeout(timer);
    if (running) {
      if (!await running) {
        return false;
      }
      return flush();
    }
    if (!Object.keys(pending).length) {
      return true;
    }
    const patch = pending;
    pending = {};
    options.busy(true);
    running = (async () => {
      try {
        const settings = await options.request(patch);
        options.accepted(settings, pending);
        return true;
      }
      catch {
        pending = { ...patch, ...pending };
        options.failed();
        return false;
      }
    })();
    inFlight.add(running);
    const request = running;
    const ok = await running;
    inFlight.delete(request);
    running = null;
    options.busy(false);
    if (ok) {
      return flush();
    }
    return false;
  }
  function save(patch: SettingsPatch) {
    pending = { ...pending, ...patch };
    clearTimeout(timer);
    timer = setTimeout(() => { void flush(); }, 400);
  }
  return { save, flush };
}
