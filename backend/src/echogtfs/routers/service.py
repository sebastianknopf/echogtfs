"""Proxy endpoints for the SIRI communication service."""

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from echogtfs.common.security import CurrentUser

router = APIRouter()

_SIRI_SERVICE_URL = "http://siricomservice:8080"
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

async def _forward_health_request(request: Request) -> Response:
    target_url = f"{_SIRI_SERVICE_URL}/health/live"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in {"host", "content-length", *_HOP_BY_HOP_HEADERS}
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            upstream_response = await client.request(
                request.method,
                target_url,
                headers=headers,
                content=await request.body(),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="SIRI service unavailable") from exc

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers={
            name: value
            for name, value in upstream_response.headers.items()
            if name.lower() not in _HOP_BY_HOP_HEADERS
        },
    )


@router.get("/health", include_in_schema=False)
async def siri_health(_: CurrentUser, request: Request) -> Response:
    """Forward the SIRI communication service health response."""
    return await _forward_health_request(request)
