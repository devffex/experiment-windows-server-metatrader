import argparse
import sys
import psutil
import pandas as pd
import numpy as np
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query

from shared_schemas import (
    OrderRequest,
    OrderResponse,
    OrderCheckResponse,
    OrderCalcProfitResponse,
    OrderCalcMarginResponse,
    PositionInfo,
    PositionsResponse,
    PositionsTotalResponse,
    OrderInfo,
    OrdersGetResponse,
    OrdersTotalResponse,
    AccountInfo,
    TerminalInfo,
    VersionResponse,
    LastErrorResponse,
    DealInfo,
    HistoryDealsRequest,
    HistoryDealsResponse,
    HistoryDealsTotalRequest,
    HistoryDealsTotalResponse,
    HistoryOrdersRequest,
    HistoryOrdersResponse,
    HistoryOrdersTotalRequest,
    HistoryOrdersTotalResponse,
    TickResponse,
    CopyTicksRangeRequest,
    CopyTicksFromRequest,
    CopyTicksResponse,
    RateResponse,
    CopyRatesRangeRequest,
    CopyRatesFromRequest,
    CopyRatesFromPosRequest,
    CopyRatesResponse,
    MarketBookRequest,
    BookInfo,
    MarketBookGetResponse,
    MarketBookActionResponse,
    SymbolSelectRequest,
    SymbolSelectResponse,
    SymbolInfoRequest,
    SymbolInfoResponse,
    SymbolInfoTickRequest,
    SymbolsGetResponse,
    SymbolsTotalResponse,
)

app = FastAPI(title="Session MT5 loopback API")

# --- Native MT5 Windows Import with Platform Mock Fallback ---
try:
    import os
    if os.environ.get("METAFORGE_MOCK_MT5") == "1":
        raise ImportError("Forced Mock Mode")
    import MetaTrader5 as mt5
    # Auto-initialize on import/startup inside the user RDP session
    if not mt5.initialize():
        print(f"[ERROR] Native MT5 initialization failed: {mt5.last_error()}", file=sys.stderr)
