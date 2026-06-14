import React, { useEffect, useRef, useState } from "react";
import "./css/UserCss.css";
import { Hands } from "@mediapipe/hands";
import { Pose, POSE_CONNECTIONS } from "@mediapipe/pose";
import { Camera } from "@mediapipe/camera_utils";
import axios from "axios";
import WordBuilder from "./word_composer/word_builder"; 


export default function User() {
  const videoRef = useRef(null);  //웹캠
  const canvasRef = useRef(null);  //좌표 그릴 캔버스
  const [topText, setTopText] = useState("인식된 수어: -");  //상단 텍스트
  const [bottomText, setBottomText] = useState("하단 자막 예시");  //하단 텍스트
  const [recognizedLabel, setRecognizedLabel] = useState("-");
  const [confidence, setConfidence] = useState(0);
  const [dwellProgress, setDwellProgress] = useState(0);
  const [composingText, setComposingText] = useState("-");
  const [completedText, setCompletedText] = useState("-");
  const deviceId = "SEOUL_01";
  const INFERENCE_PATH = "/api/inference";  //좌표값 전송할 주소
  const POLLING_PATH = "/api/poll/answer";  //답변폴링
  const SEND_PATH = "/api/send";  //전송 버튼

  // 중복 실행 방지 / 폴링 관리용 참조값
  const startedRef = useRef(false);
  const pollingRef = useRef(null);

  // 현재 인식된 자모 저장 / 프레임 카운트 관리
  const currentLabel = useRef(null);
  const frameCountRef = useRef(0);

  // 자모 조합 관리 부분
  // WordBuilder로 자모를 단어로 조합
  const wordBuilder = useRef(new WordBuilder());  

  // 역무원 답변 폴링 부분
  // 전송 후 서버에 답변이 왔는지 1초마다 확인
  const startPolling = (logId) => {
    pollingRef.current = setInterval(async () => {
      try {
        const response = await axios.get(POLLING_PATH, {
          params: {
            device_id: deviceId,
            log_id: logId,  
          },
        });

        const data = response.data;

        if (data?.status === "COMPLETED" && data?.staff_reply) {
          setBottomText(data.staff_reply);

          window.speechSynthesis.cancel();

          const utterance = new SpeechSynthesisUtterance(data.staff_reply);
          utterance.lang = "ko-KR";
          utterance.rate = 1;
          utterance.pitch = 1;

          window.speechSynthesis.speak(utterance);

          clearInterval(pollingRef.current);
        }
      } catch (error) {
      }
    }, 1000);
  };

  // 사용자 메시지 전송 부분
  // 조합된 문장을 서버로 보내고 답변 폴링 시작
  const handleSendClick = async () => {
    const message = wordBuilder.current.composer.text.trim();

    if (!message) return;

    wordBuilder.current.clear();

    setRecognizedLabel("-");
    setConfidence(0);
    setDwellProgress(0);
    setComposingText("-");
    setCompletedText("-");
    setTopText("인식된 수어: -");
    setBottomText("역무원 답변 대기 중");

    try {
      const response = await axios.post(
        SEND_PATH,
        {
          device_id: deviceId,
          message: message,
        },
        {
          headers: { "Content-Type": "application/json" },
        }
      );

      const data = response.data;

      startPolling(data.log_id);
    } catch (error) {
    }
  };
  
  // MediaPipe Hands / Pose / Camera 초기화 부분
  // 웹캠을 켜고 손 좌표와 포즈 좌표를 인식
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const videoEl = videoRef.current;
    const canvasEl = canvasRef.current;
    const ctx = canvasEl.getContext("2d");

    let lastSend = 0;

    let latestHands = [];
    let latestPose = [];

    // 손 인식 모델 설정 부분
    const hands = new Hands({
      locateFile: (file) =>
        `https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4/${file}`,
    });

    hands.setOptions({
      maxNumHands: 2,
      modelComplexity: 1,
      minDetectionConfidence: 0.6,
      minTrackingConfidence: 0.6,
      selfieMode: false, 
    });

    // 포즈 인식 모델 설정 부분
    const pose = new Pose({
      locateFile: (file) =>
        `https://cdn.jsdelivr.net/npm/@mediapipe/pose@0.5/${file}`,
    });

    pose.setOptions({
      modelComplexity: 1,
      smoothLandmarks: true,
      enableSegmentation: false,
      smoothSegmentation: false,
      minDetectionConfidence: 0.6,
      minTrackingConfidence: 0.6,
      selfieMode: false,
    });

    // 캔버스 크기 조정 부분
    const resizeCanvas = (resultsImage) => {
      const img = resultsImage;
      if (img?.width && img?.height) {
        canvasEl.width = img.width;
        canvasEl.height = img.height;
      } else if (videoEl.videoWidth && videoEl.videoHeight) {
        canvasEl.width = videoEl.videoWidth;
        canvasEl.height = videoEl.videoHeight;
      }
    };

    // 손 좌표 점 그리는 부분
    const drawPoints = (points, r = 3) => {
      for (const p of points) {
        const x = p.x * canvasEl.width;
        const y = p.y * canvasEl.height;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    // 포즈 뼈대 그리는 부분
    const drawPoseSkeleton = (poseLandmarks) => {
      if (!poseLandmarks || poseLandmarks.length === 0) return;

      const visTh = 0.5;

      ctx.strokeStyle = "rgba(255,255,255,0.9)";
      ctx.lineWidth = 4;

      for (const [a, b] of POSE_CONNECTIONS) {
        const pa = poseLandmarks[a];
        const pb = poseLandmarks[b];
        if (!pa || !pb) continue;

        const va = pa.visibility ?? 1;
        const vb = pb.visibility ?? 1;
        if (va < visTh || vb < visTh) continue;

        const ax = pa.x * canvasEl.width;
        const ay = pa.y * canvasEl.height;
        const bx = pb.x * canvasEl.width;
        const by = pb.y * canvasEl.height;

        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.stroke();
      }

      ctx.fillStyle = "rgba(0, 213, 255, 0.95)";
      for (const p of poseLandmarks) {
        if (!p) continue;
        const v = p.visibility ?? 1;
        if (v < visTh) continue;

        const x = p.x * canvasEl.width;
        const y = p.y * canvasEl.height;
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    // 좌표값 서버 전송 부분
    const trySend = async () => {
      const now = Date.now();
      if (now - lastSend <= 200) return;
      lastSend = now;

      if (!latestHands || latestHands.length === 0) return;

      const firstHand = latestHands[0];

      const keypoints = firstHand.flatMap((p) => [
        p.x,
        p.y,
        p.z,
      ]);

      try {
        const response = await axios.post(  
          INFERENCE_PATH,
          {
            device_id: deviceId,
            keypoints: keypoints,
          },
          {
            headers: { "Content-Type": "application/json" },
          }
        );

        const data = response.data; 

        // none / confidence 필터 처리 부분
        // 손 미감지 또는 신뢰도 낮으면 자모를 null로 처리
        if (
          data?.recognized_word === "none" ||
          !data?.recognized_word ||
          data?.confidence < 0.75
        ) {
          currentLabel.current = null;
        } else {
          currentLabel.current = data.recognized_word;
        }

        setRecognizedLabel(data?.recognized_word || "-");
        setConfidence(data?.confidence || 0);
        
      } catch (error) {
      }
    };

    // 손 인식 결과 처리 부분
    // 손 좌표 표시, 자모 조합, 일정 프레임마다 서버 전송
    hands.onResults((results) => {
      resizeCanvas(results.image);

      latestHands = results.multiHandLandmarks || [];

      ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);

      ctx.fillStyle = "rgba(0, 255, 0, 0.9)";
      for (const hand of latestHands) drawPoints(hand, 4);

      if (latestPose && latestPose.length > 0) drawPoseSkeleton(latestPose);

      const result = wordBuilder.current.update(currentLabel.current);
      setDwellProgress(result.progress || 0);
      setComposingText(result.composing || "-");
      setCompletedText(result.text || "-");
      setTopText(`인식된 수어: ${result.text || "-"}`);

      frameCountRef.current += 1;
      if (latestHands.length > 0 && frameCountRef.current % 3 === 0) {
        trySend();
      }
    });

    // 포즈 인식 결과 처리 부분
    // 포즈 좌표와 손 좌표를 캔버스에 표시
    pose.onResults((results) => {
      resizeCanvas(results.image);

      latestPose = results.poseLandmarks || [];

      ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);

      ctx.fillStyle = "rgba(0, 255, 0, 0.9)";
      for (const hand of latestHands) drawPoints(hand, 4);

      if (latestPose && latestPose.length > 0) drawPoseSkeleton(latestPose);
    });

    // 웹캠 실행 부분
    // 매 프레임마다 Hands와 Pose 모델에 영상 전달
    const camera = new Camera(videoEl, {
      onFrame: async () => {
        await hands.send({ image: videoEl });
        await pose.send({ image: videoEl });
      },
      width: 1280,
      height: 720,
    });

    camera.start();

    // 화면 종료 시 정리 부분
    // 카메라와 폴링 종료
    return () => {
      camera.stop();

      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // 유저 키오스크 화면 UI 부분
  return (
    <div className="root">
      <div className="cameraLayer">
        <video ref={videoRef} autoPlay playsInline muted className="video" />
        <canvas ref={canvasRef} className="overlayCanvas" />
      </div>

      <div className="kioskPanel">
        <div className="recognitionBox">
          <div className="recognitionTitle">
            현재 인식
          </div>

          <div className="recognitionValue">
            [{recognizedLabel}] ({Math.round(confidence * 100)}%)
          </div>

          <div className="dwellBar">
            <div
              className="dwellFill"
              style={{ width: `${Math.min(dwellProgress * 100, 100)}%` }}
            />
          </div>

          <div className="textRow">
            <span>조합 중</span>
            <strong>【{composingText}】</strong>
          </div>

          <div className="textRow">
            <span>완성 단어</span>
            <strong>{completedText}</strong>
          </div>

          <div className="buttonRow">
            <button type="button"
              onClick={() => {
                wordBuilder.current.backspace();
              
                const text = wordBuilder.current.composer.text;
                const composing = wordBuilder.current.composer.composing;

                setCompletedText(text || "-");
                setComposingText(composing || "-");
                setTopText(`인식된 수어: ${text || "-"}`);
              }}
            >지우기</button>
            <button type="button"
              onClick={() => {
                wordBuilder.current.clear();

                setRecognizedLabel("-");
                setConfidence(0);
                setDwellProgress(0);
                setComposingText("-");
                setCompletedText("-");
                setTopText("인식된 수어: -");
                setBottomText("답변 대기 중");
              }}
            >초기화</button>
            <button type="button" onClick={handleSendClick}>전송</button>
          </div>
        </div>

        <div className="answerBox">
          <div className="answerTitle">─── 역무원 답변 ───</div>
          <div className="answerText">{bottomText}</div>
        </div>
      </div>
    </div>
  );
}