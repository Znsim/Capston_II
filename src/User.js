import React, { useCallback, useEffect, useRef, useState } from "react";
import "./css/UserCss.css";
import { Hands } from "@mediapipe/hands";
import { Pose, POSE_CONNECTIONS } from "@mediapipe/pose";
import { Camera } from "@mediapipe/camera_utils";
import axios from "axios";
import WordBuilder from "./word_composer/word_builder";
import { toFingerspellingModelKeypoints } from "./ai/fingerspellingLandmarks";
import { handleFrontendError, reportDevelopmentError } from "./utils/errorHandling";
import { createSequentialPoller } from "./utils/sequentialPoller";
import { createSubmissionLock } from "./utils/submissionLock";
import DeviceSettingsModal from "./device/DeviceSettingsModal";
import { getConfiguredDeviceId, saveConfiguredDeviceId } from "./utils/deviceSelection";

const INFERENCE_PATH = "/api/inference";
const CONVERSATIONS_PATH = "/api/conversations";
const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 2 * 60 * 1000;
const MEDIAPIPE_ASSET_BASE = (process.env.REACT_APP_MEDIAPIPE_ASSET_BASE || "").replace(/\/$/, "");

export default function User() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const pollerRef = useRef(null);
  const submissionLockRef = useRef(null);
  if (submissionLockRef.current === null) submissionLockRef.current = createSubmissionLock();
  const currentLabelRef = useRef(null);
  const frameCountRef = useRef(0);
  const handDetectedRef = useRef(false);
  const handSessionRef = useRef(0);
  const wordBuilder = useRef(new WordBuilder());
  const [deviceId, setDeviceId] = useState(getConfiguredDeviceId);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [bottomText, setBottomText] = useState("질문을 전송하면 답변이 표시됩니다.");
  const [recognizedLabel, setRecognizedLabel] = useState("-");
  const [confidence, setConfidence] = useState(0);
  const [dwellProgress, setDwellProgress] = useState(0);
  const [composingText, setComposingText] = useState("-");
  const [completedText, setCompletedText] = useState("-");
  const [isSending, setIsSending] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [lastSentMessage, setLastSentMessage] = useState("");
  const [conversationError, setConversationError] = useState("");
  const [inferenceError, setInferenceError] = useState("");
  const [cameraError, setCameraError] = useState("");
  const [speechError, setSpeechError] = useState("");
  const deviceConfigured = Boolean(deviceId);

  const syncComposerText = useCallback(() => {
    setCompletedText(wordBuilder.current.composer.text || "-");
    setComposingText(wordBuilder.current.composer.composing || "-");
  }, []);

  const stopPolling = useCallback(() => {
    pollerRef.current?.stop();
    pollerRef.current = null;
    setIsPolling(false);
  }, []);

  const speakAnswer = useCallback((text) => {
    setSpeechError("");
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      setSpeechError("이 브라우저에서는 답변 음성 출력을 지원하지 않습니다.");
      return;
    }

    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "ko-KR";
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.onerror = (event) => {
        reportDevelopmentError("kiosk.speech", event);
        setSpeechError("답변은 표시했지만 음성 출력에 실패했습니다.");
      };
      window.speechSynthesis.speak(utterance);
    } catch (error) {
      setSpeechError(handleFrontendError(
        "kiosk.speech",
        "답변은 표시했지만 음성 출력에 실패했습니다.",
        error
      ));
    }
  }, []);

  const startPolling = useCallback((conversationId) => {
    stopPolling();
    setIsPolling(true);

    const poller = createSequentialPoller({
      request: () => axios.get(`${CONVERSATIONS_PATH}/${conversationId}`, {
        params: { device_id: deviceId },
        timeout: 5000,
      }),
      onResult: (response) => {
        const data = response.data;
        setConversationError("");
        if (data?.status === "COMPLETED") {
          setIsPolling(false);
          if (data.staff_reply) {
            setBottomText(data.staff_reply);
            speakAnswer(data.staff_reply);
          } else {
            setBottomText("답변이 완료됐지만 내용이 없습니다.");
          }
          return true;
        }
        if (data?.status === "CANCELLED") {
          setIsPolling(false);
          setBottomText("질문이 취소되었습니다. 필요하면 다시 전송해 주세요.");
          return true;
        }
        return false;
      },
      onError: (error) => {
        if (error?.response?.status === 404) {
          setIsPolling(false);
          setConversationError(handleFrontendError(
            "kiosk.answer_poll",
            "전송한 질문을 서버에서 찾을 수 없습니다.",
            error
          ));
          return true;
        }
        setConversationError(handleFrontendError(
          "kiosk.answer_poll",
          "답변 확인 중 서버 연결에 실패했습니다. 자동으로 다시 시도합니다.",
          error
        ));
        return false;
      },
      onTimeout: () => {
        setIsPolling(false);
        setBottomText("답변 대기 시간이 초과되었습니다. 재전송하거나 역무원에게 직접 문의해 주세요.");
      },
      intervalMs: POLL_INTERVAL_MS,
      timeoutMs: POLL_TIMEOUT_MS,
    });
    pollerRef.current = poller;
    poller.start();
  }, [deviceId, speakAnswer, stopPolling]);

  const submitMessage = useCallback(async (message) => {
    const question = message.trim();
    if (!question || isPolling || !submissionLockRef.current.acquire()) return;
    if (!deviceConfigured) {
      submissionLockRef.current.release();
      setConversationError("키오스크 장치 ID가 설정되지 않았습니다.");
      return;
    }

    setIsSending(true);
    setConversationError("");
    setSpeechError("");
    setBottomText("질문을 전송하고 있습니다.");

    try {
      const response = await axios.post(
        CONVERSATIONS_PATH,
        { device_id: deviceId, question_text: question },
        { headers: { "Content-Type": "application/json" }, timeout: 10000 }
      );
      const conversationId = response.data?.conversation_id;
      if (!conversationId) throw new Error("conversation_id_missing");

      setLastSentMessage(question);
      wordBuilder.current.clear();
      setRecognizedLabel("-");
      setConfidence(0);
      setDwellProgress(0);
      syncComposerText();
      setBottomText("역무원 답변을 기다리고 있습니다.");
      startPolling(conversationId);
    } catch (error) {
      if (error?.response?.status === 404) {
        setConversationError(handleFrontendError(
          "kiosk.question_submit",
          "등록되지 않은 키오스크 장치입니다. 장치 ID를 확인해 주세요.",
          error
        ));
      } else {
        setConversationError(handleFrontendError(
          "kiosk.question_submit",
          "질문 전송에 실패했습니다. 입력 내용은 유지되며 다시 전송할 수 있습니다.",
          error
        ));
      }
      setBottomText("질문을 전송하지 못했습니다.");
    } finally {
      submissionLockRef.current.release();
      setIsSending(false);
    }
  }, [deviceConfigured, deviceId, isPolling, startPolling, syncComposerText]);

  const handleBackspace = () => {
    wordBuilder.current.backspace();
    syncComposerText();
  };
  const handleSpace = () => {
    const text = wordBuilder.current.composer.text;
    if (!text || text.endsWith(" ")) return;
    wordBuilder.current.composer.space();
    syncComposerText();
  };
  const handleClear = () => {
    wordBuilder.current.clear();
    currentLabelRef.current = null;
    setRecognizedLabel("-");
    setConfidence(0);
    setDwellProgress(0);
    syncComposerText();
    setConversationError("");
  };

  useEffect(() => {
    const videoEl = videoRef.current;
    const canvasEl = canvasRef.current;
    const ctx = canvasEl.getContext("2d");
    let lastSend = 0;
    let latestHands = [];
    let latestPose = [];
    let stopped = false;

    const hands = new Hands({
      locateFile: (file) => MEDIAPIPE_ASSET_BASE
        ? `${MEDIAPIPE_ASSET_BASE}/hands/${file}`
        : `https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4/${file}`,
    });
    hands.setOptions({
      maxNumHands: 1,
      modelComplexity: 1,
      minDetectionConfidence: 0.7,
      minTrackingConfidence: 0.5,
      selfieMode: false,
    });

    const pose = new Pose({
      locateFile: (file) => MEDIAPIPE_ASSET_BASE
        ? `${MEDIAPIPE_ASSET_BASE}/pose/${file}`
        : `https://cdn.jsdelivr.net/npm/@mediapipe/pose@0.5/${file}`,
    });
    pose.setOptions({
      modelComplexity: 1,
      smoothLandmarks: true,
      enableSegmentation: false,
      smoothSegmentation: false,
      minDetectionConfidence: 0.7,
      minTrackingConfidence: 0.5,
      selfieMode: false,
    });

    const resizeCanvas = (image) => {
      if (image?.width && image?.height) {
        canvasEl.width = image.width;
        canvasEl.height = image.height;
      } else if (videoEl.videoWidth && videoEl.videoHeight) {
        canvasEl.width = videoEl.videoWidth;
        canvasEl.height = videoEl.videoHeight;
      }
    };
    const drawPoints = (points, radius = 3) => {
      for (const point of points) {
        ctx.beginPath();
        ctx.arc(point.x * canvasEl.width, point.y * canvasEl.height, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    };
    const drawPoseSkeleton = (landmarks) => {
      if (!landmarks?.length) return;
      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = 4;
      for (const [start, end] of POSE_CONNECTIONS) {
        const a = landmarks[start];
        const b = landmarks[end];
        if (!a || !b || (a.visibility ?? 1) < 0.5 || (b.visibility ?? 1) < 0.5) continue;
        ctx.beginPath();
        ctx.moveTo(a.x * canvasEl.width, a.y * canvasEl.height);
        ctx.lineTo(b.x * canvasEl.width, b.y * canvasEl.height);
        ctx.stroke();
      }
    };

    const tryInference = async () => {
      const now = Date.now();
      if (now - lastSend <= 200 || !latestHands.length || !deviceConfigured) return;
      lastSend = now;
      const requestHandSession = handSessionRef.current;
      try {
        const response = await axios.post(
          INFERENCE_PATH,
          { device_id: deviceId, keypoints: toFingerspellingModelKeypoints(latestHands[0]) },
          { headers: { "Content-Type": "application/json" }, timeout: 5000 }
        );
        if (!handDetectedRef.current || requestHandSession !== handSessionRef.current) return;
        const data = response.data;
        setInferenceError("");
        currentLabelRef.current =
          data?.recognized_word && data.recognized_word !== "none" && data.confidence >= 0.80
            ? data.recognized_word
            : null;
        setRecognizedLabel(data?.recognized_word || "-");
        setConfidence(data?.confidence || 0);
      } catch (error) {
        currentLabelRef.current = null;
        const message = error?.response?.status === 503
          ? "AI 모델이 준비되지 않았습니다. 관리자에게 문의해 주세요."
          : "AI 인식 서버에 연결할 수 없습니다.";
        setInferenceError(handleFrontendError("kiosk.inference", message, error));
      }
    };

    hands.onResults((results) => {
      resizeCanvas(results.image);
      latestHands = results.multiHandLandmarks || [];
      const handDetected = latestHands.length > 0;
      if (handDetectedRef.current && !handDetected) handSessionRef.current += 1;
      handDetectedRef.current = handDetected;
      if (!handDetected) {
        currentLabelRef.current = null;
        setRecognizedLabel("-");
        setConfidence(0);
      }

      ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
      ctx.fillStyle = "rgba(0, 255, 0, 0.9)";
      for (const hand of latestHands) drawPoints(hand, 4);
      drawPoseSkeleton(latestPose);

      const result = wordBuilder.current.update(currentLabelRef.current);
      setDwellProgress(result.progress || 0);
      setComposingText(result.composing || "-");
      setCompletedText(result.text || "-");
      frameCountRef.current += 1;
      if (latestHands.length && frameCountRef.current % 3 === 0) tryInference();
    });

    pose.onResults((results) => {
      resizeCanvas(results.image);
      latestPose = results.poseLandmarks || [];
      ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
      ctx.fillStyle = "rgba(0, 255, 0, 0.9)";
      for (const hand of latestHands) drawPoints(hand, 4);
      drawPoseSkeleton(latestPose);
    });

    const camera = new Camera(videoEl, {
      onFrame: async () => {
        try {
          await hands.send({ image: videoEl });
          await pose.send({ image: videoEl });
        } catch (error) {
          if (!stopped) {
            setCameraError(handleFrontendError(
              "kiosk.camera_frame",
              "카메라 영상 또는 인식 모델 처리 중 오류가 발생했습니다.",
              error
            ));
          }
        }
      },
      width: 1280,
      height: 720,
    });

    try {
      Promise.resolve(camera.start())
        .then(() => {
          if (!stopped) setCameraError("");
        })
        .catch((error) => {
          if (stopped) return;
          reportDevelopmentError("kiosk.camera_start", error);
          if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
            setCameraError("웹캠 권한이 거부되었습니다. 주소창의 카메라 권한을 허용한 뒤 새로고침해 주세요.");
          } else if (error?.name === "NotFoundError") {
            setCameraError("사용 가능한 웹캠을 찾을 수 없습니다. 연결 상태를 확인해 주세요.");
          } else {
            setCameraError("웹캠을 시작하지 못했습니다. 다른 앱이 카메라를 사용 중인지 확인해 주세요.");
          }
        });
    } catch (error) {
      setCameraError(handleFrontendError(
        "kiosk.camera_start",
        "웹캠을 시작하지 못했습니다. 브라우저 카메라 권한을 확인해 주세요.",
        error
      ));
    }

    return () => {
      stopped = true;
      camera.stop();
      hands.close();
      pose.close();
    };
  }, [deviceConfigured, deviceId]);

  const handleDeviceSelected = (nextDeviceId) => {
    if (isPolling || isSending) return;
    saveConfiguredDeviceId(nextDeviceId);
    setDeviceId(nextDeviceId);
    setSettingsOpen(false);
    setLastSentMessage("");
    setBottomText("선택한 장치로 질문을 전송할 수 있습니다.");
    handleClear();
  };

  useEffect(() => () => {
    stopPolling();
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }, [stopPolling]);

  const controlsDisabled = isSending;
  const sendDisabled = controlsDisabled || isPolling || !deviceConfigured;

  return (
    <div className="root">
      <div className="cameraLayer">
        <video ref={videoRef} autoPlay playsInline muted className="video" />
        <canvas ref={canvasRef} className="overlayCanvas" />
      </div>

      <div className="kioskPanel">
        <div className="statusStack" aria-live="polite">
          {!deviceConfigured && (
            <div className="statusMessage error">
              키오스크 장치 ID가 없습니다. REACT_APP_KIOSK_DEVICE_ID를 설정해 주세요.
            </div>
          )}
          {cameraError && <div className="statusMessage error">{cameraError}</div>}
          {conversationError && <div className="statusMessage error">{conversationError}</div>}
          {inferenceError && <div className="statusMessage error">{inferenceError}</div>}
          {speechError && <div className="statusMessage warning">{speechError}</div>}
        </div>

        <div className="recognitionBox">
          <div className="recognitionTitle">현재 인식</div>
          <div className="recognitionValue">[{recognizedLabel}] ({Math.round(confidence * 100)}%)</div>
          <div className="dwellBar">
            <div className="dwellFill" style={{ width: `${Math.min(dwellProgress * 100, 100)}%` }} />
          </div>
          <div className="textRow"><span>조합 중</span><strong>{composingText}</strong></div>
          <div className="textRow"><span>완성 문장</span><strong>{completedText}</strong></div>

          <div className="buttonRow">
            <button type="button" onClick={handleBackspace} disabled={controlsDisabled}>지우기</button>
            <button type="button" onClick={handleSpace} disabled={controlsDisabled}>공백</button>
            <button type="button" onClick={handleClear} disabled={controlsDisabled}>초기화</button>
            <button
              type="button"
              onClick={() => submitMessage(wordBuilder.current.composer.text)}
              disabled={sendDisabled}
            >
              {isSending ? "전송 중" : isPolling ? "답변 대기 중" : "전송"}
            </button>
            <button
              type="button"
              onClick={() => submitMessage(lastSentMessage)}
              disabled={sendDisabled || !lastSentMessage}
            >재전송</button>
          </div>
          <div className="deviceLabel">
            <span>장치: {deviceId || "미설정"}</span>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              disabled={isPolling || isSending}
              title={isPolling ? "답변 대기 중에는 장치를 변경할 수 없습니다." : "장치 설정"}
            >설정</button>
          </div>
        </div>

        <div className="answerBox">
          <div className="answerTitle">역무원 답변</div>
          <div className="answerText" aria-live="polite">{bottomText}</div>
        </div>
      </div>
      {settingsOpen && (
        <DeviceSettingsModal
          currentDeviceId={deviceId}
          onSelect={handleDeviceSelected}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
