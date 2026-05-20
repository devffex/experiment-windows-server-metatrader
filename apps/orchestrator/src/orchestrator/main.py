import os
import sys
import json
import secrets
import string
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse
from shared_schemas import ProvisionRequest, ProvisionResponse

app = FastAPI(title="Savisor Central Orchestrator & Gateway")

# Paths and configuration
PORT_MAPPING_FILE = Path("trader_mappings.json")
RDP_PROFILES_DIR = Path("rdp_profiles")
SCRIPTS_DIR = Path("scripts")

# Create directories if they do not exist
RDP_PROFILES_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR.mkdir(exist_ok=True)

# Shared client for reverse proxy gateway
client = httpx.AsyncClient()

def load_mappings() -> Dict[str, Dict[str, Any]]:
    """Loads current trader port and credential mappings."""
    if PORT_MAPPING_FILE.exists():
        try:
            return json.loads(PORT_MAPPING_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_mappings(mappings: Dict[str, Dict[str, Any]]):
    """Saves updated trader port and credential mappings."""
    PORT_MAPPING_FILE.write_text(json.dumps(mappings, indent=4))

def get_next_available_port(mappings: Dict[str, Dict[str, Any]]) -> int:
    """Finds the next free port between 8001 and 8005 (or above if needed)."""
    used_ports = {data["port"] for data in mappings.values()}
    for port in range(8001, 8006):
        if port not in used_ports:
            return port
    # Fallback to high port range if maximum development instances reached
    fallback_port = 8006
    while fallback_port in used_ports:
        fallback_port += 1
    return fallback_port

def generate_secure_password(length: int = 16) -> str:
    """Generates a secure password meeting Windows Server complexity requirements."""
    # Must contain uppercase, lowercase, digits, and special characters
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    special = "!@#$%"
    
    all_chars = upper + lower + digits + special
    password = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    password += [secrets.choice(all_chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)

def run_windows_command(cmd: list[str]) -> tuple[bool, str]:
    """Runs a shell command on Windows; logs command for non-Windows platforms."""
    cmd_str = " ".join(cmd)
    if os.name == 'nt':
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True, res.stdout
        except subprocess.CalledProcessError as e:
            return False, f"Command failed: {e.stderr}\nOutput: {e.stdout}"
    else:
        # Cross-platform simulation logging
        print(f"[SIMULATED WINDOWS COMMAND]: {cmd_str}", file=sys.stderr)
        return True, f"Simulated execution on non-Windows OS of: {cmd_str}"

def provision_windows_user(username: str, password: str) -> tuple[bool, str]:
    """Executes net user commands to create a user and grant RDP permissions."""
    # 1. Create the user with high complexity password
    success, msg = run_windows_command(["net", "user", username, password, "/add", "/y"])
    if not success and "exists" not in msg.lower():
        return False, f"Failed to create user: {msg}"
    
    # 2. Grant Remote Desktop privileges
    success, msg = run_windows_command(["net", "localgroup", "Remote Desktop Users", username, "/add"])
    if not success and "already" not in msg.lower():
        # Handle cases where localgroup name varies based on locale
        success, msg = run_windows_command(["net", "localgroup", "Usuarios de escritorio remoto", username, "/add"])
        if not success:
            print(f"[WARNING]: Could not add user to RDP group. Manual grouping might be needed: {msg}", file=sys.stderr)
            
    return True, "User successfully provisioned."

def configure_custom_shell(username: str) -> tuple[bool, str]:
    """
    Mounts the offline NTUSER.DAT registry key of the provisioned user to inject 
    a custom Winlogon Shell. This ensures the user starts start-session.bat in full screen,
    completely bypassing the standard explorer.exe desktop.
    """
    # Define script startup path
    startup_script = r"C:\savisor\scripts\start-session.bat"
    
    # Target profile NTUSER.DAT path on typical Windows systems
    ntuser_path = f"C:\\Users\\{username}\\NTUSER.DAT"
    temp_hive = f"TempHive_{username}"
    
    # 1. Load registry hive
    success, msg = run_windows_command(["reg", "load", f"HKLM\\{temp_hive}", ntuser_path])
    if not success:
        return False, f"Failed to load NTUSER.DAT hive (User may need to login once or registry is locked): {msg}"
    
    # 2. Write custom Winlogon Shell registry entry
    success, msg = run_windows_command([
        "reg", "add", 
        f"HKLM\\{temp_hive}\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon", 
        "/v", "Shell", 
        "/t", "REG_SZ", 
        "/d", startup_script, 
        "/f"
    ])
    if not success:
        # Rollback/Unload anyway
        run_windows_command(["reg", "unload", f"HKLM\\{temp_hive}"])
        return False, f"Failed to modify Shell key in NTUSER.DAT hive: {msg}"
    
    # 3. Unload registry hive
    success, msg = run_windows_command(["reg", "unload", f"HKLM\\{temp_hive}"])
    if not success:
        return False, f"Failed to unload NTUSER.DAT hive properly: {msg}"
        
    return True, "Registry custom shell configured successfully."

def write_rdp_file(username: str) -> Path:
    """Generates a customized Remote Desktop connection profile (.rdp) for the trader."""
    rdp_content = f"""# Savisor Remote Desktop Profile
auto connect:i:1
full address:s:127.0.0.1
username:s:{username}
screen mode id:i:2
use multimon:i:0
session bpp:i:32
alternate shell:s:C:\\savisor\\scripts\\start-session.bat
shell working directory:s:C:\\savisor\\scripts
connect to console:i:0
disable wallpaper:i:1
disable full window drag:i:1
disable menu anims:i:1
disable themes:i:1
bitmapcachepersistenable:i:1
"""
    rdp_file = RDP_PROFILES_DIR / f"{username}.rdp"
    rdp_file.write_text(rdp_content)
    return rdp_file.absolute()

def write_startup_script():
    """Writes the startup batch script start-session.bat that runs under RDP."""
    script_content = """@echo off
title MetaTrader 5 Session Wrapper Startup
echo Starting MetaTrader 5 portable terminal in user session context...

:: Set working directory
cd /d C:\\savisor

:: 1. Launch MetaTrader 5 Portable terminal full screen
start /max "" "C:\\savisor\\terminal\\terminal64.exe" /portable

:: 2. Launch FastAPI loopback wrapper running under the same user session on allocated port
:: Port will be parsed or passed through system-level environment variables
python -m session_wrapper.main --port=%PORT%
"""
    script_file = SCRIPTS_DIR / "start-session.bat"
    script_file.write_text(script_content)

# Initialize startup script on first orchestrator run
write_startup_script()


@app.post("/provision", response_model=ProvisionResponse)
def provision_trader(payload: ProvisionRequest):
    # Formulate username e.g. savisor-julio
    username = f"{payload.organization.lower()}-{payload.trader_name.lower()}"
    
    # Retrieve mappings
    mappings = load_mappings()
    
    if username in mappings:
        user_data = mappings[username]
        return ProvisionResponse(
            status="success",
            message="Trader already provisioned. Returning existing profile details.",
            port=user_data["port"],
            password=user_data["password"],
            rdp_profile=user_data["rdp_profile"]
        )
    
    # 1. Allocate port
    port = get_next_available_port(mappings)
    
    # 2. Generate secure password
    password = generate_secure_password()
    
    # 3. Create Windows User Accounts & assign Remote Desktop rights
    user_ok, user_msg = provision_windows_user(username, password)
    if not user_ok:
        raise HTTPException(status_code=500, detail=f"Windows Account creation failed: {user_msg}")
    
    # 4. Modify registry hives to assign custom start shell script
    shell_ok, shell_msg = configure_custom_shell(username)
    if not shell_ok:
        # Log warning, but allow RDP file generation and proxy mappings to succeed for standard flow
        print(f"[WARNING]: Registry custom shell bypass failed (Requires high privileges): {shell_msg}", file=sys.stderr)
    
    # 5. Generate client-side Remote Desktop .rdp file
    rdp_path = write_rdp_file(username)
    
    # 6. Save configuration to mapping DB
    mappings[username] = {
        "port": port,
        "password": password,
        "rdp_profile": str(rdp_path),
        "organization": payload.organization,
        "trader_name": payload.trader_name
    }
    save_mappings(mappings)
    
    return ProvisionResponse(
        status="success",
        message="Trader provisioned successfully. Windows user, RDP custom shell and API port registered.",
        port=port,
        password=password,
        rdp_profile=str(rdp_path)
    )

@app.get("/traders")
def list_traders():
    """Lists all active provisioned traders and their registered configurations."""
    return load_mappings()

# --- REVERSE PROXY GATEWAY ROUTING ---

@app.api_route("/api/v1/traders/{trader}/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def gateway_proxy(trader: str, path: str, request: Request):
    """
    Gateway Reverse Proxy. Reads incoming requests directed to traders
    and forwards them dynamically to their respective session-isolated APIs.
    """
    mappings = load_mappings()
    if trader not in mappings:
        raise HTTPException(status_code=404, detail=f"Trader '{trader}' not registered or provisioned.")
    
    port = mappings[trader]["port"]
    target_url = f"http://127.0.0.1:{port}/{path}"
    
    # Extract request body
    body = await request.body()
    
    # Extract custom headers (ignoring Host header to prevent routing errors)
    headers = {k: v for k, v in request.headers.items() if k.lower() != 'host'}
    
    # Capture query parameters
    params = dict(request.query_params)
    
    try:
        # Dynamic forwarding using HTTPX
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=params,
            content=body,
            timeout=15.0
        )
        
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers)
        )
        
    except httpx.RequestError as e:
        # Return elegant error if session-wrapper API is down (e.g. if RDP session hasn't started)
        raise HTTPException(
            status_code=502, 
            detail=f"Session wrapper API at port {port} is currently unreachable. Make sure RDP session has been initialized: {e}"
        )

