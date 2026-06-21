import { toFingerspellingModelKeypoints } from "./fingerspellingLandmarks";

test("converts browser landmarks to the mirrored model coordinate system", () => {
  const landmarks = Array.from({ length: 21 }, (_, index) => ({
    x: index / 20,
    y: 0.25,
    z: -0.1,
  }));

  const keypoints = toFingerspellingModelKeypoints(landmarks);

  expect(keypoints).toHaveLength(63);
  expect(keypoints.slice(0, 3)).toEqual([1, 0.25, -0.1]);
  expect(keypoints.slice(-3)).toEqual([0, 0.25, -0.1]);
});

test("rejects an incomplete hand landmark set", () => {
  expect(() => toFingerspellingModelKeypoints([])).toThrow(
    "invalid_hand_landmarks"
  );
});
