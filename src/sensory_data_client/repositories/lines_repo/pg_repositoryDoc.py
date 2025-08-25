from __future__ import annotations
from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sensory_data_client.db import DocumentLineORM

class DocumentDetailsRepository:
    async def delete_by_doc_in_session(self, session: AsyncSession, doc_id: UUID):
        await session.execute(delete(DocumentLineORM).where(DocumentLineORM.doc_id == doc_id))

    async def bulk_insert_in_session(self, session: AsyncSession, values: List[Dict[str, Any]]):
        if not values:
            return
        await session.execute(pg_insert(DocumentLineORM).values(values))