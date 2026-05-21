from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from shared_schemas import (
    DeprovisionResponse,
    ProvisionRequest,
    ProvisionResponse,
    TraderListResponse,
    TraderStatus,
)

from orchestrator.provisioner import Provisioner, ProvisioningError
from orchestrator.store import TraderStore

router = APIRouter(tags=["admin"])


def _get_store(request: Request) -> TraderStore:
    return request.app.state.store


def _get_provisioner(request: Request) -> Provisioner:
    return request.app.state.provisioner


@router.post("/provision", response_model=ProvisionResponse)
async def provision_trader(payload: ProvisionRequest, request: Request):
    """Provision a new trader: create Windows user, shell override, RDP profile, and port mapping."""
    provisioner = _get_provisioner(request)
    try:
        mapping = await provisioner.provision(payload.organization, payload.trader_name)
        return ProvisionResponse(
            status="success",
            message=f"Trader {payload.organization}-{payload.trader_name} provisioned successfully.",
            port=mapping.port,
            password=mapping.password,
            rdp_profile=mapping.rdp_profile,
        )
    except ProvisioningError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traders", response_model=TraderListResponse)
async def list_traders(request: Request):
    """List all provisioned traders with their live session status."""
    store = _get_store(request)
    gateway = request.app.state.gateway
    mappings = await store.load()

    traders: list[TraderStatus] = []
    for username, mapping in mappings.items():
        health = await gateway.check_health(mapping.port)
        traders.append(
            TraderStatus(
                username=username,
                organization=mapping.organization,
                trader_name=mapping.trader_name,
                port=mapping.port,
                rdp_profile=mapping.rdp_profile,
                session_online=health is not None,
                health=health,
            )
        )

    return TraderListResponse(traders=traders)


@router.get("/traders/{trader}/status", response_model=TraderStatus)
async def trader_status(trader: str, request: Request):
    """Probe the session-wrapper health for a specific trader."""
    store = _get_store(request)
    gateway = request.app.state.gateway

    mapping = await store.get_trader(trader)
    if mapping is None:
        raise HTTPException(status_code=404, detail=f"Trader '{trader}' not found.")

    health = await gateway.check_health(mapping.port)
    return TraderStatus(
        username=trader,
        organization=mapping.organization,
        trader_name=mapping.trader_name,
        port=mapping.port,
        rdp_profile=mapping.rdp_profile,
        session_online=health is not None,
        health=health,
    )


@router.delete("/traders/{trader}", response_model=DeprovisionResponse)
async def deprovision_trader(trader: str, request: Request):
    """Fully deprovision a trader: logoff session, delete Windows user, remove mapping."""
    provisioner = _get_provisioner(request)
    removed = await provisioner.deprovision(trader)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Trader '{trader}' not found.")

    return DeprovisionResponse(
        status="success",
        message=f"Trader '{trader}' fully deprovisioned (session terminated, user deleted, mapping removed).",
    )
