import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import DeviceSettingsModal from "./DeviceSettingsModal";

jest.mock("axios");

beforeEach(() => jest.clearAllMocks());

test("인증되지 않은 사용자는 관리자 비밀번호 입력 화면을 본다", async () => {
  axios.get.mockRejectedValueOnce({ response: { status: 401 } });
  render(<DeviceSettingsModal currentDeviceId="SEOUL_01" onSelect={jest.fn()} onClose={jest.fn()} />);
  expect(await screen.findByPlaceholderText("관리자 비밀번호")).toBeInTheDocument();
});

test("등록된 장치를 선택하면 로그아웃 후 선택값을 전달한다", async () => {
  axios.get.mockImplementation((path) => {
    if (path === "/api/auth/me") return Promise.resolve({ data: { authenticated: true } });
    if (path === "/api/devices") {
      return Promise.resolve({
        data: [{ device_id: "SEOUL_01", station_name: "서울역", location: "1번 창구" }],
      });
    }
    return Promise.reject(new Error("unexpected path"));
  });
  axios.post.mockResolvedValue({ data: { authenticated: false } });
  const onSelect = jest.fn();

  render(<DeviceSettingsModal currentDeviceId="SEOUL_01" onSelect={onSelect} onClose={jest.fn()} />);
  expect(await screen.findByDisplayValue("SEOUL_01")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "이 장치 사용" }));

  await waitFor(() => expect(onSelect).toHaveBeenCalledWith("SEOUL_01"));
  expect(axios.post).toHaveBeenCalledWith(
    "/api/auth/logout",
    {},
    expect.objectContaining({ withCredentials: true })
  );
});
