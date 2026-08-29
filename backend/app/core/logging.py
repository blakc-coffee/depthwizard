"""Logging config. Never logs tokens or keys.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import logging
import re

# JWTs, service-role keys, and refresh tokens must never be logged (PRD §9.2).
_REDACT_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+", re.IGNORECASE),
    re.compile(r"((?:supabase_)?service[_-]?role[_-]?key\s*[:=]\s*)\S+", re.IGNORECASE),
    re.compile(r"(supabase_jwt_secret\s*[:=]\s*)\S+", re.IGNORECASE),
    re.compile(r"(refresh_token\s*[:=]\s*)\S+", re.IGNORECASE),
]


class RedactingFilter(logging.Filter):
    """Strips secrets from a record's rendered message before it's emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in _REDACT_PATTERNS:
            msg = pattern.sub(r"\1[REDACTED]", msg)
        record.msg = msg
        record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
