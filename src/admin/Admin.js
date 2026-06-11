import { useEffect, useRef, useState } from "react";
import "./AdminCss.css";
import axios from "axios";


export default function Admin() {
  const [chatRooms, setChatRooms] = useState([]);  //채팅방 

  const [selectedRoomId, setSelectedRoomId] = useState(null);  //현재 선택된 채팅방
  const [inputText, setInputText] = useState("");  //관리자 메시지
  const [isListening, setIsListening] = useState(false);  //음성 인식
  const [disabledRoomIds, setDisabledRoomIds] = useState([]);  //비활성화 채팅방 목록

  const recognitionRef = useRef(null);  

  const STAFF_LIST_PATH = "/api/staff/list";
  const REPLY_PATH = "/api/staff/reply";

  const selectedRoom = chatRooms.find((room) => room.id === selectedRoomId);  //현재 선택된 채팅방 정보

  // 사용자 질문 목록 폴링 부분
  // 서버에서 채팅방 목록을 1초마다 가져옴
  useEffect(() => {
    const fetchStaffList = async () => {
      try {
        const response = await axios.get(STAFF_LIST_PATH);
        const data = response.data;

        const list = Array.isArray(data) ? data : data.list;

        if (!Array.isArray(list)) return;

        setChatRooms((prevRooms) =>
          list.map((item) => {
            if (
              prevRooms.find((room) => room.id === item.log_id) &&
              prevRooms
                .find((room) => room.id === item.log_id)
                .messages.filter((message) => message.sender === "user")
                .at(-1)?.text !== (item.recognized_word || "")
            ) {
              setDisabledRoomIds((prev) => prev.filter((id) => id !== item.log_id));

              return {
                ...prevRooms.find((room) => room.id === item.log_id),
                messages: [
                  ...prevRooms.find((room) => room.id === item.log_id).messages,
                  {
                    id: Date.now(),
                    sender: "user",
                    text: item.recognized_word || "",
                    time: new Date().toLocaleTimeString("ko-KR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    }),
                  },
                ],
              };
            }

            return (
              prevRooms.find((room) => room.id === item.log_id) || {
                id: item.log_id,
                name: `채팅방 ${item.log_id}`,
                profile: "",
                messages: [
                  {
                    id: item.log_id,
                    sender: "user",
                    text: item.recognized_word || "",
                  },
                ],
              }
            );
          })
        );
      } catch (error) {
      }
    };

    fetchStaffList();

    const interval = setInterval(fetchStaffList, 1000);

    return () => {
      clearInterval(interval);
    };
  }, []);

  // 음성 인식 설정 부분
  // Web Speech API로 관리자 음성을 텍스트로 변환
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      recognitionRef.current = null;
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "ko-KR";
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event) => {
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript.trim();

        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        }
      }

      if (!finalTranscript) return;

      setInputText((prev) => {
        if (!prev.trim()) return finalTranscript;
        return `${prev} ${finalTranscript}`;
      });
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;
  }, []);

  // 채팅방 선택 부분
  // 비활성화된 채팅방은 선택하지 못하게 함
  const handleSelectRoom = (roomId) => {
    if (disabledRoomIds.includes(roomId)) return;
    setSelectedRoomId(roomId);
  };

  // 관리자 답변 전송 부분
  // 화면에 메시지 추가 후 서버로 답변 전송
  const handleSendMessage = async () => {
    if (disabledRoomIds.includes(selectedRoomId)) return;  
    if (!inputText.trim()) return;

    const sendText = inputText;

    setDisabledRoomIds((prev) =>
      prev.includes(selectedRoomId) ? prev : [...prev, selectedRoomId]
    );

    setChatRooms((prevRooms) =>
      prevRooms.map((room) =>
        room.id === selectedRoomId
          ? {
            ...room,
            messages: [
              ...room.messages,
              {
                id: Date.now(),
                sender: "admin",
                text: sendText,
                time: new Date().toLocaleTimeString("ko-KR", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              },
            ],
          }
          : room
      )
    );

    try {  //관리자 -> 서버로 답변 전송
      await axios.post(
        REPLY_PATH,
        {
          log_id: selectedRoomId,
          reply: sendText,
        },
        {
          headers: { "Content-Type": "application/json" },
        }
      );
    } catch (error) {
    }

    setInputText("");
  };

  // 사용자 메시지 추가 부분
  // 새 사용자 메시지가 들어오면 채팅방을 다시 활성화
  const addUserMessage = (roomId, text) => {
    setChatRooms((prevRooms) =>
      prevRooms.map((room) =>
        room.id === roomId
          ? {
            ...room,
            messages: [
              ...room.messages,
              {
                id: Date.now(),
                sender: "user",
                text,
              },
            ],
          }
          : room
      )
    );

    setDisabledRoomIds((prev) => prev.filter((id) => id !== roomId));
  };

  // 엔터키 전송 부분
  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      handleSendMessage();
    }
  };

  // 마이크 버튼 처리 부분
  const handleStartVoice = () => {
    if (!recognitionRef.current) {
      alert("이 브라우저에서는 음성 인식을 지원하지 않습니다.");
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      return;
    }

    recognitionRef.current.start();
  };

  // 관리자 채팅 화면 UI 부분
  return (
    <div className="admin-page">
      <div className="chat-layout">
        <aside className="chat-sidebar">
          <div className="sidebar-header">
            <h2>대기 중인 질문</h2>
            
          </div>

          <div className="chat-room-list">
            {chatRooms.map((room) => (
              <div
                key={room.id}
                className={`chat-room-item ${selectedRoomId === room.id ? "selected" : ""
                  } ${disabledRoomIds.includes(room.id) ? "disabled-room" : ""}`}
                onClick={() => handleSelectRoom(room.id)}
              >
                <div className="chat-room-left">
                  {room.profile ? (
                    <img
                      src={room.profile}
                      alt={room.name}
                      className="profile-image"
                    />
                  ) : (
                    <div className="profile-image empty-profile"></div>
                  )}
                </div>

                <div className="chat-room-info">
                  <div className="chat-room-name">{room.name}</div>
                  <div className="chat-room-time">
                    {room.messages?.at(-1)?.time || ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <main className="chat-content">
          {selectedRoom ? (
            <>
              <div className="chat-content-header">
                <div className="chat-user-info">
                  {selectedRoom.profile ? (
                    <img
                      src={selectedRoom.profile}
                      alt={selectedRoom.name}
                      className="chat-header-profile"
                    />
                  ) : (
                    <div className="chat-header-profile empty-profile"></div>
                  )}
                  <span>{selectedRoom.name}</span>
                </div>
              </div>

              <div className="chat-message-area">
                {selectedRoom.messages.map((message) => (
                  <div
                    key={message.id}
                    className={`message-row ${message.sender === "admin" ? "admin-row" : "user-row"
                      }`}
                  >
                    <div
                      className={`message-bubble ${message.sender === "admin"
                        ? "admin-bubble"
                        : "user-bubble"
                        }`}
                    >
                      {message.text}
                    </div>
                    <span className="message-time">{message.time}</span>
                  </div>
                ))}
              </div>

              <div className="chat-input-area">
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder=""
                />

                <button
                  type="button"
                  className={`mic-btn ${isListening ? "listening" : ""}`}
                  onClick={handleStartVoice}
                >
                  {isListening ? "음성중지" : "마이크"}
                </button>

                <button type="button" onClick={handleSendMessage}>
                  전송
                </button>
              </div>
            </>
          ) : (
            <div className="no-room-selected"></div>
          )}
        </main>
      </div>
    </div>
  );
}