except ImportError:
    class MockMT5:
        def __init__(self):
            # MT5 Enums
            self.ORDER_TYPE_BUY = 0
            self.ORDER_TYPE_SELL = 1
            self.TRADE_ACTION_DEAL = 1
            self.ORDER_TIME_GTC = 0
            self.ORDER_FILLING_FOK = 0
            self.TRADE_RETCODE_DONE = 10009

        def initialize(self, *args, **kwargs):
            return True

        def shutdown(self):
            pass

        def last_error(self):
            return (0, "Success (Mock Mode)")

        def version(self):
            return (500, 4000, "15 Sep 2023")

        def terminal_info(self):
            class TermInfo:
                def _asdict(self):
                    return {
                        "community_account": True,
                        "community_connection": True,
                        "connected": True,
                        "dlls_allowed": False,
                        "trade_allowed": True,
                        "tradeapi_disabled": False,
                        "email_enabled": False,
                        "ftp_enabled": False,
                        "notifications_enabled": False,
                        "mqid": False,
                        "build": 4000,
                        "maxbars": 5000,
                        "codepage": 1252,
                        "ping_last": 1500,
                        "community_balance": 100.0,
                        "retransmission": 0.0,
                        "company": "MetaQuotes Software Corp.",
                        "name": "MetaTrader 5",
                        "language": "English",
                        "path": "C:\\savisor\\terminal",
                        "data_path": "C:\\savisor\\terminal",
                        "commondata_path": "C:\\savisor\\common",
                    }
            return TermInfo()

        def account_info(self):
            class AccInfo:
                def _asdict(self):
                    return {
                        "login": 5012345,
                        "trade_mode": 0,
                        "leverage": 100,
                        "limit_orders": 200,
                        "margin_so_mode": 0,
                        "trade_allowed": True,
                        "trade_expert": True,
                        "margin_mode": 2,
                        "currency_digits": 2,
                        "fifo_close": False,
                        "balance": 10000.0,
                        "credit": 0.0,
                        "profit": 15.50,
                        "equity": 10015.50,
                        "margin": 10.0,
                        "margin_free": 10005.50,
                        "margin_level": 100155.0,
                        "margin_so_call": 50.0,
                        "margin_so_so": 30.0,
                        "margin_initial": 0.0,
                        "margin_maintenance": 0.0,
                        "assets": 0.0,
                        "liabilities": 0.0,
                        "commission_blocked": 0.0,
                        "name": "Manual RDP Trader",
                        "server": "MetaQuotes-Demo",
                        "currency": "USD",
                        "company": "MetaQuotes Software Corp."
                    }
            return AccInfo()

        def order_send(self, request):
            class OrderResult:
                def __init__(self):
                    self.retcode = 10009
                def _asdict(self):
                    return {
                        "ticket": 87654321,
                        "retcode": self.retcode,
                        "price": request.get("price", 1.1025),
                        "volume": request.get("volume", 0.1),
                        "comment": "Request executed successfully",
                        "request_id": "req-mock-12345"
                    }
            return OrderResult()

        def order_check(self, request):
            class CheckResult:
                def _asdict(self):
                    return {
                        "retcode": 0,
                        "balance": 10000.0,
                        "equity": 10000.0,
                        "profit": 0.0,
                        "margin": 10.0,
                        "margin_free": 9990.0,
                        "margin_level": 100000.0,
                        "comment": "Mock success"
                    }
            return CheckResult()

        def order_calc_profit(self, action, symbol, volume, price_open, price_close):
            return 150.0

        def order_calc_margin(self, action, symbol, volume, price):
            return 10.0

        def positions_get(self, symbol=None, group=None, ticket=None):
            class Position:
                def _asdict(self):
                    return {
                        "ticket": 987654,
                        "symbol": symbol or "EURUSD",
                        "volume": 0.1,
                        "price_open": 1.1025,
                        "profit": 15.50,
                        "comment": "API position",
                        "time": 1705320000
                    }
            return [Position()]

        def positions_total(self):
            return 1

        def orders_get(self, symbol=None, group=None, ticket=None):
            class Order:
                def _asdict(self):
                    return {
                        "ticket": 112233,
                        "time_setup": 1705320000,
                        "type": 0,
                        "state": 1,
                        "volume_initial": 0.5,
                        "volume_current": 0.5,
                        "price_open": 1.1050,
                        "sl": 0.0,
                        "tp": 0.0,
                        "price_current": 1.1025,
                        "symbol": symbol or "EURUSD",
                        "comment": "Pending order"
                    }
            return [Order()]

        def orders_total(self):
            return 1

        def history_deals_get(self, *args, **kwargs):
            class Deal:
                def _asdict(self):
                    return {
                        "ticket": 554433,
                        "order": 112233,
                        "time": 1705320000,
                        "time_msc": 1705320000000,
                        "type": 0,
                        "entry": 0,
                        "magic": 123456,
                        "position_id": 987654,
                        "reason": 3,
                        "volume": 0.1,
                        "price": 1.1025,
                        "commission": -0.5,
                        "swap": 0.0,
                        "profit": 15.0,
                        "fee": 0.0,
                        "symbol": "EURUSD",
                        "comment": "Historical deal",
                        "external_id": "ext-deal-1"
                    }
            return [Deal()]

        def history_deals_total(self, date_from, date_to):
            return 1

        def history_orders_get(self, *args, **kwargs):
            class HistOrder:
                def _asdict(self):
                    return {
                        "ticket": 112233,
                        "time_setup": 1705320000,
                        "type": 0,
                        "state": 2,
                        "volume_initial": 0.5,
                        "volume_current": 0.0,
                        "price_open": 1.1050,
                        "sl": 0.0,
                        "tp": 0.0,
                        "price_current": 1.1050,
                        "symbol": "EURUSD",
                        "comment": "Filled historical order"
                    }
            return [HistOrder()]

        def history_orders_total(self, date_from, date_to):
            return 1

        def copy_ticks_range(self, symbol, date_from, date_to, flags):
            return [
                {
                    "time": 1705320000,
                    "bid": 1.1023,
                    "ask": 1.1025,
                    "last": 0.0,
                    "volume": 0,
                    "time_msc": 1705320000000,
                    "flags": flags,
                    "volume_real": 0.0
                }
            ]

        def copy_ticks_from(self, symbol, date_from, count, flags):
            return [
                {
                    "time": 1705320000,
                    "bid": 1.1023,
                    "ask": 1.1025,
                    "last": 0.0,
                    "volume": 0,
                    "time_msc": 1705320000000,
                    "flags": flags,
                    "volume_real": 0.0
                }
            ]

        def copy_rates_range(self, symbol, timeframe, date_from, date_to):
            return [
                {
                    "time": 1705320000,
                    "open": 1.1020,
                    "high": 1.1030,
                    "low": 1.1015,
                    "close": 1.1025,
                    "tick_volume": 42,
                    "spread": 2,
                    "real_volume": 0
                }
            ]

        def copy_rates_from(self, symbol, timeframe, date_from, count):
            return [
                {
                    "time": 1705320000,
                    "open": 1.1020,
                    "high": 1.1030,
                    "low": 1.1015,
                    "close": 1.1025,
                    "tick_volume": 42,
                    "spread": 2,
                    "real_volume": 0
                }
            ]

        def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
            return [
                {
                    "time": 1705320000,
                    "open": 1.1020,
                    "high": 1.1030,
                    "low": 1.1015,
                    "close": 1.1025,
                    "tick_volume": 42,
                    "spread": 2,
                    "real_volume": 0
                }
            ]

        def market_book_add(self, symbol):
            return True

        def market_book_release(self, symbol):
            return True

        def market_book_get(self, symbol):
            class BookItem:
                def _asdict(self):
                    return {
                        "type": 1,
                        "price": 1.1025,
                        "volume": 15,
                        "volume_dbl": 15.0
                    }
            return [BookItem()]

        def symbol_select(self, symbol, enable=True):
            return True

        def symbol_info(self, symbol):
            class SymInfo:
                def _asdict(self):
                    return {
                        "custom": False,
                        "spread_float": True,
                        "margin_hedged_use_leg": False,
                        "chart_mode": 0,
                        "select": True,
                        "visible": True,
                        "session_deals": 0,
                        "session_buy_orders": 0,
                        "session_sell_orders": 0,
                        "volume": 0,
                        "volumehigh": 0,
                        "volumelow": 0,
                        "time": 1705320000,
                        "digits": 5,
                        "spread": 2,
                        "ticks_bookdepth": 10,
                        "trade_calc_mode": 0,
                        "trade_mode": 4,
                        "start_time": 0,
                        "expiration_time": 0,
                        "trade_stops_level": 0,
                        "trade_freeze_level": 0,
                        "trade_exemode": 1,
                        "swap_mode": 1,
                        "swap_rollover3days": 3,
                        "expiration_mode": 7,
                        "filling_mode": 1,
                        "order_mode": 127,
                        "order_gtc_mode": 0,
                        "option_mode": 0,
                        "option_right": 0,
                        "bid": 1.1023,
                        "bidhigh": 1.1050,
                        "bidlow": 1.1000,
                        "ask": 1.1025,
                        "askhigh": 1.1052,
                        "asklow": 1.1002,
                        "last": 0.0,
                        "lasthigh": 0.0,
                        "lastlow": 0.0,
                        "volume_real": 0.0,
                        "volumehigh_real": 0.0,
                        "volumelow_real": 0.0,
                        "option_strike": 0.0,
                        "point": 0.00001,
                        "trade_tick_value": 1.0,
                        "trade_tick_value_profit": 1.0,
                        "trade_tick_value_loss": 1.0,
                        "trade_tick_size": 0.00001,
                        "trade_contract_size": 100000.0,
                        "trade_accrued_interest": 0.0,
                        "trade_face_value": 0.0,
                        "trade_liquidity_rate": 0.0,
                        "volume_min": 0.01,
                        "volume_max": 500.0,
                        "volume_step": 0.01,
                        "volume_limit": 0.0,
                        "swap_long": -1.5,
                        "swap_short": -0.5,
                        "margin_initial": 0.0,
                        "margin_maintenance": 0.0,
                        "session_volume": 0.0,
                        "session_turnover": 0.0,
                        "session_interest": 0.0,
                        "session_buy_orders_volume": 0.0,
                        "session_sell_orders_volume": 0.0,
                        "session_open": 0.0,
                        "session_close": 0.0,
                        "session_aw": 0.0,
                        "session_price_settlement": 0.0,
                        "session_price_limit_min": 0.0,
                        "session_price_limit_max": 0.0,
                        "margin_hedged": 100000.0,
                        "price_change": 0.0,
                        "price_volatility": 0.0,
                        "price_theoretical": 0.0,
                        "price_greeks_delta": 0.0,
                        "price_greeks_theta": 0.0,
                        "price_greeks_gamma": 0.0,
                        "price_greeks_vega": 0.0,
                        "price_greeks_rho": 0.0,
                        "price_greeks_omega": 0.0,
                        "price_sensitivity": 0.0,
                        "basis": "",
                        "category": "",
                        "currency_base": "EUR",
                        "currency_profit": "USD",
                        "currency_margin": "EUR",
                        "bank": "",
                        "description": "Euro vs US Dollar",
                        "exchange": "",
                        "formula": "",
                        "isin": "",
                        "name": symbol,
                        "page": "http://www.mql5.com",
                        "path": f"Forex\\{symbol}"
                    }
            return SymInfo()

        def symbol_info_tick(self, symbol):
            class Tick:
                def __init__(self):
                    self.time = 1705320000
                    self.bid = 1.1023
                    self.ask = 1.1025
                    self.last = 0.0
                    self.volume = 0
                    self.time_msc = 1705320000000
                    self.flags = 2
                    self.volume_real = 0.0
                def _asdict(self):
                    return {
                        "time": self.time,
                        "bid": self.bid,
                        "ask": self.ask,
                        "last": self.last,
                        "volume": self.volume,
                        "time_msc": self.time_msc,
                        "flags": self.flags,
                        "volume_real": self.volume_real
                    }
            return Tick()

        def symbols_get(self, group=None):
            class SymInfo:
                def _asdict(self):
                    return {
                        "custom": False,
                        "spread_float": True,
                        "margin_hedged_use_leg": False,
                        "chart_mode": 0,
                        "select": True,
                        "visible": True,
                        "session_deals": 0,
                        "session_buy_orders": 0,
                        "session_sell_orders": 0,
                        "volume": 0,
                        "volumehigh": 0,
                        "volumelow": 0,
                        "time": 1705320000,
                        "digits": 5,
                        "spread": 2,
                        "ticks_bookdepth": 10,
                        "trade_calc_mode": 0,
                        "trade_mode": 4,
                        "start_time": 0,
                        "expiration_time": 0,
                        "trade_stops_level": 0,
                        "trade_freeze_level": 0,
                        "trade_exemode": 1,
                        "swap_mode": 1,
                        "swap_rollover3days": 3,
                        "expiration_mode": 7,
                        "filling_mode": 1,
                        "order_mode": 127,
                        "order_gtc_mode": 0,
                        "option_mode": 0,
                        "option_right": 0,
                        "bid": 1.1023,
                        "bidhigh": 1.1050,
                        "bidlow": 1.1000,
                        "ask": 1.1025,
                        "askhigh": 1.1052,
                        "asklow": 1.1002,
                        "last": 0.0,
                        "lasthigh": 0.0,
                        "lastlow": 0.0,
                        "volume_real": 0.0,
                        "volumehigh_real": 0.0,
                        "volumelow_real": 0.0,
                        "option_strike": 0.0,
                        "point": 0.00001,
                        "trade_tick_value": 1.0,
                        "trade_tick_value_profit": 1.0,
                        "trade_tick_value_loss": 1.0,
                        "trade_tick_size": 0.00001,
                        "trade_contract_size": 100000.0,
                        "trade_accrued_interest": 0.0,
                        "trade_face_value": 0.0,
                        "trade_liquidity_rate": 0.0,
                        "volume_min": 0.01,
                        "volume_max": 500.0,
                        "volume_step": 0.01,
                        "volume_limit": 0.0,
                        "swap_long": -1.5,
                        "swap_short": -0.5,
                        "margin_initial": 0.0,
                        "margin_maintenance": 0.0,
                        "session_volume": 0.0,
                        "session_turnover": 0.0,
                        "session_interest": 0.0,
                        "session_buy_orders_volume": 0.0,
                        "session_sell_orders_volume": 0.0,
                        "session_open": 0.0,
                        "session_close": 0.0,
                        "session_aw": 0.0,
                        "session_price_settlement": 0.0,
                        "session_price_limit_min": 0.0,
                        "session_price_limit_max": 0.0,
                        "margin_hedged": 100000.0,
                        "price_change": 0.0,
                        "price_volatility": 0.0,
                        "price_theoretical": 0.0,
                        "price_greeks_delta": 0.0,
                        "price_greeks_theta": 0.0,
                        "price_greeks_gamma": 0.0,
                        "price_greeks_vega": 0.0,
                        "price_greeks_rho": 0.0,
                        "price_greeks_omega": 0.0,
                        "price_sensitivity": 0.0,
                        "basis": "",
                        "category": "",
                        "currency_base": "EUR",
                        "currency_profit": "USD",
                        "currency_margin": "EUR",
                        "bank": "",
                        "description": "Euro vs US Dollar",
                        "exchange": "",
                        "formula": "",
                        "isin": "",
                        "name": "EURUSD",
                        "page": "http://www.mql5.com",
                        "path": "Forex\\EURUSD"
                    }
            return [SymInfo()]

        def symbols_total(self):
            return 1

    mt5 = MockMT5()


