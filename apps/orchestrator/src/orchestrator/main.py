from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx

from orchestrator.config import get_settings
from orchestrator.gateway import GatewayProxy
from orchestrator.provisioner import Provisioner
from orchestrator.routers import admin, dashboard, gateway
from orchestrator.store import TraderStore


async def _health_monitor(app: FastAPI) -> None:
    """Background task that periodically probes all trader session-wrappers.

    Runs every `settings.health_check_interval` seconds and logs session
    status changes. This ensures the dashboard and /traders endpoint always
    have recent data and provides proactive alerting in server logs.
    """
    settings = app.state.settings
    store: TraderStore = app.state.store
    gw: GatewayProxy = app.state.gateway
    interval = settings.health_check_interval

    while True:
        try:
            await asyncio.sleep(interval)
            mappings = await store.load()
            for username, mapping in mappings.items():
                health = await gw.check_health(mapping.port)
                status = "ONLINE" if health else "OFFLINE"
                print(
                    f"[HEALTH-MONITOR] {username} (port {mapping.port}): {status}",
                    file=sys.stderr,
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[HEALTH-MONITOR] Error: {e}", file=sys.stderr)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize shared state on startup, clean up on shutdown."""
    settings = get_settings()

    # Ensure required directories exist
    settings.scripts_dir.mkdir(parents=True, exist_ok=True)
    settings.rdp_profiles_dir.mkdir(parents=True, exist_ok=True)

    # Initialize shared state
    store = TraderStore(settings.mappings_file)
    gw = GatewayProxy(settings)
    provisioner = Provisioner(settings, store)

    app.state.settings = settings
    app.state.store = store
    app.state.gateway = gw
    app.state.provisioner = provisioner

    # Start background health monitor
    monitor_task = asyncio.create_task(_health_monitor(app))

    print(
        f"[STARTUP] Orchestrator ready on {settings.host}:{settings.port}",
        file=sys.stderr,
    )

    yield

    # Shutdown: cancel monitor and close HTTPX client
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    await gw.close()
    print("[SHUTDOWN] Orchestrator stopped.", file=sys.stderr)


app = FastAPI(
    title="Savisor Central Orchestrator & Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# Reserved system subdomains
RESERVED_SUBDOMAINS = {"orchestrator", "www", "api", "dashboard", "admin", "portal"}


@app.middleware("http")
async def subdomain_routing_middleware(request: Request, call_next):
    settings = app.state.settings
    host = request.headers.get("host", "").lower()

    # Strip port suffix from host header if present (important for local testing)
    if ":" in host:
        host = host.split(":")[0]

    # Match base domain to isolate subdomains
    base_domain = settings.base_domain.lower()
    if host.endswith(f".{base_domain}"):
        subdomain = host[: -len(base_domain) - 1]

        # If it's a reserved subdomain, let it pass to standard orchestrator routes
        if subdomain in RESERVED_SUBDOMAINS:
            return await call_next(request)

        # Otherwise, resolve the trader mapping
        store = app.state.store
        mapping = await store.get_trader(subdomain)

        if mapping:
            # Proxy the request transparently using GatewayProxy
            gateway = app.state.gateway
            path = request.url.path
            # Remove leading slash for gateway path matching if needed
            if path.startswith("/"):
                path = path[1:]
            try:
                return await gateway.forward_request(mapping.port, path, request)
            except httpx.RequestError as e:
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": "Bad Gateway",
                        "detail": f"Trader session wrapper on port {mapping.port} is unreachable: {e}",
                    },
                )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Not Found",
                    "detail": f"Trader subdomain '{subdomain}' is not provisioned on this host.",
                },
            )

    # Fallback: standard local testing, direct IP access, or main domain routing
    return await call_next(request)


app.include_router(admin.router)
app.include_router(gateway.router)
app.include_router(dashboard.router)


def main():
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
