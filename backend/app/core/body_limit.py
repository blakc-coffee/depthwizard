"""Request body size cap, enforced before FastAPI reads the body.

Owner: Backend Engineer A. See PRD §9.

FastAPI parses a multipart body (spooling file parts to disk) BEFORE it
resolves dependencies, so without this an unauthenticated client can make
the API write an arbitrarily large upload to disk before auth ever rejects
it. The per-file check in routes/jobs.py still applies on top of this.
"""

from __future__ import annotations

import json

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ApiException, ErrorCode


class _BodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int, max_upload_mb: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_upload_mb = max_upload_mb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None and content_length.isdigit() and int(content_length) > self.max_body_bytes:
            await self._send_too_large(send)
            return

        # Chunked uploads have no Content-Length, so count what actually arrives.
        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded:
                # FastAPI converts the _BodyTooLarge raised mid-parse into its
                # own generic 400 — replace that with the real 413.
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    await self._send_too_large(send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if not response_started:
                await self._send_too_large(send)

    async def _send_too_large(self, send: Send) -> None:
        exc = ApiException(ErrorCode.FILE_TOO_LARGE, f"File exceeds the {self.max_upload_mb} MB limit.")
        body = json.dumps(exc.to_envelope()).encode()
        await send(
            {
                "type": "http.response.start",
                "status": exc.http_status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
