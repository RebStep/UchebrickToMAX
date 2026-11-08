type Clock = {
  now: () => number;
  request: (step: () => void) => number;
  cancel: (id: number) => void;
};
export function createGraphMotion(clock: Clock) {
  let active: {
    frame: number;
    update: (progress: number) => void;
    complete: () => void;
  } | null = null;
  function stop(finish = false) {
    const run = active;
    if (!run) {
      return;
    }
    active = null;
    clock.cancel(run.frame);
    if (finish) {
      run.update(1);
    }
    run.complete();
  }
  function start(update: (progress: number) => void, complete: () => void, duration = 560) {
    stop();
    if (duration <= 0) {
      update(1);
      complete();
      return;
    }
    const run = { frame: 0, update, complete };
    const started = clock.now();
    active = run;
    update(0);
    const step = () => {
      if (active !== run) {
        return;
      }
      const t = Math.min(1, Math.max(0, (clock.now() - started) / duration));
      update(1 - (1 - t) ** 3);
      if (active !== run) {
        return;
      }
      if (t === 1) {
        active = null;
        complete();
      }
      else {
        run.frame = clock.request(step);
      }
    };
    run.frame = clock.request(step);
  }
  return { start, stop, finish: () => stop(true) };
}
