import pytest
from uuid import uuid4
from sensory_data_client.models.document import DocumentCreate, DocumentMetadata
from sensory_data_client.client import DataClient
from sensory_data_client.exceptions import DocumentNotFoundError

# Помечаем все тесты в этом файле для работы с asyncio
pytestmark = pytest.mark.asyncio

async def test_full_lifecycle(data_client: DataClient):
    """
    Проверяет полный жизненный цикл документа: загрузка, получение, листинг, удаление.
    """
    # --- ARRANGE ---
    file_content = b"This is a test file for the full lifecycle."
    file_name = "lifecycle.log"
    doc_meta = DocumentCreate(
        user_document_id="user-doc-123",
        name=file_name,
        owner="tester",
        access_group="test-group",
        extension="log",
        metadata=DocumentMetadata(extra={"source": "pytest"})
    )

    # 1. Загрузка файла
    # --- ACT ---
    saved_doc = await data_client.upload_file(file_name, file_content, doc_meta)

    # --- ASSERT ---
    assert saved_doc.id is not None
    assert saved_doc.name == file_name
    assert saved_doc.owner == "tester"
    assert saved_doc.metadata.extra == {"source": "pytest"}
    assert saved_doc.content_hash is not None

    # 2. Получение файла
    # --- ACT ---
    retrieved_content = await data_client.get_file(saved_doc.id)

    # --- ASSERT ---
    assert retrieved_content == file_content

    # 3. Листинг документов
    # --- ACT ---
    all_docs = await data_client.list_doc()

    # --- ASSERT ---
    assert len(all_docs) == 1
    assert all_docs[0].id == saved_doc.id

    # 4. Удаление файла
    # --- ACT ---
    await data_client.delete_file(saved_doc.id)

    # --- ASSERT ---
    # Убеждаемся, что документ действительно удален
    docs_after_delete = await data_client.list_doc()
    assert len(docs_after_delete) == 0

    # Попытка получить удаленный файл должна вызвать ошибку
    with pytest.raises(DocumentNotFoundError):
        await data_client.get_file(saved_doc.id)


async def test_get_nonexistent_file(data_client: DataClient):
    """Проверяет, что при запросе несуществующего файла возникает DocumentNotFoundError."""
    # --- ARRANGE ---
    non_existent_id = uuid4()

    # --- ACT & ASSERT ---
    with pytest.raises(DocumentNotFoundError):
        await data_client.get_file(non_existent_id)