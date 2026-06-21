import asyncio
import json
from http.cookies import SimpleCookie
from urllib.parse import urlencode


class ASGITestClient:
    """Small dependency-free ASGI client for this project's JSON API tests."""

    def __init__(self, app):
        self.app = app
        self.cookies = {}
        self.client_number = 0

    def request(self, method, path, json_body=None, query=None, headers=None):
        self.client_number += 1
        body = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
        request_headers = {
            "host": "testserver",
            "content-length": str(len(body)),
        }
        if json_body is not None:
            request_headers["content-type"] = "application/json"
        if self.cookies:
            request_headers["cookie"] = "; ".join(
                f"{key}={value}" for key, value in self.cookies.items()
            )
        request_headers.update(headers or {})
        query_string = urlencode(query or {}).encode("ascii")
        messages = []
        received = False
        response_complete = asyncio.Event()

        async def receive():
            nonlocal received
            if received:
                await response_complete.wait()
                return {"type": "http.disconnect"}
            received = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_complete.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query_string,
            "headers": [
                (key.lower().encode("ascii"), value.encode("utf-8"))
                for key, value in request_headers.items()
            ],
            "client": (f"test-{self.client_number}", 10000 + self.client_number),
            "server": ("testserver", 80),
        }
        asyncio.run(self.app(scope, receive, send))

        start = next(message for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        response_headers = {}
        for key, value in start.get("headers", []):
            name = key.decode("latin1").lower()
            decoded = value.decode("latin1")
            response_headers.setdefault(name, []).append(decoded)
            if name == "set-cookie":
                cookie = SimpleCookie()
                cookie.load(decoded)
                for cookie_name, morsel in cookie.items():
                    if morsel.value:
                        self.cookies[cookie_name] = morsel.value
                    else:
                        self.cookies.pop(cookie_name, None)

        parsed = json.loads(response_body) if response_body else None
        return start["status"], parsed, response_headers

    def get(self, path, query=None, headers=None):
        return self.request("GET", path, query=query, headers=headers)

    def post(self, path, json_body=None, headers=None):
        return self.request("POST", path, json_body=json_body, headers=headers)
