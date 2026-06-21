const requestIdFrom = (error) =>
  error?.response?.headers?.["x-request-id"] ||
  error?.response?.data?.request_id ||
  "";

export const userErrorMessage = (message, error) => {
  const requestId = requestIdFrom(error);
  return requestId ? `${message} (요청 ID: ${requestId})` : message;
};

export const reportDevelopmentError = (context, error) => {
  if (process.env.NODE_ENV === "production") return;
  // 요청 본문·비밀번호·쿠키는 출력하지 않고 진단에 필요한 메타데이터만 기록한다.
  console.error(`[${context}]`, {
    message: error?.message || String(error),
    name: error?.name,
    code: error?.code,
    status: error?.response?.status,
    serverMessage: error?.response?.data?.message,
    requestId: requestIdFrom(error) || undefined,
  });
};

export const handleFrontendError = (context, message, error) => {
  reportDevelopmentError(context, error);
  return userErrorMessage(message, error);
};
