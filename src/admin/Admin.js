import { useEffect, useRef, useState } from "react";
import "./AdminCss.css";
import axios from "axios";
import { handleFrontendError, reportDevelopmentError } from "../utils/errorHandling";

const STAFF_LIST_PATH = "/api/staff/list";
const REPLY_PATH = "/api/staff/reply";
const LOGIN_PATH = "/api/auth/login";
const LOGOUT_PATH = "/api/auth/logout";
const SESSION_PATH = "/api/auth/me";
const ACTIVE_POLL_MS = 2000;
const IDLE_POLL_MS = 5000;

const formatRequestTime = (value) => {
  if (!value) return "시간 정보 없음";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "시간 정보 없음";
  return date.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const voiceErrorMessage = (errorCode) => {
  const messages = {
    "not-allowed": "마이크 권한이 거부되었습니다. 브라우저 권한을 허용해 주세요.",
    "service-not-allowed": "브라우저에서 음성 인식 서비스 사용이 차단되었습니다.",
    "audio-capture": "사용 가능한 마이크를 찾을 수 없습니다.",
    "no-speech": "음성이 감지되지 않았습니다. 다시 말씀해 주세요.",
    network: "음성 인식 서버에 연결할 수 없습니다.",
    aborted: "음성 입력이 취소되었습니다.",
  };
  return messages[errorCode] || "음성 입력 중 오류가 발생했습니다.";
};

export default function Admin() {
  const [authenticated, setAuthenticated] = useState(null);
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [questions, setQuestions] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [inputText, setInputText] = useState("");
  const [sendingId, setSendingId] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [listError, setListError] = useState("");
  const [replyError, setReplyError] = useState("");
  const [voiceMessage, setVoiceMessage] = useState("");
  const [voiceSupported, setVoiceSupported] = useState(true);
  const recognitionRef = useRef(null);

  const selectedQuestion = questions.find((item) => item.conversation_id === selectedId);

  useEffect(() => {
    let stopped = false;
    axios.get(SESSION_PATH, { withCredentials: true, timeout: 5000 })
      .then(() => {
        if (!stopped) setAuthenticated(true);
      })
      .catch((error) => {
        if (!stopped) {
          if (error?.response?.status !== 401) {
            setAuthError(handleFrontendError(
              "staff.session_check",
              "로그인 상태를 확인하지 못했습니다.",
              error
            ));
          }
          setAuthenticated(false);
        }
      });
    return () => {
      stopped = true;
    };
  }, []);

  useEffect(() => {
    if (!authenticated) return undefined;
    let stopped = false;
    let timer = null;

    const schedule = (delay) => {
      if (!stopped) timer = setTimeout(fetchWaitingQuestions, delay);
    };

    const fetchWaitingQuestions = async () => {
      if (stopped) return;
      try {
        const response = await axios.get(STAFF_LIST_PATH, {
          params: { page: 1, limit: 100 },
          timeout: 7000,
          withCredentials: true,
        });
        const list = Array.isArray(response.data?.items) ? response.data.items : [];
        if (stopped) return;
        setQuestions(list);
        setSelectedId((currentId) => {
          if (list.some((item) => item.conversation_id === currentId)) return currentId;
          return list[0]?.conversation_id ?? null;
        });
        setListError("");
        schedule(document.hidden ? IDLE_POLL_MS : ACTIVE_POLL_MS);
      } catch (error) {
        if (stopped) return;
        if (error?.response?.status === 401) {
          setAuthenticated(false);
          setAuthError(handleFrontendError(
            "staff.waiting_list",
            "로그인 세션이 만료되었습니다.",
            error
          ));
        } else {
          setListError(handleFrontendError(
            "staff.waiting_list",
            "대기 질문을 불러오지 못했습니다. 자동으로 다시 시도합니다.",
            error
          ));
        }
        schedule(IDLE_POLL_MS);
      }
    };

    fetchWaitingQuestions();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [authenticated]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceSupported(false);
      setVoiceMessage("이 브라우저에서는 음성 입력을 지원하지 않습니다.");
      return undefined;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "ko-KR";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.onstart = () => {
      setIsListening(true);
      setVoiceMessage("음성을 듣고 있습니다.");
    };
    recognition.onresult = (event) => {
      let finalTranscript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        if (event.results[index].isFinal) {
          finalTranscript += event.results[index][0].transcript.trim();
        }
      }
      if (finalTranscript) {
        setInputText((previous) => `${previous.trim()} ${finalTranscript}`.trim());
        setVoiceMessage("음성 입력이 반영되었습니다.");
      }
    };
    recognition.onerror = (event) => {
      reportDevelopmentError("staff.voice_input", event);
      setIsListening(false);
      setVoiceMessage(voiceErrorMessage(event.error));
    };
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;

    return () => {
      recognition.abort();
      recognitionRef.current = null;
    };
  }, []);

  const handleSelectQuestion = (conversationId) => {
    if (sendingId !== null) return;
    setSelectedId(conversationId);
    setInputText("");
    setReplyError("");
  };

  const handleSendReply = async () => {
    const reply = inputText.trim();
    if (!selectedQuestion || sendingId !== null) return;
    if (!reply) {
      setReplyError("답변 내용을 입력해 주세요.");
      return;
    }

    const conversationId = selectedQuestion.conversation_id;
    setSendingId(conversationId);
    setReplyError("");

    try {
      await axios.post(
        REPLY_PATH,
        { conversation_id: conversationId, reply },
        {
          headers: {
            "Content-Type": "application/json",
          },
          timeout: 10000,
          withCredentials: true,
        }
      );

      setQuestions((current) => current.filter((item) => item.conversation_id !== conversationId));
      setSelectedId(null);
      setInputText("");
    } catch (error) {
      if (error?.response?.status === 401) {
        setAuthenticated(false);
        setAuthError(handleFrontendError(
          "staff.reply_submit",
          "로그인 세션이 만료되었습니다.",
          error
        ));
      } else if (error?.response?.status === 400) {
        setReplyError(handleFrontendError(
          "staff.reply_submit",
          "이미 답변됐거나 취소된 질문입니다. 목록을 갱신해 주세요.",
          error
        ));
      } else if (error?.response?.status === 404) {
        setReplyError(handleFrontendError(
          "staff.reply_submit",
          "질문을 찾을 수 없습니다. 목록을 갱신해 주세요.",
          error
        ));
      } else {
        setReplyError(handleFrontendError(
          "staff.reply_submit",
          "답변 전송에 실패했습니다. 질문과 입력 내용은 유지됩니다.",
          error
        ));
      }
    } finally {
      setSendingId(null);
    }
  };

  const handleStartVoice = () => {
    if (!voiceSupported || !recognitionRef.current) {
      setVoiceMessage("이 브라우저에서는 음성 입력을 지원하지 않습니다.");
      return;
    }
    try {
      if (isListening) recognitionRef.current.stop();
      else recognitionRef.current.start();
    } catch (error) {
      setVoiceMessage(handleFrontendError(
        "staff.voice_start",
        "음성 입력을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        error
      ));
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSendReply();
    }
  };

  const handleLogin = async (event) => {
    event.preventDefault();
    if (!password || isLoggingIn) return;
    setIsLoggingIn(true);
    setAuthError("");
    try {
      await axios.post(
        LOGIN_PATH,
        { password },
        { withCredentials: true, timeout: 10000 }
      );
      setPassword("");
      setAuthenticated(true);
    } catch (error) {
      if (error?.response?.status === 503) {
        setAuthError(handleFrontendError(
          "staff.login",
          "서버 관리자 인증 설정이 완료되지 않았습니다.",
          error
        ));
      } else if (error?.response?.status === 429) {
        setAuthError(handleFrontendError(
          "staff.login",
          "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.",
          error
        ));
      } else {
        setAuthError(handleFrontendError(
          "staff.login",
          "비밀번호가 올바르지 않습니다.",
          error
        ));
      }
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post(LOGOUT_PATH, {}, { withCredentials: true, timeout: 5000 });
    } catch (error) {
      reportDevelopmentError("staff.logout", error);
    } finally {
      setAuthenticated(false);
      setQuestions([]);
      setSelectedId(null);
      setInputText("");
    }
  };

  if (authenticated === null) {
    return <div className="admin-auth-page">로그인 상태를 확인하고 있습니다.</div>;
  }

  if (!authenticated) {
    return (
      <div className="admin-auth-page">
        <form className="admin-login-card" onSubmit={handleLogin}>
          <h1>역무원 로그인</h1>
          <p>관리자 비밀번호를 입력해 주세요.</p>
          {authError && <div className="admin-alert error">{authError}</div>}
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            maxLength={200}
            autoFocus
          />
          <button type="submit" disabled={!password || isLoggingIn}>
            {isLoggingIn ? "로그인 중" : "로그인"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <div className="chat-layout">
        <aside className="chat-sidebar">
          <div className="sidebar-header">
            <h2>대기 질문</h2>
            <span className="waiting-count">{questions.length}건</span>
            <button type="button" className="logout-button" onClick={handleLogout}>로그아웃</button>
            {listError && <div className="admin-alert error">{listError}</div>}
          </div>

          <div className="chat-room-list">
            {questions.length === 0 && !listError && (
              <div className="empty-list">현재 대기 중인 질문이 없습니다.</div>
            )}
            {questions.map((question) => (
              <button
                type="button"
                key={question.conversation_id}
                className={`question-item ${selectedId === question.conversation_id ? "selected" : ""}`}
                onClick={() => handleSelectQuestion(question.conversation_id)}
                disabled={sendingId !== null}
              >
                <span className="question-station">{question.station_name}</span>
                <span className="question-location">
                  {question.location || "위치 미등록"} · {question.device_id}
                </span>
                <span className="question-preview">{question.question_text}</span>
                <time>{formatRequestTime(question.created_at)}</time>
              </button>
            ))}
          </div>
        </aside>

        <main className="chat-content">
          {selectedQuestion ? (
            <>
              <header className="request-header">
                <div>
                  <h3>{selectedQuestion.station_name}</h3>
                  <p>{selectedQuestion.location || "위치 미등록"} · {selectedQuestion.device_id}</p>
                </div>
                <time>요청 {formatRequestTime(selectedQuestion.created_at)}</time>
              </header>

              <section className="question-detail">
                <span>사용자 질문</span>
                <p>{selectedQuestion.question_text}</p>
              </section>

              <div className="reply-status" aria-live="polite">
                {replyError && <div className="admin-alert error">{replyError}</div>}
                {voiceMessage && <div className="admin-alert info">{voiceMessage}</div>}
              </div>

              <div className="chat-input-area">
                <input
                  type="text"
                  value={inputText}
                  onChange={(event) => {
                    setInputText(event.target.value);
                    setReplyError("");
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder="답변을 입력하세요"
                  disabled={sendingId !== null}
                  maxLength={500}
                />
                <button
                  type="button"
                  className={`mic-btn ${isListening ? "listening" : ""}`}
                  onClick={handleStartVoice}
                  disabled={!voiceSupported || sendingId !== null}
                >
                  {isListening ? "듣는 중" : "음성 입력"}
                </button>
                <button
                  type="button"
                  onClick={handleSendReply}
                  disabled={!inputText.trim() || sendingId !== null}
                >
                  {sendingId !== null ? "전송 중" : "답변 전송"}
                </button>
              </div>
            </>
          ) : (
            <div className="no-room-selected">답변할 질문을 선택해 주세요.</div>
          )}
        </main>
      </div>
    </div>
  );
}
