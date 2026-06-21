import asyncio
import json
import time
from collections import defaultdict, deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send


async def _send_json(send: Send, status: int, message: str, headers=None) -> None:
    body = json.dumps(
        {"status": "error", "message": message, "details": None},
        separators=(",", ":"),
    ).encode("utf-8")
    response_headers = [(b"content-type", b"application/json; charset=utf-8")]
    if headers:
        response_headers.extend(headers)
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await _send_json(send, 413, "request_body_too_large")
                    return
            except ValueError:
                await _send_json(send, 400, "invalid_content_length")
                return

        messages = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await _send_json(send, 413, "request_body_too_large")
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)


class RateLimitMiddleware:
    """Single-process sliding-window limiter. Use Redis when running multiple workers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.requests = defaultdict(deque)
        self.lock = asyncio.Lock()

    @staticmethod
    def _bucket(scope: Scope) -> tuple[str, int] | None:
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if path == "/api/auth/login" and method == "POST":
            return "login", 10
        if path == "/api/inference" and method == "POST":
            return "inference", 300
        if path == "/api/conversations" and method == "POST":
            return "conversation", 30
        if path.startswith("/api/staff/"):
            return "staff", 120
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        bucket = self._bucket(scope)
        if bucket is None:
            await self.app(scope, receive, send)
            return

        name, limit = bucket
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        key = (client_ip, name)
        now = time.monotonic()

        async with self.lock:
            timestamps = self.requests[key]
            while timestamps and now - timestamps[0] >= 60:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, int(60 - (now - timestamps[0])))
                await _send_json(
                    send,
                    429,
                    "rate_limit_exceeded",
                    headers=[(b"retry-after", str(retry_after).encode("ascii"))],
                )
                return
            timestamps.append(now)

        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, production: bool) -> None:
        self.app = app
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"permissions-policy", b"camera=(self), microphone=(self)"),
                    ]
                )
                if self.production:
                    headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
