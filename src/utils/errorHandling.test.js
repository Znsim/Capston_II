import { userErrorMessage } from "./errorHandling";

test("API 오류 메시지에 요청 ID를 붙인다", () => {
  const error = { response: { headers: { "x-request-id": "req-test-123" } } };
  expect(userErrorMessage("요청에 실패했습니다.", error)).toBe(
    "요청에 실패했습니다. (요청 ID: req-test-123)"
  );
});

test("요청 ID가 없으면 사용자 메시지만 반환한다", () => {
  expect(userErrorMessage("카메라 오류", new Error("camera"))).toBe("카메라 오류");
});
