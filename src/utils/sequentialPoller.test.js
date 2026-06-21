import { createSequentialPoller } from "./sequentialPoller";

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  jest.useRealTimers();
});

test("느린 응답 중에는 다음 폴링이나 중복 시작을 허용하지 않는다", async () => {
  let resolveRequest;
  const request = jest.fn(() => new Promise((resolve) => { resolveRequest = resolve; }));
  const poller = createSequentialPoller({ request, onResult: () => false });

  expect(poller.start()).toBe(true);
  expect(poller.start()).toBe(false);
  expect(request).toHaveBeenCalledTimes(1);

  resolveRequest({ status: "WAITING" });
  await flushPromises();
  expect(request).toHaveBeenCalledTimes(1);
  poller.stop();
});

test("완료 응답을 받으면 폴링을 종료한다", async () => {
  const request = jest.fn().mockResolvedValue({ status: "COMPLETED" });
  const poller = createSequentialPoller({
    request,
    onResult: (result) => result.status === "COMPLETED",
  });

  poller.start();
  await flushPromises();
  expect(poller.isActive()).toBe(false);
  expect(request).toHaveBeenCalledTimes(1);
});

test("장시간 반복해도 요청은 겹치지 않고 시간 초과 시 끝난다", async () => {
  let currentTime = 0;
  const scheduled = [];
  let concurrent = 0;
  let maxConcurrent = 0;
  const request = jest.fn(async () => {
    concurrent += 1;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    concurrent -= 1;
    return { status: "WAITING" };
  });
  const onTimeout = jest.fn();
  const poller = createSequentialPoller({
    request,
    onResult: () => false,
    onTimeout,
    intervalMs: 1000,
    timeoutMs: 60 * 60 * 1000,
    now: () => currentTime,
    schedule: (callback, delay) => {
      scheduled.push({ callback, delay });
      return scheduled.length;
    },
    cancel: () => {},
  });

  poller.start();
  for (let second = 1; second <= 3600; second += 1) {
    await Promise.resolve();
    await Promise.resolve();
    const next = scheduled.shift();
    expect(next?.delay).toBe(1000);
    currentTime = second * 1000;
    next.callback();
  }
  await Promise.resolve();

  expect(request.mock.calls.length).toBe(3600);
  expect(maxConcurrent).toBe(1);
  expect(onTimeout).toHaveBeenCalledTimes(1);
  expect(poller.isActive()).toBe(false);
});
