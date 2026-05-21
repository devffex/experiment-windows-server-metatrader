from pydantic import BaseModel, Field
from typing import Optional, List

# --- Provisioning Schemas (used by orchestrator) ---
class ProvisionRequest(BaseModel):
    organization: str = Field(..., description="Name of the organization (e.g., savisor)")
    trader_name: str = Field(..., description="Name of the trader (e.g., julio, luis, john)")

class ProvisionResponse(BaseModel):
    status: str = Field(..., description="Provisioning outcome status (success / error)")
    message: str = Field(..., description="Descriptive execution message")
    port: int = Field(..., description="Allocated user session API loopback port")
    password: str = Field(..., description="Securely generated user password")
    rdp_profile: str = Field(..., description="Absolute file path of the generated .rdp file")


# --- Trading & Calculations Schemas ---
class OrderRequest(BaseModel):
    symbol: str = Field(..., description="Asset symbol (e.g. EURUSD)")
    volume: float = Field(..., description="Trade volume in lots (e.g. 0.1)")
    action: str = Field(..., description="Action type: BUY or SELL")
    price: Optional[float] = Field(None, description="Execution price (optional)")
    sl: Optional[float] = Field(None, description="Stop Loss limit price (optional)")
    tp: Optional[float] = Field(None, description="Take Profit limit price (optional)")

class OrderResponse(BaseModel):
    ticket: int = Field(..., description="Unique trade ticket number")
    retcode: int = Field(..., description="MT5 transaction return code")
    price: float = Field(..., description="Execution deal price")
    volume: float = Field(..., description="Executed volume")
    comment: str = Field(..., description="Order comment or error description")
    request_id: str = Field(..., description="Request identifier")

class OrderCheckResponse(BaseModel):
    retcode: int
    balance: float
    equity: float
    profit: float
    margin: float
    margin_free: float
    margin_level: float
    comment: str

class OrderCalcProfitResponse(BaseModel):
    profit: float = Field(..., description="Estimated profit in account currency")

class OrderCalcMarginResponse(BaseModel):
    margin: float = Field(..., description="Estimated margin needed in account currency")


# --- Positions & Orders Schemas ---
class PositionInfo(BaseModel):
    ticket: int
    symbol: str
    volume: float
    price_open: float
    profit: float
    comment: str
    time: int

class PositionsResponse(BaseModel):
    positions: List[PositionInfo]

class PositionsTotalResponse(BaseModel):
    total: int

class OrderInfo(BaseModel):
    ticket: int
    time_setup: int
    type: int
    state: int
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    symbol: str
    comment: str

class OrdersGetResponse(BaseModel):
    orders: List[OrderInfo]

class OrdersTotalResponse(BaseModel):
    total: int


# --- Account & Terminal Status Schemas ---
class AccountInfo(BaseModel):
    login: int
    trade_mode: int
    leverage: int
    limit_orders: int
    margin_so_mode: int
    trade_allowed: bool
    trade_expert: bool
    margin_mode: int
    currency_digits: int
    fifo_close: bool
    balance: float
    credit: float
    profit: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float
    margin_so_call: float
    margin_so_so: float
    margin_initial: float
    margin_maintenance: float
    assets: float
    liabilities: float
    commission_blocked: float
    name: str
    server: str
    currency: str
    company: str

class TerminalInfo(BaseModel):
    community_account: bool
    community_connection: bool
    connected: bool
    dlls_allowed: bool
    trade_allowed: bool
    tradeapi_disabled: bool
    email_enabled: bool
    ftp_enabled: bool
    notifications_enabled: bool
    mqid: bool
    build: int
    maxbars: int
    codepage: int
    ping_last: int
    community_balance: float
    retransmission: float
    company: str
    name: str
    language: str
    path: str
    data_path: str
    commondata_path: str

class VersionResponse(BaseModel):
    version: int
    build: int
    release_date: str

class LastErrorResponse(BaseModel):
    code: int
    description: str


# --- Historical Data Schemas ---
class DealInfo(BaseModel):
    ticket: int
    order: int
    time: int
    time_msc: int
    type: int
    entry: int
    magic: int
    position_id: int
    reason: int
    volume: float
    price: float
    commission: float
    swap: float
    profit: float
    fee: float
    symbol: str
    comment: str
    external_id: str

class HistoryDealsRequest(BaseModel):
    date_from: Optional[int] = None
    date_to: Optional[int] = None
    group: Optional[str] = None
    ticket: Optional[int] = None
    position: Optional[int] = None

class HistoryDealsResponse(BaseModel):
    deals: List[DealInfo]

class HistoryDealsTotalRequest(BaseModel):
    date_from: int
    date_to: int

class HistoryDealsTotalResponse(BaseModel):
    total: int

class HistoryOrdersRequest(BaseModel):
    date_from: Optional[int] = None
    date_to: Optional[int] = None
    group: Optional[str] = None
    ticket: Optional[int] = None
    position: Optional[int] = None

class HistoryOrdersResponse(BaseModel):
    orders: List[OrderInfo]

