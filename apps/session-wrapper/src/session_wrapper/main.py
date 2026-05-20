import argparse
import sys
import psutil
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from shared_schemas import (
    LoginRequest,
    OrderRequest,
    OrderResponse,
    PositionInfo,
    PositionsResponse,
    AccountInfo,
)

app = FastAPI(title="Session MT5 loopback API")

# 1. Native MT5 Windows Import with Platform Mock Fallback
try:
    import MetaTrader5 as mt5
except ImportError:
    class MockMT5:
        def __init__(self):
            self.ORDER_TYPE_BUY = 0
            self.ORDER_TYPE_SELL = 1
            self.TRADE_ACTION_DEAL = 1
            self.ORDER_TIME_GTC = 0
            self.ORDER_FILLING_FOK = 0
            self.TRADE_RETCODE_DONE = 10009
            
        def initialize(self, *args, **kwargs):
            return True
            
        def login(self, login, password, server):
            # Simulate auth check
            if login == 999999:
                return False
            return True
            
        def account_info(self):
            class Acc:
                def __init__(self):
                    self.login = 5012345
                    self.balance = 10000.0
                    self.equity = 10000.0
                    self.margin = 0.0
                    self.leverage = 100
                    self.currency = "USD"
                    self.server = "MetaQuotes-Demo"
                def _asdict(self):
                    return {
                        "login": self.login,
                        "balance": self.balance,
                        "equity": self.equity,
                        "margin": self.margin,
                        "leverage": self.leverage,
                        "currency": self.currency,
                        "server": self.server
                    }
            return Acc()

        def symbol_info_tick(self, symbol):
            class Tick:
                def __init__(self):
                    self.ask = 1.1025
                    self.bid = 1.1023
            return Tick()

        def order_send(self, request):
            class OrderResult:
                def __init__(self):
                    self.retcode = 10009
                    self.comment = "Request executed successfully"
                    self.volume = request.get("volume", 0.1)
                    self.price = request.get("price", 1.1025)
                def _asdict(self):
                    return {
                        "ticket": 87654321,
                        "retcode": self.retcode,
                        "price": self.price,
                        "volume": self.volume,
                        "comment": self.comment,
                        "request_id": "req-mock-12345"
                    }
            return OrderResult()

        def positions_get(self, symbol=None):
            class Position:
                def __init__(self):
                    self.ticket = 987654
                    self.symbol = "EURUSD"
                    self.volume = 0.1
                    self.price_open = 1.1025
                    self.profit = 15.50
                    self.comment = "API position"
                    self.time = 1705320000
                def _asdict(self):
                    return {
                        "ticket": self.ticket,
                        "symbol": self.symbol,
                        "volume": self.volume,
                        "price_open": self.price_open,
                        "profit": self.profit,
                        "comment": self.comment,
                        "time": self.time
                    }
            return [Position()]
            
        def shutdown(self):
            pass
            
        def last_error(self):
            return (1, "Success (Mock Mode)")
            
    mt5 = MockMT5()

# 2. API Endpoints Implementation using Shared Schemas
@app.post("/login", response_model=dict)
def login_broker(payload: LoginRequest):
    if not mt5.initialize():
        raise HTTPException(status_code=500, detail=f"MT5 initialization failed: {mt5.last_error()}")
    
    authorized = mt5.login(
        login=payload.login,
        password=payload.password,
        server=payload.server
    )
    if not authorized:
        raise HTTPException(status_code=401, detail=f"Broker login failed: {mt5.last_error()}")
    
    return {"status": "success", "message": f"Successfully logged into account {payload.login}"}

@app.get("/account", response_model=AccountInfo)
def get_account_info():
    info = mt5.account_info()
    if info is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch account info: {mt5.last_error()}")
    return AccountInfo(**info._asdict())

@app.post("/order", response_model=OrderResponse)
def send_order(payload: OrderRequest):
    # Resolve order action type
    action_type = mt5.ORDER_TYPE_BUY if payload.action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    
    # Fetch execution price if none was provided
    price = payload.price
    if not price:
        tick = mt5.symbol_info_tick(payload.symbol)
        if not tick:
            raise HTTPException(status_code=400, detail=f"Failed to fetch symbol ticks: {mt5.last_error()}")
        price = tick.ask if payload.action.upper() == "BUY" else tick.bid

    request_payload = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": payload.symbol,
        "volume": payload.volume,
        "type": action_type,
        "price": price,
        "sl": payload.sl or 0.0,
        "tp": payload.tp or 0.0,
        "deviation": 20,
        "magic": 123456,
        "comment": "FastAPI Monorepo order",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request_payload)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Order rejected by broker: retcode={result.retcode}, comment={result.comment}"
        )
    
    # Map values to Pydantic OrderResponse
    res_dict = result._asdict()
    # Add a fallback request_id if not returned by native struct
    if "request_id" not in res_dict:
        res_dict["request_id"] = "req-dynamic-uuid"
        
    return OrderResponse(**res_dict)

@app.get("/positions", response_model=PositionsResponse)
def get_positions(symbol: str = None):
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None or len(positions) == 0:
        return PositionsResponse(positions=[])
    
    # Use Pandas to transform NumPy arrays safely into JSON records
    df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys() if len(positions) > 0 else [])
    df = df.replace({np.nan: None})
    records = df.to_dict(orient="records")
    
    # Map raw records to PositionInfo models
    positions_list = [PositionInfo(**rec) for rec in records]
    return PositionsResponse(positions=positions_list)

@app.get("/health")
def get_health():
    proc = psutil.Process()
    return {
        "status": "healthy",
        "pid": proc.pid,
        "cpu_percent": proc.cpu_percent(),
        "memory_info": proc.memory_info()._asdict()
    }

def main():
    import uvicorn
    # Bind argument parsing for dynamic port allocation
    import sys
    port = 8001
    for arg in sys.argv:
        if arg.startswith("--port="):
            port = int(arg.split("=")[1])
            
    uvicorn.run(app, host="127.0.0.1", port=port)

if __name__ == "__main__":
    main()
