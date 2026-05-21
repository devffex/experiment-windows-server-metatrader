# Savisor MetaTrader Hub CLI Client

The **Savisor MetaTrader Hub CLI** (`savisor-mt`) is a premium, high-fidelity administrative terminal and quant operator workstation built in Python using **Typer** and **Rich**. 

It interfaces directly with the central **Orchestrator** and routes trading actions to isolated remote MT5 sessions using the **API Gateway Router**.

---

## Technical Stack
*   **CLI Parsing & Autocomplete:** [Typer](https://typer.tiangolo.com/)
*   **Visual Terminals & Color Hud:** [Rich](https://rich.readthedocs.io/)
*   **Networking:** [HTTPX](https://www.python-httpx.org/) (Synchronous mode)
*   **Workspace Schemas:** Reuses shared structures from `packages/shared-schemas` directly.

---

## Installation & Setup

Ensure you are inside the monorepo root directory and run the sync command to discover the new CLI app package:

```bash
# Sync monorepo workspaces and lockfile
uv sync
```

---

## CLI Command Reference

### Global Callback Flags
*   `--url` / `-u`: Central Orchestrator URL. Defaults to `http://localhost:8000` (or reads environment variable `SAVISOR_ORCHESTRATOR_URL`).

---

### 1. Administration Commands (`savisor-mt admin ...`)

#### A. Server Status Check
Pings and validates connection status with the Central Orchestrator:
```bash
uv run --package cli-client savisor-mt admin status
```

#### B. Active Node List
Retrieves a colorful grid list showing registered windows users, ports, session status, wrapper PID, and the local RDP configuration paths:
```bash
uv run --package cli-client savisor-mt admin list
```

#### C. Provision Trader Session
Creates a new Windows User, builds their isolated MT5 directory sandbox, mounts offline registry shell overrides, compiles RDP configurations, and spins up local loopback wrappers:
```bash
uv run --package cli-client savisor-mt admin provision --org savisor --name john
```

#### D. Deprovision Node
Prompts for explicit confirmation before logging off RDP profiles, deleting Windows user, and wiping filesystem sandbox:
```bash
uv run --package cli-client savisor-mt admin deprovision savisor-john
```

---

### 2. Trading Workstation Commands (`savisor-mt trade ...`)

All trading commands require specifying the target trader name via the global group option `--trader` (or `-t`).

#### A. Retrieve Live Account HUD
Fetches balance, equity, margin ratios, and live floating profit/loss for a trader:
```bash
uv run --package cli-client savisor-mt trade --trader john account
```

#### B. Open Positions Table
Renders all active positions with tickets, lots, prices, and live color-coded floating P&L:
```bash
uv run --package cli-client savisor-mt trade --trader john positions
```

#### C. Pending Orders list
Shows active limit and stop orders:
```bash
uv run --package cli-client savisor-mt trade --trader john orders
```

#### D. Pre-Flight Margin Check
Evaluates account sufficiency and broker commission constraints before execution:
```bash
uv run --package cli-client savisor-mt trade --trader john check EURUSD 0.1 BUY
```

#### E. Execute Broker Trade Deal
Places live buy/sell orders. Automatically prompts for operator confirmation before deal submission:
```bash
uv run --package cli-client savisor-mt trade --trader john execute EURUSD 0.1 BUY --sl 1.0850 --tp 1.1150
```

#### F. Close Active Trade Position
Automatically resolves and sends opposite transaction to close out a specific position ticket:
```bash
uv run --package cli-client savisor-mt trade --trader john close 987654
```

#### G. Closed Deals Logs
Extracts historical transactions and computes realized P&L calculations over a designated timeframe:
```bash
uv run --package cli-client savisor-mt trade --trader john history --days 14
```