# --- Helper Function for NumPy/List of Objects Serialization ---
def serialize_pandas_records(raw_items) -> List[dict]:
    if not raw_items:
        return []
    try:
        if isinstance(raw_items, np.ndarray):
            df = pd.DataFrame(raw_items)
            df = df.replace({np.nan: None})
            return df.to_dict(orient="records")
        elif isinstance(raw_items, (list, tuple)):
            if len(raw_items) > 0 and hasattr(raw_items[0], "_asdict"):
                df = pd.DataFrame([item._asdict() for item in raw_items])
                df = df.replace({np.nan: None})
                return df.to_dict(orient="records")
    except Exception as e:
        print(f"[WARNING] Panda serialization error: {e}", file=sys.stderr)
    # Simple fallback serialization
    serialized = []
    for item in raw_items:
        if hasattr(item, "_asdict"):
            serialized.append(item._asdict())
        elif isinstance(item, dict):
            serialized.append(item)
        else:
            serialized.append(item)
    return serialized


# --- API Endpoints ---

# 1. GET /account
@app.get("/account", response_model=AccountInfo)
def get_account_info():
    info = mt5.account_info()
    if info is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch account info: {mt5.last_error()}")
    return AccountInfo(**info._asdict())

# 2. POST /order
@app.post("/order", response_model=OrderResponse)
def send_order(payload: OrderRequest):
    action_type = mt5.ORDER_TYPE_BUY if payload.action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
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
    
    res_dict = result._asdict()
    if "request_id" not in res_dict:
        res_dict["request_id"] = "req-dynamic-uuid"
        
    return OrderResponse(**res_dict)

