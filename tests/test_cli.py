import pytest
from typer.testing import CliRunner
from sqlalchemy import create_engine, inspect

# Убедитесь, что политика для Windows установлена, если тестируете на Windows
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sensory_data_client.cli import app
from sensory_data_client.config import get_settings

runner = CliRunner()

def test_cli_init_and_check():
    """
    Тестирует команды init и check в едином сценарии.
    Тест полностью самодостаточен и не требует фикстур, т.к. тестирует
    консольные команды, которые сами настраивают окружение.
    """
    # --- ACT 1: Запускаем инициализацию ---
    result_init = runner.invoke(app, ["init"])

    # --- ASSERT 1: Проверяем результат init ---
    assert result_init.exit_code == 0, f"Команда 'init' провалилась: {result_init.stdout}"
    assert "Database tables created successfully" in result_init.stdout
    assert "MinIO bucket" in result_init.stdout
    assert "is ready" in result_init.stdout

    # Дополнительная проверка: таблицы действительно созданы в БД
    settings = get_settings()
    sync_dsn = settings.postgres.get_pg_dsn().replace("+asyncpg", "")
    engine = create_engine(sync_dsn)
    inspector = inspect(engine)
    assert inspector.has_table("documents"), "Таблица 'documents' не была создана"
    assert inspector.has_table("document_lines"), "Таблица 'document_lines' не была создана"
    engine.dispose()

    # --- ACT 2: Проверяем статус после инициализации ---
    result_check = runner.invoke(app, ["check"])

    # --- ASSERT 2: Проверяем результат check ---
    assert result_check.exit_code == 0
    assert "PostgreSQL connection: OK" in result_check.stdout
    assert "MinIO connection: OK" in result_check.stdout