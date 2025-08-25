from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy import text

class AsyncUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self):
        self.session = self._sf()
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.__aexit__(exc_type, exc, tb)

    async def advisory_lock_doc(self, doc_id: UUID | str | None):
        """Транзакционный advisory-lock по doc_id (строкой). Безопасно при параллельных редактированиях."""
        if not doc_id:
            return
        await self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": str(doc_id)})