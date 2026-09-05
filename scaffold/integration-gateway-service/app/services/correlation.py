"""Correlation-id middleware (FR-INT-05: every call is logged and traceable).

Reads `X-Correlation-Id` from the inbound request if the caller supplied one
(so a caller can tie its own logs to ours), otherwise generates one. Always
echoed back on the response header and available to route handlers via
`request.state.correlation_id`.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

HEADER = "X-Correlation-Id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get(HEADER)
        try:
            correlation_id = str(uuid.UUID(supplied)) if supplied else str(uuid.uuid4())
        except ValueError:
            # external_system_logs.correlation_id is UUID-typed; an unparsable
            # caller-supplied value falls back to a fresh one rather than 500ing.
            correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[HEADER] = correlation_id
        return response
