/**
 * MediaPipe Hands landmarks를 지문자 모델의 학습 좌표계로 변환한다.
 *
 * 학습 데이터는 OpenCV 프레임을 좌우 반전한 뒤 추출했으므로 브라우저의
 * 원본 카메라 좌표에서는 x만 반전해야 한다. y와 z는 그대로 유지한다.
 */
export function toFingerspellingModelKeypoints(landmarks) {
  if (!Array.isArray(landmarks) || landmarks.length !== 21) {
    throw new Error("invalid_hand_landmarks");
  }

  return landmarks.flatMap(({ x, y, z }) => [1 - x, y, z]);
}
