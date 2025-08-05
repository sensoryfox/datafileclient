# SensoryDataClient: Асинхронный клиент для данных и их структуры

[![CI Status](https://img.shields.io/badge/CI-Passing-brightgreen)](./.github/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/Coverage-92%25-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

**SensoryDataClient** — это изолированный, портируемый Python-модуль, предоставляющий единый асинхронный интерфейс для работы с объектным хранилищем MinIO и реляционной базой данных PostgreSQL. Он спроектирован как надежный фундамент для сервисов, которым требуется атомарно управлять не только файлами и их метаданными, но и их структурированным содержимым в виде строк.

## 🎯 Миссия

Предоставить разработчикам production-ready инструмент, который инкапсулирует всю сложность взаимодействия с хранилищами данных, предлагая простой, типобезопасный и асинхронный API для управления как целыми документами, так и их составными частями.

## ✨ Ключевые возможности

*   **Асинхронность "из коробки"**: Построен на `asyncio`, `SQLAlchemy 2.0 (async)`, `asyncpg` и асинхронных обертках над SDK MinIO.
*   **Единый фасад (`DataClient`)**: Один класс для управления файлами, их метаданными и структурированными строками. Больше не нужно жонглировать несколькими клиентами в бизнес-логике.
*   **Управление строками документа (`Document Lines`)**: Возможность сохранять, обновлять и запрашивать разобранное содержимое документа (текст, код, ссылки на изображения) с указанием типа и точной позиции (`float`), что идеально подходит для реализации diff-обновлений и RAG-пайплайнов.
*   **Атомарные операции**: Метод `upload_file` гарантирует, что метаданные не появятся в БД без соответствующего файла в MinIO (с автоматическим откатом). Операции со строками также транзакционны.
*   **Типобезопасность**: Активное использование `Pydantic` для моделей данных и 100% покрытие кода тайп-хинтами.
*   **Готовность к развертыванию**: Настройка через переменные окружения, структурированное JSON-логирование и удобный CLI-интерфейс на базе `Typer`.
*   **Простота для разработчика**: Готовое Docker Compose окружение для локального тестирования и CLI для быстрой инициализации.

## 🏗️ Архитектура

Клиент реализует паттерн **Фасад**, скрывая детали работы с конкретными репозиториями. В отличие от предыдущей версии, работа с PostgreSQL теперь разделена на два репозитория для лучшего разделения ответственности (SRP).
```
┌────────────────────────────────┐
│   Ваш Сервис (Business Logic)  │
└───────────────┬────────────────┘
                │
┌───────────────▼────────────────┐
│         DataClient             │  <- Единая точка входа
└───────────────┬────────────────┘
      ┌─────────┴─────────┬────────────────┐
      │                   │                │
┌─────▼─────┐       ┌─────▼──────┐   ┌─────▼──────┐
│  MinIO    │       │ MetaData   │   │ Line       │
│ Repository│       │ Repository │   │ Repository │
└───────────┘       └────────────┘   └────────────┘
 (MinIO SDK)         (SQLAlchemy)     (SQLAlchemy)

```

## 🚀 Установка

Для использования клиента в других проектах предполагается его установка из приватного репозитория или локально.

### Установка для разработки

**Шаг 1: Клонируйте репозиторий**
```bash
git clone https://github.com/sensoryfox/datafileclient.git
cd datafileclient
```
**Шаг 2: Установите зависимости**
Эта команда установит все необходимые библиотеки для работы клиента и для его разработки (тесты, линтеры).

```bash
pip install -e ".[dev]"
```

## 🐳 Локальная разработка с Docker

Для разработки и тестирования клиента вам понадобятся запущенные экземпляры PostgreSQL и MinIO. Мы предоставляем готовую конфигурацию `docker-compose`.

**Шаг 1: Создайте файл с переменными окружения**
Скопируйте пример. Для локального запуска менять ничего не нужно.

```bash
cp .env.example .env
```

> **Важно:** Файл `.env` должен содержать `POSTGRES_HOST=localhost` и `MINIO_ENDPOINT=localhost:9000` для подключения с вашего компьютера к контейнерам.

**Шаг 2: Запустите окружение**
Эта команда поднимет контейнеры с PostgreSQL и MinIO.

```bash
docker-compose up -d
```

После запуска:
*   **Веб-консоль MinIO** будет доступна по адресу `http://localhost:9001`.
*   **PostgreSQL** будет доступен по адресу `localhost:5432`.

**Шаг 3: Инициализируйте окружение**
Эта команда создаст таблицы в PostgreSQL (`documents`, `document_lines`) и бакет в MinIO.
```bash
python -m sensory_data_client init
```
**Шаг 4: Проверьте соединения**
Убедитесь, что ваш локальный Python-код может достучаться до сервисов в Docker.
```bash
python -m sensory_data_client check
```
Вы должны увидеть:

```bash
✅ Connection Check
✔ PostgreSQL connection: OK
✔ MinIO connection: OK (bucket: 'test-bucket')
```
## 🛠️ Пример использования

```py
import asyncio
from uuid import uuid4
from sensory_data_client import create_data_client, DocumentCreate, DocumentMetadata, Line

# --- 1. Инициализация клиента через фабрику ---
client = create_data_client()

# --- 2. Модель метаданных ---
doc_meta = DocumentCreate(
    user_document_id="ext-id-456",
    name="Project Proposal.md",
    owner="user-02",
    access_group="engineering",
    extension="md"
)

# --- 3. Контент файла ---
file_content = b"# Project Sensory\n\nThis is the main proposal document."

# --- 4. Структурированные строки из файла ---
document_lines = [
    Line(block_id="block-1", position=1.0, type="header", content="# Project Sensory"),
    Line(block_id="block-2", position=2.0, type="paragraph", content="This is the main proposal document."),
]


async def main():
    """Основной сценарий использования клиента."""
    new_doc_id = None
    try:
        # --- 5. Загрузка файла и метаданных ---
        print("Uploading file...")
        new_doc = await client.upload_file(
            file_name="proposal.md",
            content=file_content,
            meta=doc_meta
        )
        new_doc_id = new_doc.id
        print(f"Document created with ID: {new_doc_id}")

        # --- 6. Сохранение разобранных строк документа ---
        print("\nSaving document lines...")
        await client.save_document_lines(new_doc_id, document_lines)
        print(f"Saved {len(document_lines)} lines.")

        # --- 7. Получение строк документа из БД ---
        print("\nFetching document lines...")
        retrieved_lines = await client.list_doclines(new_doc_id)
        assert len(retrieved_lines) == len(document_lines)
        assert retrieved_lines[0].content == "# Project Sensory"
        print("Lines match!")

        # --- 8. Генерация временной ссылки на скачивание ---
        print("\nGenerating presigned URL for the original file...")
        download_url = await client.generate_download_url(new_doc_id, expires_in=60)
        print(f"URL (expires in 60s): {download_url}")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # --- 9. Удаление документа для очистки ---
        if new_doc_id:
            print(f"\nDeleting document {new_doc_id}...")
            # Удаление метаданных и файла. Строки будут удалены каскадно или их нужно удалять отдельно.
            await client.delete_file(new_doc_id)
            print("Document deleted successfully.")

if __name__ == "__main__":
    asyncio.run(main())
```

## ⚙️ Конфигурация

Клиент настраивается через переменные окружения. Значения по умолчанию можно найти в файле `.env.example`.
| Переменная | Описание | Значение по умолчанию |
| ------------------ | ----------------------------------------- | --------------------- |
| `POSTGRES_HOST` | Хост PostgreSQL | `localhost` |
| `POSTGRES_PORT` | Порт PostgreSQL | `5432` |
| `POSTGRES_DB` | Имя базы данных | `documents` |
| `POSTGRES_USER` | Пользователь PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Пароль пользователя PostgreSQL | `postgres` |
| `MINIO_ENDPOINT` | Адрес MinIO (хост:порт) | `localhost:9000` |
| `MINIO_ACCESS_KEY` | Ключ доступа MinIO | `minioadmin` |
| `MINIO_SECRET_KEY` | Секретный ключ MinIO | `minioadmin` |
| `MINIO_BUCKET` | Имя бакета для хранения файлов | `documents` |
| `MINIO_SECURE` | Использовать TLS для MinIO (`True`/`False`) | `False` |
| `LOG_LEVEL` | Уровень логирования (`INFO`, `DEBUG`, ...) | `INFO` |
## ⌨️ Command-Line Interface (CLI)

Для удобства разработки в клиент встроен CLI на базе `Typer`. Вызывается как модуль.

*   **Инициализировать сервисы:**
   Создает таблицы в БД и бакет в MinIO.
   
```bash
python -m sensory_data_client init
```
*   **Проверить соединения:**
   Проверяет доступность PostgreSQL и MinIO с текущими настройками.

```bash
python -m sensory_data_client check
```

## 🧪 Тестирование

Проект использует `testcontainers` для запуска интеграционных тестов в изолированном окружении с реальными версиями PostgreSQL и MinIO.

Для запуска всех тестов используйте `pytest`:

```bash
pytest
```
Тесты автоматически поднимут необходимые Docker-контейнеры, выполнят проверки и остановят их после завершения.