@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    """Renders a simple state and diagnostics control dashboard."""
    mappings = load_mappings()
    rows = ""
    for user, info in mappings.items():
        rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #333;">{user}</td>
            <td style="padding: 10px; border-bottom: 1px solid #333;">{info['organization']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #333;"><code>{info['port']}</code></td>
            <td style="padding: 10px; border-bottom: 1px solid #333;"><code>{info['rdp_profile']}</code></td>
        </tr>
        """
        
    if not rows:
        rows = "<tr><td colspan='4' style='padding:15px; text-align:center; color:#777;'>No traders provisioned yet.</td></tr>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Savisor Orchestrator Gateway Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #121212; color: #e0e0e0; margin: 0; padding: 40px; }}
            h1 {{ color: #ffffff; margin-bottom: 5px; }}
            .card {{ background-color: #1e1e1e; border-radius: 8px; padding: 25px; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ padding: 10px; border-bottom: 2px solid #444; color: #888; }}
        </style>
    </head>
    <body>
        <h1>Savisor Orchestrator Gateway</h1>
        <p style="color:#888; margin: 0;">Central control room for trading sessions, RDP wrappers, and local network routes</p>
        <div class="card">
            <h2>Active Trader Nodes</h2>
            <table>
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Organization</th>
                        <th>API Port Mapping</th>
                        <th>RDP Profile Location</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return html

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
