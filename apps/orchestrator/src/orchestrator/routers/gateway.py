from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from orchestrator.store import TraderStore

router = APIRouter(tags=["gateway"])


def _get_store(request: Request) -> TraderStore:
    return request.app.state.store


@router.api_route(
    "/api/v1/traders/{trader}/api/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def gateway_proxy(trader: str, path: str, request: Request) -> None:
    """Reverse proxy that forwards requests to a trader's session-wrapper API.

    Resolves the trader's loopback port from the store and forwards the
    incoming HTTP request (method, headers, query params, body) to the
    session-wrapper running on that port.
    """
    import httpx

    store = _get_store(request)
    mapping = await store.get_trader(trader)
    if mapping is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trader '{trader}' not registered or provisioned.",
        )

    gateway = request.app.state.gateway
    try:
        return await gateway.forward_request(mapping.port, path, request)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Session wrapper API at port {mapping.port} is currently unreachable. "
                f"Make sure the RDP session has been initialized: {e}"
            ),
        )
