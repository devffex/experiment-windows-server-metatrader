from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from orchestrator.config import Settings
from orchestrator.main import app
from orchestrator.store import TraderMapping


class TestSubdomainRouter(unittest.TestCase):
    def setUp(self):
        # Backup original app state
        self.original_settings = getattr(app.state, "settings", None)
        self.original_store = getattr(app.state, "store", None)
        self.original_gateway = getattr(app.state, "gateway", None)

        # Initialize test-specific settings, mock store, and mock gateway proxy
        self.settings = Settings(base_domain="savisor.com")
        self.store = MagicMock()
        self.gateway = MagicMock()

        # Inject mocks into app state
        app.state.settings = self.settings
        app.state.store = self.store
        app.state.gateway = self.gateway

        # Set up a registered trader session mapping for "julio"
        self.mock_mapping = TraderMapping(
            port=8001,
            password="testpassword",
            rdp_profile="test.rdp",
            organization="devffex",
            trader_name="julio",
        )

        async def mock_get_trader(username: str):
            if username == "julio":
                return self.mock_mapping
            return None

        self.store.get_trader = mock_get_trader

        # Set up a mock request forwarding callback
        async def mock_forward_request(port: int, path: str, request):
            return Response(
                content=f"Forwarded to port {port} path {path}".encode(),
                status_code=200,
                headers={"X-Forwarded-Mock": "true"},
            )

        self.gateway.forward_request = mock_forward_request

        self.client = TestClient(app)

    def tearDown(self):
        # Restore original app state to prevent test bleed
        if self.original_settings:
            app.state.settings = self.original_settings
        if self.original_store:
            app.state.store = self.original_store
        if self.original_gateway:
            app.state.gateway = self.original_gateway

    def test_reserved_subdomain_passes_through(self):
        # Reserved subdomain (e.g., orchestrator) bypasses subdomain proxying and hits central admin routers
        async def mock_load():
            return {}

        self.store.load = mock_load

        response = self.client.get(
            "/traders",
            headers={"Host": "orchestrator.savisor.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("traders", response.json())

    def test_valid_trader_subdomain_is_forwarded(self):
        # A valid trader subdomain is transparently routed via the GatewayProxy
        response = self.client.get(
            "/api/orders?symbol=EURUSD",
            headers={"Host": "julio.savisor.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-forwarded-mock"), "true")
        self.assertEqual(response.text, "Forwarded to port 8001 path api/orders")

    def test_valid_trader_subdomain_with_port_is_forwarded(self):
        # Port suffixes (e.g. from local test uvicorn runs) are stripped and parsed correctly
        response = self.client.get(
            "/api/orders",
            headers={"Host": "julio.savisor.com:8000"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "Forwarded to port 8001 path api/orders")

    def test_nonexistent_trader_subdomain_returns_404(self):
        # An unprovisioned trader subdomain immediately returns a clean, secure 404
        response = self.client.get(
            "/api/orders",
            headers={"Host": "luis.savisor.com"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not provisioned", response.json()["detail"])

    def test_fallback_to_standard_routes_for_unrelated_hosts(self):
        # Requests accessing the service directly (e.g. localhost, direct IP) fall back to central routers
        async def mock_load():
            return {}

        self.store.load = mock_load

        response = self.client.get(
            "/traders",
            headers={"Host": "localhost:8000"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("traders", response.json())
