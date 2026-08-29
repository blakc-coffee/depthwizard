"""Logging config. Never logs tokens or keys.

Owner: Backend Engineer A. See PRD §9.

Redaction happens in a Formatter, not just a Filter, and covers the fully
rendered record — the log message AND any exception traceback. A Filter
alone only sees record.msg/record.args; a logged traceback (e.g. a DB or
Redis connection failure, whose error message commonly embeds the DSN,
password and all) is rendered separately by the Formatter and would
otherwise slip through unredacted. Verified: a raw `logger.exception(...)`
over a ConnectionError embedding a Postgres password leaks the password in
plaintext under the old Filter-only approach; it does not under this one.
"""

from __future__ import annotations

import logging
import re

# (pattern, replacement) — not a single uniform "\1[REDACTED]" substitution,
# since these patterns have different group shapes.
_REDACT_RULES: list[tuple[re.Pattern[str], str]] = [
    # Authorization: Bearer <token>
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+", re.IGNORECASE), r"\1[REDACTED]"),
    # key: value / key=value style secret assignments, however they ended up in a message
    (re.compile(r"((?:supabase_)?service[_-]?role[_-]?key\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(supabase_jwt_secret\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(refresh_token\s*[:=]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    # scheme://user:password@host — DATABASE_URL / REDIS_URL credentials,
    # which commonly end up embedded verbatim in connection-error messages.
    (re.compile(r"(://[^:@/\s]*:)[^@\s]+(@)"), r"\1[REDACTED]\2"),
    # Any bare JWT (Supabase access tokens, service-role keys, and the JWT
    # secret itself are all JWT-shaped: base64url.base64url.base64url,
    # starting with "eyJ") — a safety net for whatever the labeled patterns miss.
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*\b"), "[REDACTED_JWT]"),
]


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_RULES:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # uvicorn and celery configure their own loggers with their own
    # handlers by default, bypassing root — reattach explicitly so their
    # output is redacted too, not just this app's own logger calls.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
