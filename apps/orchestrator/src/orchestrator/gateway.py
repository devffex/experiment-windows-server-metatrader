from __future__ import annotations

import sys
from typing import Optional

import httpx
from fastapi import Request, Response

from orchestrator.config import Settings

# Headers that must not be forwarded between hops
HOP_BY_HOP_HEADERS = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
})


class GatewayProxy:
    """Production-grade reverse proxy for forwarding requests to session-wrapper APIs.

    Features:
    - Connection pooling via httpx.Limits
    - Hop-by-hop header stripping
    - Configurable timeouts
    - Health probing for session status
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.proxy_timeout),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )

    async def forward_request(
        self, port: int, path: str, request: Request
    ) -> Response:
        """Forward an incoming HTTP request to a session-wrapper on the given port."""
        target_url = f"http://127.0.0.1:{port}/{path}"

        body = await request.body()

        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS and k.lower() != "host"
        }

        params = dict(request.query_params)

        resp = await self.client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=params,
            content=body,
        )

        response_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in HOP_BY_HOP_HEADERS
        }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
        )

    async def check_health(self, port: int) -> Optional[dict]:
        """Probe a session-wrapper's /health endpoint.

        Returns the health JSON dict on success, or None if unreachable.
        """
        url = f"http://127.0.0.1:{port}/health"
        try:
            resp = await self.client.get(
                url, timeout=httpx.Timeout(self.settings.health_check_timeout)
            )
            if resp.status_code == 200:
                return resp.json()
        except httpx.RequestError as e:
            print(
                f"[HEALTH] Port {port} unreachable: {e}",
                file=sys.stderr,
            )
        return None

    async def close(self) -> None:
        """Gracefully close the underlying HTTPX client."""
        await self.client.aclose()
