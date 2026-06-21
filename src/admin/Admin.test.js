import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import Admin from "./Admin";

jest.mock("axios");

const waitingQuestion = {
  conversation_id: 11,
  device_id: "SEOUL_01",
  station_name: "서울역",
  location: "1번 출구",
  question_text: "화장실이 어디예요",
  status: "WAITING",
  created_at: "2026-06-20T10:00:00+09:00",
};

const prepareAuthenticatedList = () => {
  axios.get.mockImplementation((url) => {
    if (url === "/api/auth/me") return Promise.resolve({ data: { authenticated: true } });
    if (url === "/api/staff/list") {
      return Promise.resolve({ data: { items: [waitingQuestion], total: 1 } });
    }
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
};

afterEach(() => {
  cleanup();
  jest.clearAllMocks();
});

test("문장·역명·위치·요청을 표시하고 빈 답변을 막는다", async () => {
  prepareAuthenticatedList();
  render(<Admin />);

  expect((await screen.findAllByText("화장실이 어디예요")).length).toBeGreaterThan(0);
  expect(screen.getAllByText("서울역").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/1번 출구/).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "답변 전송" })).toBeDisabled();
});

test("답변 실패 시 질문과 입력 내용을 유지한다", async () => {
  prepareAuthenticatedList();
  axios.post.mockRejectedValue({
    response: { status: 500, headers: { "x-request-id": "reply-fail-1" } },
    message: "server error",
  });
  render(<Admin />);

  expect((await screen.findAllByText("화장실이 어디예요")).length).toBeGreaterThan(0);
  const input = screen.getByPlaceholderText("답변을 입력하세요");
  fireEvent.change(input, { target: { value: "오른쪽입니다" } });
  fireEvent.click(screen.getByRole("button", { name: "답변 전송" }));

  expect(await screen.findByText(/요청 ID: reply-fail-1/)).toBeInTheDocument();
  expect(input).toHaveValue("오른쪽입니다");
  expect(screen.getAllByText("화장실이 어디예요").length).toBeGreaterThan(0);
});

test("전송 중 중복 답변을 막고 성공한 질문을 제거한다", async () => {
  prepareAuthenticatedList();
  let resolveReply;
  axios.post.mockReturnValue(new Promise((resolve) => { resolveReply = resolve; }));
  render(<Admin />);

  expect((await screen.findAllByText("화장실이 어디예요")).length).toBeGreaterThan(0);
  fireEvent.change(screen.getByPlaceholderText("답변을 입력하세요"), {
    target: { value: "오른쪽입니다" },
  });
  const sendButton = screen.getByRole("button", { name: "답변 전송" });
  fireEvent.click(sendButton);

  await waitFor(() => expect(screen.getByRole("button", { name: "전송 중" })).toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: "전송 중" }));
  expect(axios.post).toHaveBeenCalledTimes(1);

  resolveReply({ data: { conversation_id: 11 } });
  await waitFor(() => expect(screen.queryAllByText("화장실이 어디예요")).toHaveLength(0));
});
