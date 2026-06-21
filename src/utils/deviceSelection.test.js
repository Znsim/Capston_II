import { DEVICE_STORAGE_KEY, getConfiguredDeviceId, saveConfiguredDeviceId } from "./deviceSelection";

afterEach(() => window.localStorage.clear());

test("유효한 장치 선택을 브라우저에 저장하고 복원한다", () => {
  saveConfiguredDeviceId("BUSAN_02");
  expect(window.localStorage.getItem(DEVICE_STORAGE_KEY)).toBe("BUSAN_02");
  expect(getConfiguredDeviceId()).toBe("BUSAN_02");
});

test("잘못된 장치 ID는 저장하지 않는다", () => {
  expect(() => saveConfiguredDeviceId("bad-device")).toThrow("invalid_device_id_format");
});
