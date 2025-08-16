# Файл: sensory_data_client/db/triggers.py
from sqlalchemy import DDL, event
from .documents.document_orm import DocumentORM
from .documents.documentLine_orm import DocumentLineORM

# --- Триггер для обновления поля 'edited' ---

# ✅ РЕШЕНИЕ: Разделяем КАЖДУЮ команду на свой собственный DDL объект.

# 1. DDL для создания функции (это одна команда, все в порядке)
create_update_function_ddl = DDL("""
    CREATE OR REPLACE FUNCTION update_edited_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.edited = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
""")

# 2. DDL для УДАЛЕНИЯ старого триггера (отдельная команда)
drop_update_trigger_ddl = DDL("""
    DROP TRIGGER IF EXISTS trg_documents_update_edited ON documents;
""")

# 3. DDL для СОЗДАНИЯ нового триггера (отдельная команда)
create_update_trigger_ddl = DDL("""
    CREATE TRIGGER trg_documents_update_edited
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_edited_column();
""")


# --- Триггер для pg_notify ---

# 4. DDL для создания функции уведомления (одна команда)
create_notify_function_ddl = DDL("""
    CREATE OR REPLACE FUNCTION notify_new_document()
    RETURNS trigger AS $$
    DECLARE
        payload JSON;
    BEGIN
        payload = json_build_object('doc_id', NEW.id::text, 'file_name', NEW.name);
        PERFORM pg_notify('docparser_new_doc', payload::text);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
""")

# 5. DDL для УДАЛЕНИЯ старого триггера уведомления
drop_notify_trigger_ddl = DDL("""
    DROP TRIGGER IF EXISTS trg_documents_after_insert ON documents;
""")

# 6. DDL для СОЗДАНИЯ нового триггера уведомления
create_notify_trigger_ddl = DDL("""
    CREATE TRIGGER trg_documents_after_insert
    AFTER INSERT ON documents
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_document();
""")


# --- "Привязываем" все DDL к событию "after_create" для таблицы DocumentORM ---
# SQLAlchemy выполнит их последовательно, один за другим.

# Слушатели для триггера 'edited'
event.listen(DocumentORM.__table__, "after_create", create_update_function_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentORM.__table__, "after_create", drop_update_trigger_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentORM.__table__, "after_create", create_update_trigger_ddl.execute_if(dialect="postgresql"))

# Слушатели для триггера 'notify'
event.listen(DocumentORM.__table__, "after_create", create_notify_function_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentORM.__table__, "after_create", drop_notify_trigger_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentORM.__table__, "after_create", create_notify_trigger_ddl.execute_if(dialect="postgresql"))


# 1. DDL для создания функции, которая парсит строку и создает задачу
create_image_upsert_function_ddl = DDL("""
CREATE OR REPLACE FUNCTION upsert_document_image_from_line()
RETURNS trigger AS $$
DECLARE
    v_filename text;
    v_extension text;
    v_object_key text;
    v_image_hash text;
    v_image_id uuid;
BEGIN
    -- Работаем только если это строка с типом 'image_placeholder'
    IF NEW.block_type IS NULL OR NEW.block_type <> 'image_placeholder' THEN
        RETURN NEW;
    END IF;

    -- Извлекаем имя файла из markdown-разметки: ![...](filename.png)
    -- Используем regexp_matches, который возвращает массив; берем первый элемент
    SELECT (regexp_matches(NEW.content, '!\\[[^\\]]*\\]\\(([^)]+)\\)'))[1]
    INTO v_filename;

    -- Если имя файла не найдено, выходим
    IF v_filename IS NULL OR length(v_filename) = 0 THEN
        RETURN NEW;
    END IF;

    -- Находим расширение исходного документа (pdf, docx) для построения полного пути
    SELECT sf.extension INTO v_extension
    FROM documents d
    JOIN stored_files sf ON sf.id = d.stored_file_id
    WHERE d.id = NEW.doc_id;

    -- Если по какой-то причине расширение не найдено
    IF v_extension IS NULL THEN
        v_extension := 'unknown';
    END IF;

    -- Хеш изображения = имя файла без расширения (для дедупликации)
    v_image_hash := regexp_replace(v_filename, '\\.[^.]+$', '', 'g');

    -- Собираем полный путь к объекту в MinIO
    v_object_key := v_extension || '/' || replace(NEW.doc_id::text, '-', '') || '/images/' || v_filename;

    -- UPSERT: Вставляем новую запись или обновляем существующую.
    -- Это гарантирует, что для одной и той же картинки в документе будет только одна задача.
    -- Если парсер пересоздает строки, мы просто обновим ссылку на новую source_line_id.
    -- Также сбрасываем статус 'failed' для повторной попытки обработки.
    INSERT INTO document_images (doc_id, source_line_id, object_key, filename, image_hash, status, attempts)
    VALUES (NEW.doc_id, NEW.id, v_object_key, v_filename, v_image_hash, 'pending', 0)
    ON CONFLICT (doc_id, image_hash)
    DO UPDATE SET
        source_line_id = EXCLUDED.source_line_id,
        updated_at = now(),
        -- Эта часть у вас уже идеальна, она сбрасывает failed задачи на pending
        status = CASE WHEN document_images.status = 'failed' THEN 'pending' ELSE document_images.status END
    RETURNING id INTO v_image_id;

    -- Отправляем уведомление диспетчеру с ID созданной/обновленной задачи
    PERFORM pg_notify('image_jobs', json_build_object('image_id', v_image_id::text)::text);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

# 2. DDL для удаления старого триггера (для идемпотентности)
drop_image_upsert_trigger_ddl = DDL("""
    DROP TRIGGER IF EXISTS trg_document_lines_image_upsert ON document_lines;
""")

# 3. DDL для создания нового триггера
create_image_upsert_trigger_ddl = DDL("""
    CREATE TRIGGER trg_document_lines_image_upsert
    AFTER INSERT OR UPDATE OF block_type, content ON document_lines
    FOR EACH ROW
    EXECUTE FUNCTION upsert_document_image_from_line();
""")
# --- "Привязываем" все DDL к событию "after_create" для таблицы DocumentLineORM ---
# SQLAlchemy выполнит их последовательно, один за другим.

event.listen(DocumentLineORM.__table__, "after_create", create_image_upsert_function_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentLineORM.__table__, "after_create", drop_image_upsert_trigger_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentLineORM.__table__, "after_create", create_image_upsert_trigger_ddl.execute_if(dialect="postgresql"))



print("[sensory-data-client] Database triggers registered for DocumentORM.")