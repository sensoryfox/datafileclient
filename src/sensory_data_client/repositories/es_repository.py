# sensory_data_client/repositories/elasticsearch_repository.py
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel
from elasticsearch import AsyncElasticsearch, ApiError
from sensory_data_client.config import ElasticsearchConfig

from sensory_data_client.models.line import ESLine

logger = logging.getLogger(__name__)


class ElasticsearchRepository:
    def __init__(self, cfg: ElasticsearchConfig):
        self._cfg = cfg
        auth = None
        if cfg.api_key:
            auth = {"api_key": cfg.api_key}
        elif cfg.username and cfg.password:
            auth = (cfg.username, cfg.password)
        self._es = AsyncElasticsearch(
            cfg.endpoint,
            basic_auth=auth if isinstance(auth, tuple) else None,
            api_key=auth["api_key"] if isinstance(auth, dict) else None,
            verify_certs=cfg.verify_certs,
            request_timeout=cfg.request_timeout,
        )
        self._index_lines = cfg.index_lines
        self._index_docs = cfg.index_docs

    async def check_connection(self) -> bool:
        try:
            ok = await self._es.ping()
            logger.info("Elasticsearch ping: %s", ok)
            return bool(ok)
        except Exception as e:
            logger.exception("Elasticsearch ping failed: %s", e)
            return False

    async def get_lines_with_vectors(
        self,
        doc_id: UUID | str,
        include_types: Optional[List[str]] = None,
        exclude_types: Optional[List[str]] = None,
        fields: Optional[List[str]] = None,
        limit: Optional[int] = None,
        sort_by: str = "position",
        ascending: bool = True,
    ) -> List[ESLine]:
        """
        Возвращает построчные документы из ES с векторами.
        Требует, чтобы поле 'vector' было в _source (или замените на своё имя).
        """
        if fields is None:
            fields = [
                "line_id","doc_id","text_content","block_type","position",
                "page_idx","sheet_name","hierarchy","vector","source_line_id",
            ]
        size = min(self._cfg.max_page_size, limit or self._cfg.max_page_size)
        collected: List[ESLine] = []
        search_after = None
        total_wanted = limit or 10_000_000

        must_filters: List[Dict[str, Any]] = [{"term": {"doc_id": str(doc_id)}}]
        if include_types:
            must_filters.append({"terms": {"block_type.keyword": include_types}})
        if exclude_types:
            must_filters.append({"bool": {"must_not": {"terms": {"block_type.keyword": exclude_types}}}})

        sort = [{sort_by: "asc" if ascending else "desc"}, {"_doc": "asc"}]

        while len(collected) < total_wanted:
            body = {
                "query": {"bool": {"filter": must_filters}},
                "size": size,
                "_source": fields,
                "sort": sort,
            }
            if search_after:
                body["search_after"] = search_after
            try:
                res = await self._es.search(index=self._index_lines, body=body)
            except ApiError as e:
                logger.exception("ES search error: %s", e)
                break

            hits = res.get("hits", {}).get("hits", [])
            if not hits:
                break

            for h in hits:
                src = h.get("_source", {})
                try:
                    collected.append(ESLine.model_validate(src))
                except Exception:
                    # Подстрахуемся на несовпадения схемы
                    collected.append(ESLine(
                        line_id=src.get("line_id") or h["_id"],
                        doc_id=src.get("doc_id"),
                        text_content=src.get("text_content"),
                        block_type=src.get("block_type"),
                        position=src.get("position"),
                        page_idx=src.get("page_idx"),
                        sheet_name=src.get("sheet_name"),
                        hierarchy=src.get("hierarchy"),
                        vector=src.get("vector"),
                        source_line_id=src.get("source_line_id"),
                    ))
                if len(collected) >= total_wanted:
                    break

            search_after = hits[-1]["sort"]

        return collected