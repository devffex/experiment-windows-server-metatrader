from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

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

app.include_router(admin.router)
app.include_router(gateway.router)
app.include_router(dashboard.router)


def main():
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
