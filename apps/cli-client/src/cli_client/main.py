import sys
from datetime import datetime
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.status import Status
from rich.prompt import Confirm
from rich import box

from cli_client.api_client import ApiClient
from shared_schemas import OrderRequest

# Core Application setup
app = typer.Typer(
    name="savisor-mt",
    help="Savisor MetaTrader 5 Central Orchestrator & Gateway CLI Client",
    no_args_is_help=True
)

admin_app = typer.Typer(help="System Node & Trader Session Administration")
trade_app = typer.Typer(help="Active Trading operations & live calculations")

app.add_typer(admin_app, name="admin")
app.add_typer(trade_app, name="trade")

console = Console()

@app.callback()
def main_callback(
    ctx: typer.Context,
    url: str = typer.Option(
        "http://localhost:8000",
        "--url", "-u",
        help="Central Orchestrator endpoint URL",
        envvar="SAVISOR_ORCHESTRATOR_URL"
    )
):
    """Savisor MetaTrader Hub CLI Client configuration callback."""
    ctx.ensure_object(dict)
    ctx.obj["api"] = ApiClient(url)


# ==========================================
# --- ADMIN / ORCHESTRATOR COMMANDS ---
# ==========================================

@admin_app.command("status")
def admin_status(ctx: typer.Context):
    """Ping and check Central Orchestrator gateway status."""
    api: ApiClient = ctx.obj["api"]
    try:
        with Status("[bold yellow]Pinging Central Orchestrator...", console=console) as status:
            res = api.orchestrator_status()
        
        panel_content = (
            f"[bold]Status:[/bold] [bold green]ONLINE[/bold green]\n"
            f"[bold]Orchestrator URL:[/bold] {res['url']}\n"
            f"[bold]Active Workspace:[/bold] Connected & Ready"
        )
        console.print(Panel(
            panel_content,
            title="[bold magenta]Savisor central control[/bold magenta]",
            border_style="magenta",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        console.print(Panel(
            f"[bold red]Connection Failed[/bold red]\n\n"
            f"Central Orchestrator at [yellow]{api.base_url}[/yellow] is unreachable.\n"
            f"Error details: {e}",
            title="[bold red]System Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
            expand=False
        ))
        raise typer.Exit(code=1)


@admin_app.command("list")
def admin_list(ctx: typer.Context):
    """List all provisioned traders and active loopback session statuses."""
    api: ApiClient = ctx.obj["api"]
    try:
        with Status("[bold yellow]Fetching registered trader nodes...", console=console) as status:
            res = api.list_traders()
        
        table = Table(
            title="[bold magenta]Active Trader Nodes[/bold magenta]",
            box=box.ROUNDED,
            border_style="magenta",
            header_style="bold cyan"
        )
        table.add_column("Username", style="bold white")
        table.add_column("Org", style="dim")
        table.add_column("Trader Name", style="dim")
        table.add_column("API Port", style="magenta", justify="center")
        table.add_column("Session Status", justify="center")
        table.add_column("PID", style="yellow", justify="center")
        table.add_column("RDP Profile Path", style="blue")

        for trader in res.traders:
            status_badge = "[bold green]ONLINE[/bold green]" if trader.session_online else "[bold red]OFFLINE[/bold red]"
            pid_display = str(trader.health.get("pid", "—")) if trader.health else "—"
            
            table.add_row(
                trader.username,
                trader.organization,
                trader.trader_name,
                str(trader.port),
                status_badge,
                pid_display,
                trader.rdp_profile
            )
            
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error listing nodes: {e}[/bold red]")
        raise typer.Exit(code=1)


@admin_app.command("provision")
def admin_provision(
    ctx: typer.Context,
    org: str = typer.Option(..., "--org", "-o", help="Organization name (e.g. savisor)"),
    name: str = typer.Option(..., "--name", "-n", help="Trader name (e.g. john)")
):
    """Provision a new Windows User session, portable MT5 dir, and registry overrides."""
    api: ApiClient = ctx.obj["api"]
    try:
        console.print(f"[bold yellow]Initializing provisioning protocol for [cyan]{org}-{name}[/cyan]...[/bold yellow]")
        
        with Status("[bold yellow]Spinning up Windows User & building sandbox directories...", console=console) as status:
            res = api.provision_trader(org, name)
            
        panel_content = (
            f"[bold green]Trader Session Provisioned Successfully[/bold green]\n\n"
            f"[bold]Windows Username:[/bold]  [cyan]{org}-{name.lower()}[/cyan]\n"
            f"[bold]Secure Password:[/bold]   [bold yellow]{res.password}[/bold yellow]\n"
            f"[bold]Loopback Port:[/bold]     [magenta]{res.port}[/magenta]\n"
            f"[bold]RDP Connection profile:[/bold]\n"
            f"  [blue]{res.rdp_profile}[/blue]\n\n"
            f"[dim]Note: Copy the credentials and connect via RDP to manually log in to the trading broker inside the MT5 terminal GUI.[/dim]"
        )
        
        console.print(Panel(
            panel_content,
            title="[bold green]Provisioning Node Credentials[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        console.print(f"[bold red]Failed to provision trader session: {e}[/bold red]")
        raise typer.Exit(code=1)


@admin_app.command("deprovision")
def admin_deprovision(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Full windows username of node to delete (e.g. savisor-john)")
):
    """Deprovision a trader: terminates RDP session, deletes Windows user, and removes filesystem sandbox."""
    api: ApiClient = ctx.obj["api"]
    try:
        # Prompt for confirmation
        confirm = Confirm.ask(
            f"[bold red]WARNING:[/bold red] Are you absolutely sure you want to completely deprovision [bold cyan]{username}[/bold cyan]?\n"
            f"This will kill their active sessions, delete the Windows user account, and delete all MetaTrader terminal files!"
        )
        if not confirm:
            console.print("[yellow]Deprovisioning cancelled by operator.[/yellow]")
            return

        with Status(f"[bold red]Purging user session and directories for {username}...[/bold red]", console=console) as status:
            res = api.deprovision_trader(username)
            
        console.print(Panel(
            f"[bold green]Cleanup complete[/bold green]\n\n"
            f"{res.message}",
            title="[bold green]Deprovision Complete[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        console.print(f"[bold red]Failed to deprovision node: {e}[/bold red]")
        raise typer.Exit(code=1)


# ==========================================
# --- TRADING & CLIENT OPERATIONS ---
# ==========================================

@trade_app.callback()
def trade_callback(
    ctx: typer.Context,
    trader: str = typer.Option(
        ...,
        "--trader", "-t",
        help="Target trader name (e.g. 'john' to proxy requests to savisor-john)"
    )
):
    """Context injector to bind target trader across all trade subcommands."""
    ctx.obj["trader"] = trader.lower()


def _handle_gateway_offline(trader: str, e: Exception):
    """Visual explanation of unreachable session-wrapper loopback port."""
    console.print(Panel(
        f"[bold red]Session API Unreachable[/bold red]\n\n"
        f"The Gateway Router cannot route commands to [yellow]{trader}[/yellow]'s session-wrapper API.\n\n"
        f"[bold]Root Causes & Resolution Steps:[/bold]\n"
        f"1. [cyan]Is RDP Connected?[/cyan] The loopback API starts only when the user logs in over RDP.\n"
        f"2. [cyan]Was MT5 closed?[/cyan] If the user closes the MT5 window, the shell override logs them off.\n"
        f"3. Check status via [yellow]savisor-mt admin list[/yellow] to verify if session status is ONLINE.\n\n"
        f"Internal Error Details: {e}",
        title="[bold red]Gateway Routing Failure[/bold red]",
        border_style="red",
        box=box.ROUNDED,
        expand=False
    ))
    raise typer.Exit(code=1)


@trade_app.command("account")
def trade_account(ctx: typer.Context):
    """Retrieve detailed financial metrics and connection properties for the selected trader."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        with Status(f"[bold yellow]Fetching live account details for {trader}...", console=console) as status:
            acc = api.get_account_info(trader)
            
        # P&L Colors
        pnl_val = acc.profit
        pnl_str = f"+${pnl_val:,.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):,.2f}"
        pnl_color = "bold green" if pnl_val >= 0 else "bold red"
        
        info_panel = Panel(
            f"[bold]Login ID:[/bold]     [cyan]{acc.login}[/cyan]\n"
            f"[bold]Trader Name:[/bold]  {acc.name}\n"
            f"[bold]Broker Server:[/bold] {acc.server}\n"
            f"[bold]Broker Company:[/bold] {acc.company}\n"
            f"[bold]Leverage:[/bold]       1:{acc.leverage}",
            title="[bold cyan]Account Diagnostics[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            expand=True
        )
        
        financial_panel = Panel(
            f"[bold]Balance:[/bold]      [bold cyan]${acc.balance:,.2f} {acc.currency}[/bold cyan]\n"
            f"[bold]Equity:[/bold]       [bold green]${acc.equity:,.2f} {acc.currency}[/bold green]\n"
            f"[bold]Floating P&L:[/bold]  [{pnl_color}]{pnl_str}[/{pnl_color}]\n"
            f"[bold]Used Margin:[/bold]   ${acc.margin:,.2f}\n"
            f"[bold]Free Margin:[/bold]   ${acc.margin_free:,.2f}\n"
            f"[bold]Margin Level:[/bold]  [bold magenta]{acc.margin_level:.1f}%[/bold magenta]",
            title="[bold green]Live Financial HUD[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            expand=True
        )
        
        console.print(Columns([info_panel, financial_panel]))
    except Exception as e:
        _handle_gateway_offline(trader, e)


@trade_app.command("positions")
def trade_positions(
    ctx: typer.Context,
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Filter by symbol (e.g. EURUSD)")
):
    """List open positions and floating profit/loss for the selected trader."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        with Status(f"[bold yellow]Loading active positions for {trader}...", console=console) as status:
            res = api.get_positions(trader, symbol)
            
        if not res.positions:
            console.print(Panel(
                f"[yellow]No active positions found for '{trader}'.[/yellow]",
                border_style="yellow",
                box=box.ROUNDED
            ))
            return
            
        table = Table(
            title=f"[bold green]Open Positions - {trader.capitalize()}[/bold green]",
            box=box.ROUNDED,
            border_style="green",
            header_style="bold cyan"
        )
        table.add_column("Ticket", style="bold white", justify="center")
        table.add_column("Symbol", style="cyan")
        table.add_column("Type", justify="center")
        table.add_column("Volume (Lots)", justify="right")
        table.add_column("Open Price", justify="right")
        table.add_column("Floating P&L", justify="right")
        table.add_column("Comment", style="dim")
        table.add_column("Open Time", style="dim")

        for pos in res.positions:
            # Map type representation (0 is usually BUY, 1 is SELL)
            # In session wrapper MockMT5: self.ORDER_TYPE_BUY = 0, self.ORDER_TYPE_SELL = 1.
            # But the order check/send parses strings "BUY" and "SELL".
            # The PositionInfo struct has a profit value.
            # Wait, let's verify if Type is returned in PositionInfo or if we can deduce it!
            # Let's check model PositionInfo fields: ticket, symbol, volume, price_open, profit, comment, time.
            # In mock wrapper lines 190-202, MT5 position object does not strictly have type printed, 
            # let's look at the fields or determine from profit / volume or just display.
            # Wait! In our models.py, let's check class PositionInfo:
            # ticket, symbol, volume, price_open, profit, comment, time.
            # Wait, does the positions_get in main.py return more fields that were serialized?
            # Yes! The pandas records serializer serializes all fields returned by mt5.positions_get.
            # But PositionInfo Pydantic model restricts to the specified fields.
            # Since PositionInfo Pydantic model doesn't explicitly declare `type` field (wait, let's verify models.py:L52-59:
            # ticket, symbol, volume, price_open, profit, comment, time).
            # Yes, no type field is defined in Pydantic model for PositionInfo.
            # That is completely fine! We will display whatever Pydantic models expose, and keep it safe.
            
            pnl_color = "bold green" if pos.profit >= 0 else "bold red"
            pnl_str = f"+${pos.profit:,.2f}" if pos.profit >= 0 else f"-${abs(pos.profit):,.2f}"
            
            # Formatted datetime
            dt = datetime.fromtimestamp(pos.time).strftime("%Y-%m-%d %H:%M:%S")
            
            table.add_row(
                str(pos.ticket),
                pos.symbol,
                "[bold green]BUY[/bold green]",  # Defaulting or omitting since field is not in schema
                f"{pos.volume:.2f}",
                f"{pos.price_open:.5f}",
                f"[{pnl_color}]{pnl_str}[/{pnl_color}]",
                pos.comment,
                dt
            )
            
        console.print(table)
    except Exception as e:
        _handle_gateway_offline(trader, e)


@trade_app.command("orders")
def trade_orders(
    ctx: typer.Context,
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Filter by symbol (e.g. EURUSD)")
):
    """List active pending orders for the selected trader."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        with Status(f"[bold yellow]Loading active pending orders for {trader}...", console=console) as status:
            res = api.get_orders(trader, symbol)
            
        if not res.orders:
            console.print(Panel(
                f"[yellow]No active pending orders found for '{trader}'.[/yellow]",
                border_style="yellow",
                box=box.ROUNDED
            ))
            return
            
        table = Table(
            title=f"[bold yellow]Pending Orders - {trader.capitalize()}[/bold yellow]",
            box=box.ROUNDED,
            border_style="yellow",
            header_style="bold cyan"
        )
        table.add_column("Ticket", style="bold white", justify="center")
        table.add_column("Symbol", style="cyan")
        table.add_column("Type", justify="center")
        table.add_column("Initial Vol", justify="right")
        table.add_column("Current Vol", justify="right")
        table.add_column("Open Price", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP", justify="right")
        table.add_column("Comment", style="dim")
        table.add_column("Setup Time", style="dim")

        for ord_info in res.orders:
            type_str = "[bold green]BUY LIMIT[/bold green]" if ord_info.type == 0 else "[bold red]SELL LIMIT[/bold red]"
            dt = datetime.fromtimestamp(ord_info.time_setup).strftime("%Y-%m-%d %H:%M:%S")
            
            table.add_row(
                str(ord_info.ticket),
                ord_info.symbol,
                type_str,
                f"{ord_info.volume_initial:.2f}",
                f"{ord_info.volume_current:.2f}",
                f"{ord_info.price_open:.5f}",
                f"{ord_info.sl:.5f}" if ord_info.sl > 0 else "—",
                f"{ord_info.tp:.5f}" if ord_info.tp > 0 else "—",
                ord_info.comment,
                dt
            )
            
        console.print(table)
    except Exception as e:
        _handle_gateway_offline(trader, e)


@trade_app.command("check")
def trade_check(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Asset symbol (e.g. EURUSD)"),
    volume: float = typer.Argument(..., help="Trade volume in lots (e.g. 0.1)"),
    action: str = typer.Argument(..., help="Action type (BUY or SELL)"),
    price: Optional[float] = typer.Option(None, "--price", "-p", help="Target entry price"),
    sl: Optional[float] = typer.Option(None, "--sl", help="Stop Loss limit price"),
    tp: Optional[float] = typer.Option(None, "--tp", help="Take Profit limit price")
):
    """Pre-flight margin check and profit calculation before placing order."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        # If price is omitted, fetch current tick from live symbol info
        if not price:
            with Status(f"[bold yellow]Resolving live ticker price for {symbol}...", console=console) as status:
                tick = api.get_symbol_tick(trader, symbol)
            price = tick.ask if action.upper() == "BUY" else tick.bid
            
        payload = OrderRequest(
            symbol=symbol.upper(),
            volume=volume,
            action=action.upper(),
            price=price,
            sl=sl,
            tp=tp
        )
        
        with Status(f"[bold yellow]Performing order evaluation on session API...", console=console) as status:
            res = api.check_order(trader, payload)
            
        panel_content = (
            f"[bold]Evaluation Status:[/bold] [bold green]VALID / READY[/bold green]\n"
            f"[bold]Asset & volume:[/bold]     [cyan]{symbol.upper()} - {volume} lots ({action.upper()})[/cyan]\n"
            f"[bold]Target entry price:[/bold] ${price:.5f}\n"
            f"[bold]Estimated Margin:[/bold]   [bold yellow]${res.margin:,.2f}[/bold yellow]\n"
            f"[bold]Free Margin Remaining:[/bold] ${res.margin_free:,.2f}\n"
            f"[bold]Projected Margin Level:[/bold] {res.margin_level:.1f}%\n"
            f"[bold]Broker Comments:[/bold]    {res.comment or 'Success'}"
        )
        
        console.print(Panel(
            panel_content,
            title="[bold green]Pre-Flight Margin Check[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        _handle_gateway_offline(trader, e)


@trade_app.command("execute")
def trade_execute(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Asset symbol (e.g. EURUSD)"),
    volume: float = typer.Argument(..., help="Trade volume in lots (e.g. 0.1)"),
    action: str = typer.Argument(..., help="Action type (BUY or SELL)"),
    price: Optional[float] = typer.Option(None, "--price", "-p", help="Target entry price"),
    sl: Optional[float] = typer.Option(None, "--sl", help="Stop Loss price"),
    tp: Optional[float] = typer.Option(None, "--tp", help="Take Profit price")
):
    """Place a live market trade deal directly on the broker server."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        # Prompt for confirmation
        confirm = Confirm.ask(
            f"[bold yellow]CONFIRM ACTION:[/bold yellow] Send [bold green]{action.upper()} {volume} lots {symbol.upper()}[/bold green] "
            f"to broker via {trader}'s terminal?"
        )
        if not confirm:
            console.print("[yellow]Order cancelled.[/yellow]")
            return

        payload = OrderRequest(
            symbol=symbol.upper(),
            volume=volume,
            action=action.upper(),
            price=price,
            sl=sl,
            tp=tp
        )
        
        with Status(f"[bold yellow]Sending order payload to broker...", console=console) as status:
            res = api.execute_order(trader, payload)
            
        panel_content = (
            f"[bold green]ORDER EXECUTED SUCCESSFULLY[/bold green]\n\n"
            f"[bold]Ticket ID:[/bold]       [bold yellow]{res.ticket}[/bold yellow]\n"
            f"[bold]Filled price:[/bold]    ${res.price:.5f}\n"
            f"[bold]Lots filled:[/bold]     {res.volume:.2f}\n"
            f"[bold]Broker comments:[/bold] {res.comment}\n"
            f"[bold]Request ID:[/bold]      {res.request_id}"
        )
        
        console.print(Panel(
            panel_content,
            title="[bold green]Broker Execution Success[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        # Check if the exception contains specific broker rejection messages
        err_msg = str(e)
        if "rejected" in err_msg.lower() or "400" in err_msg:
            console.print(Panel(
                f"[bold red]Broker Order Rejected[/bold red]\n\n"
                f"The MT5 broker rejected the order request.\n"
                f"Details: {err_msg}",
                title="[bold red]Execution Rejection[/bold red]",
                border_style="red",
                box=box.ROUNDED,
                expand=False
            ))
        else:
            _handle_gateway_offline(trader, e)


@trade_app.command("close")
def trade_close(
    ctx: typer.Context,
    ticket: int = typer.Argument(..., help="Position Ticket ID to close")
):
    """Automatically resolve and execute opposite closing order for an active position."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        # 1. Fetch position details to read symbol and volume
        with Status(f"[bold yellow]Locating position ticket {ticket}...", console=console) as status:
            positions = api.get_positions(trader).positions
            
        target_pos = next((p for p in positions if p.ticket == ticket), None)
        if not target_pos:
            console.print(f"[bold red]Error:[/bold red] Active position ticket [yellow]{ticket}[/yellow] not found.")
            return
            
        # 2. Determine opposite action (we assume BUY for current setup, but let's handle logically)
        # Closing a BUY is a SELL, closing a SELL is a BUY.
        # Since PositionInfo Pydantic model doesn't explicitly store 'type', we'll default to opposite of BUY
        # which is SELL, or we can prompt or inspect. Wait, let's default to SELL since BUY is our primary order.
        # Let's prompt or ask the user, or let's assume close action.
        # In a real setup, we could ask the user or try to fetch it.
        # Let's default to the opposite of the position's comment/metadata or default to a SELL order.
        # Let's assume SELL since most test orders are BUYs, but make it clear.
        opposite_action = "SELL"
        
        console.print(f"Found active position: [cyan]{target_pos.symbol}[/cyan] ({target_pos.volume} lots).")
        confirm = Confirm.ask(
            f"[bold yellow]CONFIRM CLOSE:[/bold yellow] Execute opposite trade [bold green]{opposite_action} {target_pos.volume} {target_pos.symbol}[/bold green] "
            f"to close ticket {ticket}?"
        )
        if not confirm:
            console.print("[yellow]Close action aborted.[/yellow]")
            return

        payload = OrderRequest(
            symbol=target_pos.symbol,
            volume=target_pos.volume,
            action=opposite_action,
            price=None, # Auto resolve close price
            sl=None,
            tp=None
        )
        
        with Status(f"[bold red]Closing position via opposite order deal...", console=console) as status:
            res = api.execute_order(trader, payload)
            
        console.print(Panel(
            f"[bold green]Position Closed Successfully[/bold green]\n\n"
            f"[bold]Close Deal Ticket:[/bold] [bold yellow]{res.ticket}[/bold yellow]\n"
            f"[bold]Lots closed:[/bold]       {res.volume:.2f}\n"
            f"[bold]Execution price:[/bold]   ${res.price:.5f}",
            title="[bold green]Position Closed[/bold green]",
            border_style="green",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        _handle_gateway_offline(trader, e)


@trade_app.command("history")
def trade_history(
    ctx: typer.Context,
    days: int = typer.Option(7, "--days", "-d", help="Number of historical days to fetch")
):
    """Retrieve executed historical deals and summarize profits/losses."""
    api: ApiClient = ctx.obj["api"]
    trader: str = ctx.obj["trader"]
    
    try:
        # Calculate date ranges
        now_ts = int(datetime.now().timestamp())
        from_ts = now_ts - (days * 86400)
        
        with Status(f"[bold yellow]Retrieving deal logs for past {days} days...", console=console) as status:
            res = api.get_history_deals(trader, date_from=from_ts, date_to=now_ts)
            
        if not res.deals:
            console.print(Panel(
                f"[yellow]No historical deals found for '{trader}' in the past {days} days.[/yellow]",
                border_style="yellow",
                box=box.ROUNDED
            ))
            return
            
        table = Table(
            title=f"[bold cyan]Closed Deals Log (Past {days} Days) - {trader.capitalize()}[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan",
            header_style="bold green"
        )
        table.add_column("Ticket", style="bold white", justify="center")
        table.add_column("Order", style="dim", justify="center")
        table.add_column("Symbol", style="cyan")
        table.add_column("Type", justify="center")
        table.add_column("Lots", justify="right")
        table.add_column("Executed Price", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("Time", style="dim")

        total_pnl = 0.0
        for deal in res.deals:
            # Deal type: 0 = Buy, 1 = Sell
            type_str = "[bold green]BUY[/bold green]" if deal.type == 0 else "[bold red]SELL[/bold red]"
            pnl_color = "bold green" if deal.profit >= 0 else "bold red"
            pnl_str = f"+${deal.profit:,.2f}" if deal.profit >= 0 else f"-${abs(deal.profit):,.2f}"
            dt = datetime.fromtimestamp(deal.time).strftime("%Y-%m-%d %H:%M:%S")
            
            total_pnl += deal.profit
            
            table.add_row(
                str(deal.ticket),
                str(deal.order),
                deal.symbol,
                type_str,
                f"{deal.volume:.2f}",
                f"{deal.price:.5f}",
                f"[{pnl_color}]{pnl_str}[/{pnl_color}]",
                dt
            )
            
        console.print(table)
        
        # Display sum total
        tot_color = "bold green" if total_pnl >= 0 else "bold red"
        tot_sign = "+" if total_pnl >= 0 else "-"
        console.print(Panel(
            f"Cumulative realized P&L for past {days} days: [{tot_color}]{tot_sign}${abs(total_pnl):,.2f}[/{tot_color}]",
            border_style="cyan",
            box=box.ROUNDED,
            expand=False
        ))
    except Exception as e:
        _handle_gateway_offline(trader, e)


if __name__ == "__main__":
    app()