# 3. POST /order/check
@app.post("/order/check", response_model=OrderCheckResponse)
def check_order(payload: OrderRequest):
    action_type = mt5.ORDER_TYPE_BUY if payload.action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    price = payload.price or 0.0
    
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
        "comment": "FastAPI Monorepo check",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_check(request_payload)
    if result is None:
        raise HTTPException(status_code=400, detail=f"Order check failed: {mt5.last_error()}")
    return OrderCheckResponse(**result._asdict())

# 4. POST /order/calc/profit
@app.post("/order/calc/profit", response_model=OrderCalcProfitResponse)
def calc_order_profit(action: str, symbol: str, volume: float, price_open: float, price_close: float):
    action_val = mt5.ORDER_TYPE_BUY if action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    profit = mt5.order_calc_profit(action_val, symbol, volume, price_open, price_close)
    if profit is None:
        raise HTTPException(status_code=400, detail=f"Failed to calculate profit: {mt5.last_error()}")
    return OrderCalcProfitResponse(profit=profit)

# 5. POST /order/calc/margin
@app.post("/order/calc/margin", response_model=OrderCalcMarginResponse)
def calc_order_margin(action: str, symbol: str, volume: float, price: float):
    action_val = mt5.ORDER_TYPE_BUY if action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
    margin = mt5.order_calc_margin(action_val, symbol, volume, price)
    if margin is None:
        raise HTTPException(status_code=400, detail=f"Failed to calculate margin: {mt5.last_error()}")
    return OrderCalcMarginResponse(margin=margin)

