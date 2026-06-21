export function createSequentialPoller({
  request,
  onResult,
  onError,
  onTimeout,
  intervalMs = 1000,
  timeoutMs = 120000,
  now = () => Date.now(),
  schedule = (callback, delay) => setTimeout(callback, delay),
  cancel = (timer) => clearTimeout(timer),
}) {
  let active = false;
  let inFlight = false;
  let timer = null;
  let deadline = 0;

  const stop = () => {
    active = false;
    if (timer !== null) {
      cancel(timer);
      timer = null;
    }
  };

  const run = async () => {
    if (!active || inFlight) return;
    if (now() >= deadline) {
      stop();
      onTimeout?.();
      return;
    }

    inFlight = true;
    let shouldStop = false;
    try {
      const result = await request();
      shouldStop = (await onResult?.(result)) === true;
    } catch (error) {
      shouldStop = (await onError?.(error)) === true;
    } finally {
      inFlight = false;
    }

    if (!active) return;
    if (shouldStop) {
      stop();
      return;
    }
    timer = schedule(run, intervalMs);
  };

  return {
    start() {
      if (active) return false;
      active = true;
      deadline = now() + timeoutMs;
      run();
      return true;
    },
    stop,
    isActive: () => active,
  };
}
