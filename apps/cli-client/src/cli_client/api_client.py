import httpx
from typing import Optional, List, Dict, Any
from shared_schemas import (
    ProvisionRequest,
    ProvisionResponse,
    TraderListResponse,
    TraderStatus,
    DeprovisionResponse,
    AccountInfo,
    OrderRequest,
    OrderResponse,
    OrderCheckResponse,
    PositionsResponse,
    OrdersGetResponse,
    HistoryDealsRequest,
    HistoryDealsResponse,
    TickResponse,
    SymbolInfoTickRequest
)

class ApiClient:
    def __init__(self, base_url: str):
        # Remove trailing slash if present
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)

    # --- Admin / Orchestrator API Operations ---
    
    def orchestrator_status(self) -> Dict[str, Any]:
        """Check status of Central Orchestrator."""
        # The orchestrator's admin routes are included directly on app.
        # Let's ping the root which returns the HTML dashboard or test connectivity.
        response = self.client.get(f"{self.base_url}/")
        response.raise_for_status()
        return {
            "status": "online",
            "url": self.base_url
        }

    def provision_trader(self, organization: str, trader_name: str) -> ProvisionResponse:
        """Provision a new trader session."""
        payload = ProvisionRequest(organization=organization, trader_name=trader_name)
        response = self.client.post(
            f"{self.base_url}/provision",
            json=payload.model_dump()
        )
        response.raise_for_status()
        return ProvisionResponse(**response.json())

    def list_traders(self) -> TraderListResponse:
        """List all provisioned traders with their statuses."""
        response = self.client.get(f"{self.base_url}/traders")
        response.raise_for_status()
        return TraderListResponse(**response.json())

    def get_trader_status(self, username: str) -> TraderStatus:
        """Probe status of a single trader."""
        response = self.client.get(f"{self.base_url}/traders/{username}/status")
        response.raise_for_status()
        return TraderStatus(**response.json())

    def deprovision_trader(self, username: str) -> DeprovisionResponse:
        """Fully deprovision a trader session and user."""
        response = self.client.delete(f"{self.base_url}/traders/{username}")
        response.raise_for_status()
        return DeprovisionResponse(**response.json())

    # --- Trading / Session Wrapper APIs (routed via Gateway proxy) ---

    def _gateway_url(self, trader: str, path: str) -> str:
        """Helper to construct gateway-proxied URLs."""
        return f"{self.base_url}/api/v1/traders/{trader}/api/{path}"

    def get_account_info(self, trader: str) -> AccountInfo:
        """Retrieve active account metrics."""
        response = self.client.get(self._gateway_url(trader, "account"))
        response.raise_for_status()
        return AccountInfo(**response.json())

    def get_positions(self, trader: str, symbol: Optional[str] = None) -> PositionsResponse:
        """Retrieve open active positions."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        response = self.client.get(self._gateway_url(trader, "positions"), params=params)
        response.raise_for_status()
        return PositionsResponse(**response.json())

    def get_orders(self, trader: str, symbol: Optional[str] = None) -> OrdersGetResponse:
        """Retrieve active pending orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        response = self.client.get(self._gateway_url(trader, "orders"), params=params)
        response.raise_for_status()
        return OrdersGetResponse(**response.json())

    def check_order(self, trader: str, payload: OrderRequest) -> OrderCheckResponse:
        """Check margin/profit calculations before sending order."""
        response = self.client.post(
            self._gateway_url(trader, "order/check"),
            json=payload.model_dump()
        )
        response.raise_for_status()
        return OrderCheckResponse(**response.json())

    def execute_order(self, trader: str, payload: OrderRequest) -> OrderResponse:
        """Execute a market order."""
        response = self.client.post(
            self._gateway_url(trader, "order"),
            json=payload.model_dump()
        )
        response.raise_for_status()
        return OrderResponse(**response.json())

    def get_history_deals(self, trader: str, date_from: Optional[int] = None, date_to: Optional[int] = None) -> HistoryDealsResponse:
        """Retrieve executed historical deals."""
        payload = HistoryDealsRequest(date_from=date_from, date_to=date_to)
        response = self.client.post(
            self._gateway_url(trader, "history/deals"),
            json=payload.model_dump(exclude_none=True)
        )
        response.raise_for_status()
        return HistoryDealsResponse(**response.json())

    def get_symbol_tick(self, trader: str, symbol: str) -> TickResponse:
        """Retrieve latest bid/ask tick data for a symbol."""
        payload = SymbolInfoTickRequest(symbol=symbol)
        response = self.client.post(
            self._gateway_url(trader, "market/symbol/info/tick"),
            json=payload.model_dump()
        )
        response.raise_for_status()
        return TickResponse(**response.json())