# 6. GET /positions
@app.get("/positions", response_model=PositionsResponse)
def get_positions(symbol: str = None):
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None or len(positions) == 0:
        return PositionsResponse(positions=[])
    records = serialize_pandas_records(positions)
    return PositionsResponse(positions=[PositionInfo(**rec) for rec in records])

# 7. GET /positions/total
@app.get("/positions/total", response_model=PositionsTotalResponse)
def get_positions_total():
    total = mt5.positions_total()
    if total is None:
        raise HTTPException(status_code=500, detail=f"Failed to get positions total: {mt5.last_error()}")
    return PositionsTotalResponse(total=total)

# 8. GET /orders
@app.get("/orders", response_model=OrdersGetResponse)
def get_orders(symbol: str = None):
    orders = mt5.orders_get(symbol=symbol) if symbol else mt5.orders_get()
    if orders is None or len(orders) == 0:
        return OrdersGetResponse(orders=[])
    records = serialize_pandas_records(orders)
    return OrdersGetResponse(orders=[OrderInfo(**rec) for rec in records])

# 9. GET /orders/total
@app.get("/orders/total", response_model=OrdersTotalResponse)
def get_orders_total():
    total = mt5.orders_total()
    if total is None:
        raise HTTPException(status_code=500, detail=f"Failed to get orders total: {mt5.last_error()}")
    return OrdersTotalResponse(total=total)

