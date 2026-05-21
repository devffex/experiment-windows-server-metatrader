from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class TraderMapping:
    """Typed representation of a single trader's configuration."""

    port: int
    password: str
    rdp_profile: str
    organization: str
    trader_name: str


class TraderStore:
    """Thread-safe manager for trader port/credential mappings stored on disk.

    Uses an asyncio lock to serialize concurrent access and atomic file writes
    (write to temp file then os.replace) to prevent corruption on crash.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def load(self) -> Dict[str, TraderMapping]:
        """Load all trader mappings from disk."""
        async with self._lock:
            return self._load_sync()

    def _load_sync(self) -> Dict[str, TraderMapping]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text())
            return {
                k: TraderMapping(**v) for k, v in raw.items()
            }
        except Exception:
            return {}

    async def save(self, mappings: Dict[str, TraderMapping]) -> None:
        """Persist trader mappings to disk with an atomic write."""
        async with self._lock:
            self._save_sync(mappings)

    def _save_sync(self, mappings: Dict[str, TraderMapping]) -> None:
        raw = {k: asdict(v) for k, v in mappings.items()}
        content = json.dumps(raw, indent=4)
        dir_path = self.path.parent if self.path.parent != Path(".") else Path.cwd()
        fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp_path, str(self.path))
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    async def get_trader(self, username: str) -> Optional[TraderMapping]:
        """Get a single trader's mapping, or None if not found."""
        mappings = await self.load()
        return mappings.get(username)

    async def add_trader(self, username: str, mapping: TraderMapping) -> None:
        """Add a trader mapping. Raises ValueError if already exists."""
        async with self._lock:
            mappings = self._load_sync()
            if username in mappings:
                raise ValueError(f"Trader '{username}' already provisioned.")
            mappings[username] = mapping
            self._save_sync(mappings)

    async def upsert_trader(self, username: str, mapping: TraderMapping) -> None:
        """Add or update a trader mapping."""
        async with self._lock:
            mappings = self._load_sync()
            mappings[username] = mapping
            self._save_sync(mappings)

    async def remove_trader(self, username: str) -> bool:
        """Remove a trader mapping. Returns True if the trader existed."""
        async with self._lock:
            mappings = self._load_sync()
            if username not in mappings:
                return False
            del mappings[username]
            self._save_sync(mappings)
            return True

    async def get_next_port(self, port_start: int, port_end: int) -> int:
        """Find the next available port in the configured range.

        Raises RuntimeError if all ports are exhausted.
        """
        mappings = await self.load()
        used_ports = {m.port for m in mappings.values()}
        for port in range(port_start, port_end + 1):
            if port not in used_ports:
                return port
        raise RuntimeError(
            f"All ports in range {port_start}-{port_end} are exhausted. "
            f"{len(used_ports)} traders provisioned."
        )
