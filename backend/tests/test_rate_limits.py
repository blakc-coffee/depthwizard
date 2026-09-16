"""Every endpoint must carry its own rate limit — runs standalone, no DB or
infra required.

Owner: Backend Engineer A. See PRD §9.

There is no app-wide fallback limit: slowapi's middleware can't see routes
registered through include_router on FastAPI >= 0.137, and a fallback would
key by IP anyway (it runs before auth), which the Vercel proxy collapses into
one shared bucket for all users. So a new endpoint without @limiter.limit is
unprotected — this test is what catches that.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app

EXEMPT_ENDPOINTS = {"app.routes.health.health"}


def _api_routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            # FastAPI >= 0.137 wraps included routers instead of flattening them.
            yield from _api_routes(route.original_router.routes)


def _endpoint_name(route: APIRoute) -> str:
    return f"{route.endpoint.__module__}.{route.endpoint.__name__}"


def test_every_endpoint_has_a_rate_limit():
    limited = app.state.limiter._route_limits
    routes = [r for r in _api_routes(app.routes) if _endpoint_name(r) not in EXEMPT_ENDPOINTS]

    # Guards against the walk silently finding nothing after a FastAPI change.
    assert len(routes) >= 10, f"only found {len(routes)} routes — has FastAPI's routing changed?"

    missing = sorted(f"{sorted(r.methods)} {r.path}" for r in routes if _endpoint_name(r) not in limited)
    assert not missing, f"endpoints without @limiter.limit: {missing}"