# 10. GET /terminal/info
@app.get("/terminal/info", response_model=TerminalInfo)
def get_terminal_info():
    info = mt5.terminal_info()
    if info is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch terminal info: {mt5.last_error()}")
    return TerminalInfo(**info._asdict())

# 11. GET /version
@app.get("/version", response_model=VersionResponse)
def get_version():
    ver = mt5.version()
    if ver is None or len(ver) < 3:
        raise HTTPException(status_code=500, detail=f"Failed to fetch version: {mt5.last_error()}")
    return VersionResponse(version=ver[0], build=ver[1], release_date=ver[2])

# 12. GET /last-error
@app.get("/last-error", response_model=LastErrorResponse)
def get_last_error():
    err = mt5.last_error()
    return LastErrorResponse(code=err[0], description=err[1])

# 13. POST /history/deals
@app.post("/history/deals", response_model=HistoryDealsResponse)
def get_history_deals(payload: HistoryDealsRequest):
    deals = None
    if payload.ticket is not None:
        deals = mt5.history_deals_get(ticket=payload.ticket)
    elif payload.position is not None:
        deals = mt5.history_deals_get(position=payload.position)
    elif payload.date_from is not None and payload.date_to is not None:
        if payload.group is not None:
            deals = mt5.history_deals_get(payload.date_from, payload.date_to, group=payload.group)
        else:
            deals = mt5.history_deals_get(payload.date_from, payload.date_to)
    else:
        deals = mt5.history_deals_get()

    if deals is None or len(deals) == 0:
        return HistoryDealsResponse(deals=[])
    records = serialize_pandas_records(deals)
    return HistoryDealsResponse(deals=[DealInfo(**rec) for rec in records])

