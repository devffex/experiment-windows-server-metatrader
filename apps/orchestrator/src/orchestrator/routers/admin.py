from __future__ import annotations

import os
import subprocess
import shutil
from typing import List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

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


@router.post("/upgrade")
async def upgrade_server(
    request: Request,
    files: List[UploadFile] = File(...),
):
    """Securely upload Python package wheels and trigger a detached host-side self-update script."""
    settings = request.app.state.settings
    
    # 1. Authenticate API Key
    api_key = request.headers.get("X-Admin-API-Key") or request.headers.get("Authorization")
    if api_key and api_key.startswith("Bearer "):
        api_key = api_key[7:]
        
    if settings.admin_api_key and api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin API Key")
        
    # 2. Establish temporary update directory
    update_dir = settings.base_dir / "temp" / "updates"
    
    try:
        # Create directory and clear existing wheels
        if update_dir.exists():
            shutil.rmtree(update_dir)
        update_dir.mkdir(parents=True, exist_ok=True)
        
        # 3. Save uploaded wheels
        saved_files = []
        for file in files:
            if not file.filename:
                continue
            if not file.filename.endswith(".whl"):
                raise HTTPException(status_code=400, detail="Only .whl wheel files are allowed.")
                
            dest_path = update_dir / file.filename
            with open(dest_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(file.filename)
            
        if not saved_files:
            raise HTTPException(status_code=400, detail="No valid wheel files uploaded.")
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to save wheels: {e}")
        
    # 4. Trigger detached host-side update script
    possible_paths = [
        settings.base_dir / "experiment-windows-server-metatrader" / "deployment" / "update-server.ps1",
        settings.base_dir / "deployment" / "update-server.ps1",
    ]
    
    update_script = None
    for path in possible_paths:
        if path.exists():
            update_script = path
            break
            
    if not update_script:
        raise HTTPException(
            status_code=500,
            detail="Deployment update script (update-server.ps1) not found on host."
        )
        
    # Detach execution so we can terminate ourselves
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(update_script),
        "-LocalUpdateDir", str(update_dir),
        "-BaseDir", str(settings.base_dir)
    ]
    
    try:
        # Windows detached process flags
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000
        
        subprocess.Popen(
            cmd,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
            stdout=None,
            stderr=None,
            stdin=subprocess.DEVNULL,
            close_fds=True
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to spawn update process: {e}")
        
    return {
        "status": "success",
        "message": f"Successfully cached {len(saved_files)} wheels. Detached update triggered on host.",
        "wheels": saved_files
    }
