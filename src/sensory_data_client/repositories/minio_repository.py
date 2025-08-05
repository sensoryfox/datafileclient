import logging
from io import BytesIO
from typing import Optional

from minio import Minio
from minio.error import S3Error
from datetime import timedelta
from sensory_data_client.exceptions import MinioError
from sensory_data_client.utils.minio_async import run_io_bound
from sensory_data_client.config import MinioConfig
import urllib3 

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MinioRepository:
    def __init__(self, settings: MinioConfig):
        http_client = None
        if settings.secure:
            http_client = urllib3.PoolManager(
                cert_reqs='CERT_NONE',
            )
        print(settings)
        self._client = Minio(
            endpoint=settings.endpoint,
            access_key=settings.accesskey,
            secret_key=settings.secretkey,
            secure=settings.secure,
            http_client=http_client
        )
        self._bucket = settings.bucket

    async def _ensure_bucket(self):
        exists = await run_io_bound(self._client.bucket_exists, self._bucket)
        if not exists:
            await run_io_bound(self._client.make_bucket, self._bucket)


    async def check_connection(self):
        """Проверяет соединение с MinIO и наличие бакета."""
        logger.debug(f"Checking MinIO connection and bucket '{self._bucket}' existence...")
        try:
            await self._ensure_bucket()
            logger.debug("MinIO connection and bucket presence confirmed.")
        except MinioError as e:
            logger.error(f"MinIO connection failed: {e}")
            raise
        
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
        
    async def list_all(self,
                           prefix: str | None = None,
                           recursive: bool = True) -> list[str]:
        """
        Возвращает список всех объектов в бакете (или под-префиксе).
        """
        def _collect():
            # list_objects – генератор, собираем сразу в список
            return [
                obj.object_name
                for obj in self._client.list_objects(
                    self._bucket, prefix=prefix, recursive=recursive
                )
            ]

        return await run_io_bound(_collect)