# 14. POST /history/deals/total
@app.post("/history/deals/total", response_model=HistoryDealsTotalResponse)
def get_history_deals_total(payload: HistoryDealsTotalRequest):
    total = mt5.history_deals_total(payload.date_from, payload.date_to)
    if total is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history deals total: {mt5.last_error()}")
    return HistoryDealsTotalResponse(total=total)

# 15. POST /history/orders
@app.post("/history/orders", response_model=HistoryOrdersResponse)
def get_history_orders(payload: HistoryOrdersRequest):
    orders = None
    if payload.ticket is not None:
        orders = mt5.history_orders_get(ticket=payload.ticket)
    elif payload.position is not None:
        orders = mt5.history_orders_get(position=payload.position)
    elif payload.date_from is not None and payload.date_to is not None:
        if payload.group is not None:
            orders = mt5.history_orders_get(payload.date_from, payload.date_to, group=payload.group)
        else:
            orders = mt5.history_orders_get(payload.date_from, payload.date_to)
    else:
        orders = mt5.history_orders_get()

    if orders is None or len(orders) == 0:
        return HistoryOrdersResponse(orders=[])
    records = serialize_pandas_records(orders)
    return HistoryOrdersResponse(orders=[OrderInfo(**rec) for rec in records])

# 16. POST /history/orders/total
@app.post("/history/orders/total", response_model=HistoryOrdersTotalResponse)
def get_history_orders_total(payload: HistoryOrdersTotalRequest):
    total = mt5.history_orders_total(payload.date_from, payload.date_to)
    if total is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history orders total: {mt5.last_error()}")
    return HistoryOrdersTotalResponse(total=total)

# 17. POST /market/ticks/range
@app.post("/market/ticks/range", response_model=CopyTicksResponse)
def copy_ticks_range(payload: CopyTicksRangeRequest):
    ticks = mt5.copy_ticks_range(payload.symbol, payload.date_from, payload.date_to, payload.flags)
    if ticks is None or len(ticks) == 0:
        return CopyTicksResponse(ticks=[])
    records = serialize_pandas_records(ticks)
    return CopyTicksResponse(ticks=[TickResponse(**rec) for rec in records])

# 18. POST /market/ticks/from
@app.post("/market/ticks/from", response_model=CopyTicksResponse)
def copy_ticks_from(payload: CopyTicksFromRequest):
    ticks = mt5.copy_ticks_from(payload.symbol, payload.date_from, payload.count, payload.flags)
    if ticks is None or len(ticks) == 0:
        return CopyTicksResponse(ticks=[])
    records = serialize_pandas_records(ticks)
    return CopyTicksResponse(ticks=[TickResponse(**rec) for rec in records])

# 19. POST /market/rates/range
@app.post("/market/rates/range", response_model=CopyRatesResponse)
def copy_rates_range(payload: CopyRatesRangeRequest):
    rates = mt5.copy_rates_range(payload.symbol, payload.timeframe, payload.date_from, payload.date_to)
    if rates is None or len(rates) == 0:
        return CopyRatesResponse(rates=[])
    records = serialize_pandas_records(rates)
    return CopyRatesResponse(rates=[RateResponse(**rec) for rec in records])

