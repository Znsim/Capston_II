import { cleanup, render, screen } from "@testing-library/react";
import App from "./App";

jest.mock("./User", () => () => <div>키오스크 화면</div>);
jest.mock("./admin/Admin", () => () => <div>역무원 화면</div>);

afterEach(() => {
  cleanup();
  window.history.pushState({}, "", "/");
});

test("기본 경로에 키오스크 화면을 표시한다", () => {
  window.history.pushState({}, "", "/");
  render(<App />);
  expect(screen.getByText("키오스크 화면")).toBeInTheDocument();
});

test("관리자 경로에 역무원 화면을 표시한다", () => {
  window.history.pushState({}, "", "/admin");
  render(<App />);
  expect(screen.getByText("역무원 화면")).toBeInTheDocument();
});
