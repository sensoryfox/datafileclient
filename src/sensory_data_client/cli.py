# src/data_client/cli.py
import asyncio
import typer
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text 

from .config import settings
from .init import init_minio, init_postgres
from .repositories.minio_repository import MinioRepository 

app = typer.Typer()

async def _check_pg_connection():
    """Асинхронно проверяет подключение к PostgreSQL."""
    typer.echo("Checking PostgreSQL connection...")
    engine = create_async_engine(settings.pg_dsn)
    try:
        async with engine.connect() as conn:
            # Выполняем простой запрос, чтобы убедиться в подключении
            await conn.execute(text("SELECT 1"))
        typer.secho("PostgreSQL connection OK.", fg=typer.colors.GREEN)
        return True
    except Exception as e:
        typer.secho(f"PostgreSQL connection FAILED: {e}", fg=typer.colors.RED)
        return False
    finally:
        await engine.dispose() # Важно закрывать пул соединений


async def _check_minio_connection():
    """Асинхронно проверяет подключение к MinIO."""
    typer.echo("\nChecking MinIO connection...")
    minio_repo = MinioRepository()
    try:
        # Метод _ensure_bucket идеально подходит для проверки
        await minio_repo._ensure_bucket()
        typer.secho("MinIO connection OK.", fg=typer.colors.GREEN)
        return True
    except Exception as e:
        typer.secho(f"MinIO connection FAILED: {e}", fg=typer.colors.RED)
        return False


@app.command()
def check_connections():
    """Проверяет доступность PostgreSQL и MinIO."""
    
    async def main():
        await _check_pg_connection()
        await _check_minio_connection()

    asyncio.run(main())


@app.command()
def init_all():
    """Запускает полную инициализацию: создает бакет и применяет миграции."""
    typer.echo("Running full initialization...")
    try:
        asyncio.run(init_minio())
        init_postgres()
        typer.secho("Initialization successful!", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Initialization FAILED: {e}", fg=typer.colors.RED)


if __name__ == "__main__":
    app()