# 20. POST /market/rates/from
@app.post("/market/rates/from", response_model=CopyRatesResponse)
def copy_rates_from(payload: CopyRatesFromRequest):
    rates = mt5.copy_rates_from(payload.symbol, payload.timeframe, payload.date_from, payload.count)
    if rates is None or len(rates) == 0:
        return CopyRatesResponse(rates=[])
    records = serialize_pandas_records(rates)
    return CopyRatesResponse(rates=[RateResponse(**rec) for rec in records])

# 21. POST /market/rates/from-pos
@app.post("/market/rates/from-pos", response_model=CopyRatesResponse)
def copy_rates_from_pos(payload: CopyRatesFromPosRequest):
    rates = mt5.copy_rates_from_pos(payload.symbol, payload.timeframe, payload.start_pos, payload.count)
    if rates is None or len(rates) == 0:
        return CopyRatesResponse(rates=[])
    records = serialize_pandas_records(rates)
    return CopyRatesResponse(rates=[RateResponse(**rec) for rec in records])

# 22. POST /market/book/add
@app.post("/market/book/add", response_model=MarketBookActionResponse)
def market_book_add(payload: MarketBookRequest):
    success = mt5.market_book_add(payload.symbol)
    return MarketBookActionResponse(success=success)

# 23. POST /market/book/release
@app.post("/market/book/release", response_model=MarketBookActionResponse)
def market_book_release(payload: MarketBookRequest):
    success = mt5.market_book_release(payload.symbol)
    return MarketBookActionResponse(success=success)

# 24. POST /market/book/get
@app.post("/market/book/get", response_model=MarketBookGetResponse)
def market_book_get(payload: MarketBookRequest):
    items = mt5.market_book_get(payload.symbol)
    if items is None or len(items) == 0:
        return MarketBookGetResponse(items=[])
    records = serialize_pandas_records(items)
    return MarketBookGetResponse(items=[BookInfo(**rec) for rec in records])

# 25. POST /market/symbol/select
@app.post("/market/symbol/select", response_model=SymbolSelectResponse)
def symbol_select(payload: SymbolSelectRequest):
    enable_val = True if payload.enable is None else payload.enable
    success = mt5.symbol_select(payload.symbol, enable_val)
    return SymbolSelectResponse(success=success)

# 26. POST /market/symbol/info
@app.post("/market/symbol/info", response_model=SymbolInfoResponse)
def symbol_info(payload: SymbolInfoRequest):
    info = mt5.symbol_info(payload.symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Symbol not found: {payload.symbol}")
    return SymbolInfoResponse(**info._asdict())

# 27. POST /market/symbol/info/tick
@app.post("/market/symbol/info/tick", response_model=TickResponse)
def symbol_info_tick(payload: SymbolInfoTickRequest):
    tick = mt5.symbol_info_tick(payload.symbol)
    if tick is None:
        raise HTTPException(status_code=404, detail=f"Symbol tick not found: {payload.symbol}")
    return TickResponse(**tick._asdict())

# 28. GET /market/symbols
@app.get("/market/symbols", response_model=SymbolsGetResponse)
def symbols_get(group: str = None):
    symbols = mt5.symbols_get(group=group) if group else mt5.symbols_get()
    if symbols is None or len(symbols) == 0:
        return SymbolsGetResponse(symbols=[])
    records = serialize_pandas_records(symbols)
    return SymbolsGetResponse(symbols=[SymbolInfoResponse(**rec) for rec in records])

# 29. GET /market/symbols/total
@app.get("/market/symbols/total", response_model=SymbolsTotalResponse)
def symbols_total():
    total = mt5.symbols_total()
    if total is None:
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbols total: {mt5.last_error()}")
    return SymbolsTotalResponse(total=total)

# 30. GET /health
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
    port = 8001
    for arg in sys.argv:
        if arg.startswith("--port="):
            port = int(arg.split("=")[1])
            
    uvicorn.run(app, host="127.0.0.1", port=port)

if __name__ == "__main__":
    main()
