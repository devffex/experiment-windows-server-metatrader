from pydantic import BaseModel, Field
from typing import Optional, List

class LoginRequest(BaseModel):
    login: int = Field(..., description="MetaTrader account login number")
    password: str = Field(..., description="MetaTrader password")
    server: str = Field(..., description="Broker server name")

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

class AccountInfo(BaseModel):
    login: int
    balance: float
    equity: float
    margin: float
    leverage: int
    currency: str
    server: str

class ProvisionRequest(BaseModel):
    organization: str = Field(..., description="Name of the organization (e.g., savisor)")
    trader_name: str = Field(..., description="Name of the trader (e.g., julio, luis, john)")

class ProvisionResponse(BaseModel):
    status: str = Field(..., description="Provisioning outcome status (success / error)")
    message: str = Field(..., description="Descriptive execution message")
    port: int = Field(..., description="Allocated user session API loopback port")
    password: str = Field(..., description="Securely generated user password")
    rdp_profile: str = Field(..., description="Absolute file path of the generated .rdp file")
