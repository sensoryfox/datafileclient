import logging
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error
from datetime import timedelta
from ..exceptions import MinioError
from ..config import settings
from ..utils.minio_async import run_io_bound

logger = logging.getLogger(__name__)

class MinioRepository:
    def __init__(self):
        self._client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket

    async def _ensure_bucket(self):
        exists = await run_io_bound(self._client.bucket_exists, self._bucket)
        if not exists:
            await run_io_bound(self._client.make_bucket, self._bucket)

    async def put_object(self, object_name: str, data: bytes, content_type: str | None = None):
        await self._ensure_bucket()
        try:
            await run_io_bound(
                self._client.put_object,
                self._bucket,
                object_name,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )
        except S3Error as e:
            raise MinioError(str(e)) from e

    async def get_object(self, object_name: str) -> bytes:
        try:
            resp = await run_io_bound(self._client.get_object, self._bucket, object_name)
            data = resp.read()
            resp.close()
            resp.release_conn()
            return data
        except S3Error as e:
            raise MinioError(str(e)) from e

    async def remove_object(self, object_name: str):
        try:
            await run_io_bound(self._client.remove_object, self._bucket, object_name)
        except S3Error as e:
            raise MinioError(str(e)) from e
    
    async def get_presigned_url(self, object_name: str, expires_in_seconds: int = 3600) -> str:
        """Генерирует временную ссылку для скачивания объекта."""
        try:
            url = await run_io_bound(
                self._client.presigned_get_object,
                self._bucket,
                object_name,
                expires=timedelta(seconds=expires_in_seconds),
            )
            return url
        except S3Error as e:
            raise MinioError(str(e)) from e