from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from orchestrator.store import TraderStore

router = APIRouter(tags=["dashboard"])

DASHBOARD_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background-color: #0a0a0a;
    color: #e0e0e0;
    margin: 0;
    padding: 40px;
}
h1 { color: #ffffff; margin-bottom: 5px; }
.subtitle { color: #888; margin: 0 0 30px 0; }
.card {
    background-color: #141414;
    border: 1px solid #1e1e1e;
    border-radius: 12px;
    padding: 28px;
    margin-top: 20px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
}
table { width: 100%; border-collapse: collapse; text-align: left; }
th {
    padding: 12px 10px;
    border-bottom: 2px solid #2a2a2a;
    color: #666;
    font-size: 0.8em;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
td { padding: 12px 10px; border-bottom: 1px solid #1a1a1a; }
code {
    background: #1a1a1a;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 0.9em;
    color: #a78bfa;
}
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.75em;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-online {
    background-color: rgba(34, 197, 94, 0.15);
    color: #22c55e;
    border: 1px solid rgba(34, 197, 94, 0.3);
}
.badge-offline {
    background-color: rgba(239, 68, 68, 0.15);
    color: #ef4444;
    border: 1px solid rgba(239, 68, 68, 0.3);
}
.empty-state {
    padding: 40px;
    text-align: center;
    color: #555;
    font-style: italic;
}
"""


def _get_store(request: Request) -> TraderStore:
    return request.app.state.store


@router.get("/", response_class=HTMLResponse)
async def index_dashboard(request: Request):
    """Renders the admin dashboard showing provisioned traders and their live status."""
    store = _get_store(request)
    gateway = request.app.state.gateway
    mappings = await store.load()

    rows = ""
    for username, mapping in mappings.items():
        health = await gateway.check_health(mapping.port)
        online = health is not None

        status_badge = (
            '<span class="badge badge-online">● Online</span>'
            if online
            else '<span class="badge badge-offline">● Offline</span>'
        )

        pid_display = ""
        if health and "pid" in health:
            pid_display = f'<code>{health["pid"]}</code>'
        else:
            pid_display = '<span style="color:#555">—</span>'

        rows += f"""
        <tr>
            <td><strong>{username}</strong></td>
            <td>{mapping.organization}</td>
            <td><code>{mapping.port}</code></td>
            <td>{status_badge}</td>
            <td>{pid_display}</td>
            <td><code style="font-size:0.8em">{mapping.rdp_profile}</code></td>
        </tr>
        """

    if not rows:
        rows = (
            '<tr><td colspan="6" class="empty-state">'
            "No traders provisioned yet. Use POST /provision to get started."
            "</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Savisor Orchestrator Gateway</title>
    <style>{DASHBOARD_CSS}</style>
</head>
<body>
    <h1>Savisor Orchestrator Gateway</h1>
    <p class="subtitle">Central control room for trading sessions, RDP wrappers, and local network routes</p>
    <div class="card">
        <h2 style="margin-top:0; color:#ccc;">Active Trader Nodes</h2>
        <table>
            <thead>
                <tr>
                    <th>Username</th>
                    <th>Organization</th>
                    <th>API Port</th>
                    <th>Session</th>
                    <th>PID</th>
                    <th>RDP Profile</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)
