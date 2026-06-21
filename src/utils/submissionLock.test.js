import { createSubmissionLock } from "./submissionLock";

test("전송이 끝나기 전 연속 요청은 한 번만 허용한다", () => {
  const lock = createSubmissionLock();

  expect(lock.acquire()).toBe(true);
  expect(lock.acquire()).toBe(false);
  expect(lock.isLocked()).toBe(true);

  lock.release();
  expect(lock.acquire()).toBe(true);
});
