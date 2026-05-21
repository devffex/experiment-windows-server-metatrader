from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import String, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


@dataclass
class TraderMapping:
    """Typed representation of a single trader's configuration."""

    port: int
    password: str
    rdp_profile: str
    organization: str
    trader_name: str


class Base(DeclarativeBase):
    pass


class TraderMappingModel(Base):
    __tablename__ = "trader_mappings"

    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    port: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    rdp_profile: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str] = mapped_column(String(100), nullable=False)
    trader_name: Mapped[str] = mapped_column(String(100), nullable=False)


class TraderStore:
    """PostgreSQL Manager using SQLAlchemy Async Engine to handle persistent user mappings."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def initialize_db(self) -> None:
        """Create the database tables if they do not exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose of the database engine."""
        await self.engine.dispose()

    async def load(self) -> Dict[str, TraderMapping]:
        """Load all trader mappings from PostgreSQL."""
        async with self.session_factory() as session:
            result = await session.execute(select(TraderMappingModel))
            models = result.scalars().all()
            return {
                model.username: TraderMapping(
                    port=model.port,
                    password=model.password,
                    rdp_profile=model.rdp_profile,
                    organization=model.organization,
                    trader_name=model.trader_name,
                )
                for model in models
            }

    async def get_trader(self, username: str) -> Optional[TraderMapping]:
        """Get a single trader's mapping, or None if not found."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(TraderMappingModel).where(TraderMappingModel.username == username)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            return TraderMapping(
                port=model.port,
                password=model.password,
                rdp_profile=model.rdp_profile,
                organization=model.organization,
                trader_name=model.trader_name,
            )

    async def upsert_trader(self, username: str, mapping: TraderMapping) -> None:
        """Add or update a trader mapping in PostgreSQL."""
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(TraderMappingModel).where(TraderMappingModel.username == username)
                )
                model = result.scalar_one_or_none()
                if model:
                    model.port = mapping.port
                    model.password = mapping.password
                    model.rdp_profile = mapping.rdp_profile
                    model.organization = mapping.organization
                    model.trader_name = mapping.trader_name
                else:
                    new_model = TraderMappingModel(
                        username=username,
                        port=mapping.port,
                        password=mapping.password,
                        rdp_profile=mapping.rdp_profile,
                        organization=mapping.organization,
                        trader_name=mapping.trader_name,
                    )
                    session.add(new_model)
                await session.commit()

    async def remove_trader(self, username: str) -> bool:
        """Remove a trader mapping. Returns True if the trader existed."""
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(TraderMappingModel).where(TraderMappingModel.username == username)
                )
                model = result.scalar_one_or_none()
                if not model:
                    return False
                await session.delete(model)
                await session.commit()
                return True

    async def get_next_port(self, port_start: int, port_end: int) -> int:
        """Find the next available port in the configured range."""
        mappings = await self.load()
        used_ports = {m.port for m in mappings.values()}
        for port in range(port_start, port_end + 1):
            if port not in used_ports:
                return port
        raise RuntimeError(
            f"All ports in range {port_start}-{port_end} are exhausted. "
            f"{len(used_ports)} traders provisioned."
        )
