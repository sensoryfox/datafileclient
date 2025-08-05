import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..exceptions import DatabaseError
from ..models.document import DocumentInDB, DocumentCreate, Line
from ..db.document_orm import DocumentORM
from ..db.documentLine_orm import DocumentLineORM
from ..db.base import get_session

logger = logging.getLogger(__name__)

class MetaDataRepository:
    
    async def save(self, doc: DocumentInDB) -> DocumentInDB:
        async for session in get_session():
            try:
                orm = DocumentORM(**doc.model_dump(exclude={"metadata"}, metadata_=doc.metadata))
                session.add(orm)
                await session.commit()
                await session.refresh(orm)
                return orm.to_pydantic()
            except IntegrityError as e:
                await session.rollback()
                raise DatabaseError(str(e)) from e

    async def get(self, doc_id: UUID) -> Optional[DocumentInDB]:
        async for session in get_session():
            res = await session.execute(select(DocumentORM).where(DocumentORM.id == doc_id))
            orm = res.scalar_one_or_none()
            return orm.to_pydantic() if orm else None

    async def update(self, doc_id: UUID, patch: dict) -> Optional[DocumentInDB]:
        async for session in get_session():
            try:
                q = (
                    update(DocumentORM)
                    .where(DocumentORM.id == doc_id)
                    .values(**patch, edited=func.now())
                    .returning(DocumentORM)
                )
                res = await session.execute(q)
                await session.commit()
                orm = res.scalar_one_or_none()
                return orm.to_pydantic() if orm else None
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(str(e)) from e

    async def delete(self, doc_id: UUID) -> bool:
        async for session in get_session():
            res = await session.execute(delete(DocumentORM).where(DocumentORM.id == doc_id))
            await session.commit()
            return res.rowcount > 0