class HistoryOrdersTotalRequest(BaseModel):
    date_from: int
    date_to: int

class HistoryOrdersTotalResponse(BaseModel):
    total: int


# --- Market Data & OHLCV Schemas ---
class TickResponse(BaseModel):
    time: int
    bid: float
    ask: float
    last: float
    volume: int
    time_msc: int
    flags: int
    volume_real: float

class CopyTicksRangeRequest(BaseModel):
    symbol: str
    date_from: int
    date_to: int
    flags: int

class CopyTicksFromRequest(BaseModel):
    symbol: str
    date_from: int
    count: int
    flags: int

class CopyTicksResponse(BaseModel):
    ticks: List[TickResponse]

class RateResponse(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

class CopyRatesRangeRequest(BaseModel):
    symbol: str
    timeframe: int
    date_from: int
    date_to: int

class CopyRatesFromRequest(BaseModel):
    symbol: str
    timeframe: int
    date_from: int
    count: int

class CopyRatesFromPosRequest(BaseModel):
    symbol: str
    timeframe: int
    start_pos: int
    count: int

class CopyRatesResponse(BaseModel):
    rates: List[RateResponse]


# --- Market Book & Order Book (DOM) Schemas ---
class MarketBookRequest(BaseModel):
    symbol: str

class BookInfo(BaseModel):
    type: int
    price: float
    volume: int
    volume_dbl: float

class MarketBookGetResponse(BaseModel):
    items: List[BookInfo]

class MarketBookActionResponse(BaseModel):
    success: bool


# --- Symbol Management Schemas ---
class SymbolSelectRequest(BaseModel):
    symbol: str
    enable: Optional[bool] = None

class SymbolSelectResponse(BaseModel):
    success: bool

class SymbolInfoRequest(BaseModel):
    symbol: str

class SymbolInfoResponse(BaseModel):
    custom: bool
    spread_float: bool
    margin_hedged_use_leg: bool
    chart_mode: int
    select: bool
    visible: bool
    session_deals: int
    session_buy_orders: int
    session_sell_orders: int
    volume: int
    volumehigh: int
    volumelow: int
    time: int
    digits: int
    spread: int
    ticks_bookdepth: int
    trade_calc_mode: int
    trade_mode: int
    start_time: int
    expiration_time: int
    trade_stops_level: int
    trade_freeze_level: int
    trade_exemode: int
    swap_mode: int
    swap_rollover3days: int
    expiration_mode: int
    filling_mode: int
    order_mode: int
    order_gtc_mode: int
    option_mode: int
    option_right: int
    bid: float
    bidhigh: float
    bidlow: float
    ask: float
    askhigh: float
    asklow: float
    last: float
    lasthigh: float
    lastlow: float
    volume_real: float
    volumehigh_real: float
    volumelow_real: float
    option_strike: float
    point: float
    trade_tick_value: float
    trade_tick_value_profit: float
    trade_tick_value_loss: float
    trade_tick_size: float
    trade_contract_size: float
    trade_accrued_interest: float
    trade_face_value: float
    trade_liquidity_rate: float
    volume_min: float
    volume_max: float
    volume_step: float
    volume_limit: float
    swap_long: float
    swap_short: float
    margin_initial: float
    margin_maintenance: float
    session_volume: float
    session_turnover: float
    session_interest: float
    session_buy_orders_volume: float
    session_sell_orders_volume: float
    session_open: float
    session_close: float
    session_aw: float
    session_price_settlement: float
    session_price_limit_min: float
    session_price_limit_max: float
    margin_hedged: float
    price_change: float
    price_volatility: float
    price_theoretical: float
    price_greeks_delta: float
    price_greeks_theta: float
    price_greeks_gamma: float
    price_greeks_vega: float
    price_greeks_rho: float
    price_greeks_omega: float
    price_sensitivity: float
    basis: str
    category: str
    currency_base: str
    currency_profit: str
    currency_margin: str
    bank: str
    description: str
    exchange: str
    formula: str
    isin: str
    name: str
    page: str
    path: str

class SymbolInfoTickRequest(BaseModel):
    symbol: str

class SymbolsGetResponse(BaseModel):
    symbols: List[SymbolInfoResponse]

class SymbolsTotalResponse(BaseModel):
    total: int


# --- Orchestrator Management Schemas ---
class TraderStatus(BaseModel):
    username: str = Field(..., description="Windows username (e.g. savisor-julio)")
    organization: str = Field(..., description="Organization name")
    trader_name: str = Field(..., description="Trader name")
    port: int = Field(..., description="Allocated loopback port")
    rdp_profile: str = Field(..., description="Path to the .rdp connection file")
    session_online: bool = Field(..., description="Whether the session-wrapper API is reachable")
    health: Optional[dict] = Field(None, description="Health data from session-wrapper if online")

class TraderListResponse(BaseModel):
    traders: List[TraderStatus]

class DeprovisionResponse(BaseModel):
    status: str = Field(..., description="Deprovisioning outcome (success / error)")
    message: str = Field(..., description="Descriptive message")
