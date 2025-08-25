# Файл: sensory_data_client/db/triggers.py
from sqlalchemy import DDL, event
from .documents.document_orm import DocumentORM
from .documents.lines.documentLine_orm import DocumentLineORM

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
CREATE OR REPLACE FUNCTION upsert_image_details_from_raw_line()
RETURNS trigger AS $$
DECLARE
  v_filename   TEXT;
  v_image_hash  TEXT;
  v_extension  TEXT;
  v_object_path TEXT;
BEGIN
  -- Только для блоков-картинок
  IF NEW.block_type IS NULL OR NEW.block_type <> 'image_placeholder' THEN
    RETURN NEW;
  END IF;

  -- Извлекаем имя файла из markdown: ![...] (filename.png)
  SELECT (regexp_matches(NEW.content, '!\\[[^\\]]*\\]\\(([^)]+)\\)'))[1]
  INTO v_filename;

  IF v_filename IS NULL OR length(v_filename) = 0 THEN
    RETURN NEW;
  END IF;

  -- Получаем расширение исходного документа
  SELECT sf.extension INTO v_extension
  FROM documents d
  JOIN stored_files sf ON sf.id = d.stored_file_id
  WHERE d.id = NEW.doc_id;

  v_extension := COALESCE(v_extension, 'bin');

  -- Хеш = имя без расширения
  v_image_hash := regexp_replace(v_filename, '\\.[^.]+$', '', 'g');

  -- Собираем путь к объекту (не сохраняем в БД; только для нотификации/воркера)
  v_object_path := v_extension || '/' || replace(NEW.doc_id::text, '-', '') || '/images/' || v_filename;

  -- UPSERT метаданных в lines_image
  INSERT INTO lines_image (line_id, doc_id, filename, image_hash, status, attempts)
  VALUES (NEW.id, NEW.doc_id, v_filename, v_image_hash, 'pending', 0)
  ON CONFLICT (line_id)
  DO UPDATE SET
    filename  = EXCLUDED.filename,
    image_hash = EXCLUDED.image_hash,
    updated_at = now(),
    status   = CASE WHEN lines_image.status = 'failed' THEN 'pending' ELSE lines_image.status END;

  -- Отправляем уведомление о задаче
  PERFORM pg_notify(
    'image_jobs',
    json_build_object(
      'image_id',  NEW.id::text,
      'doc_id',   NEW.doc_id::text,
      'filename',  v_filename,
      'extension',  v_extension,
      'object_path', v_object_path
    )::text
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

# 2. DDL для удаления старого триггера (для идемпотентности)
drop_image_upsert_trigger_ddl = DDL("""
    DROP TRIGGER IF EXISTS trg_raw_lines_image_upsert ON raw_lines;
""")

# 3. DDL для создания нового триггера
create_image_upsert_trigger_ddl = DDL("""
    CREATE TRIGGER trg_raw_lines_image_upsert
    AFTER INSERT OR UPDATE OF block_type, content ON raw_lines
    FOR EACH ROW
    EXECUTE FUNCTION upsert_image_details_from_raw_line();
""")
# --- "Привязываем" все DDL к событию "after_create" для таблицы DocumentLineORM ---
# SQLAlchemy выполнит их последовательно, один за другим.

event.listen(DocumentLineORM.__table__, "after_create", create_image_upsert_function_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentLineORM.__table__, "after_create", drop_image_upsert_trigger_ddl.execute_if(dialect="postgresql"))
event.listen(DocumentLineORM.__table__, "after_create", create_image_upsert_trigger_ddl.execute_if(dialect="postgresql"))



print("[sensory-data-client] Database triggers registered for DocumentORM.")



# --- DDL для Autotag NOTIFY ---
create_autotag_notify_function_ddl = DDL("""
CREATE OR REPLACE FUNCTION notify_autotag_task()
RETURNS trigger AS $$
DECLARE
    payload JSON;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF COALESCE(NEW.status,'enqueued')::text = 'enqueued' THEN
            payload := json_build_object(
                'task_id', NEW.id::text,
                'doc_id', NEW.doc_id::text,
                'status', NEW.status
            );
            PERFORM pg_notify('autotag_tasks_channel', payload::text);
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        IF COALESCE(NEW.status,'')::text = 'enqueued' AND COALESCE(OLD.status,'')::text <> 'enqueued' THEN
            payload := json_build_object(
                'task_id', NEW.id::text,
                'doc_id', NEW.doc_id::text,
                'status', NEW.status
            );
            PERFORM pg_notify('autotag_tasks_channel', payload::text);
        END IF;
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

drop_autotag_notify_trigger_ddl = DDL("""
DROP TRIGGER IF EXISTS trg_autotag_notify ON autotag_tasks;
""")

create_autotag_notify_trigger_ddl = DDL("""
CREATE TRIGGER trg_autotag_notify
AFTER INSERT OR UPDATE ON autotag_tasks
FOR EACH ROW
EXECUTE FUNCTION notify_autotag_task();
""")

# --- Регистрация обработчиков ---
# Импортируем класс ORM (путь корректируйте под ваш пакет)
from sensory_data_client.db.tags.autotag_task_orm import AutotagTaskORM
event.listen(AutotagTaskORM.__table__, "after_create", create_autotag_notify_function_ddl.execute_if(dialect="postgresql"))
event.listen(AutotagTaskORM.__table__, "after_create", drop_autotag_notify_trigger_ddl.execute_if(dialect="postgresql"))
event.listen(AutotagTaskORM.__table__, "after_create", create_autotag_notify_trigger_ddl.execute_if(dialect="postgresql"))
