import asyncio
import typer
import logging
import sys
if sys.platform == "win32":
    # Принудительно устанавливаем политику, которая использует SelectorEventLoop.
    # Это решает проблему с ProactorEventLoop по умолчанию в Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from sensory_data_client.config import get_settings
from sensory_data_client import create_data_client
from sensory_data_client.exceptions import DataClientError
from sensory_data_client.utils.cli_utils import get_rich_console

# ИМПОРТИРУЕМ Base из ORM и create_async_engine
from sensory_data_client.db.base import Base
from sqlalchemy.ext.asyncio import create_async_engine


app = typer.Typer(help="CLI for sensory-data-client management.")
logger = logging.getLogger(__name__)
console = get_rich_console()

@app.command()
def init():
    """
    Initializes all necessary services: creates DB tables and ensures MinIO bucket exists.
    """
    console.rule("[bold cyan]Service Initialization[/bold cyan]")
    
    # 1. DB Table Creation
    with console.status("Creating PostgreSQL tables...", spinner="dots"):
        async def _create_tables():
            try:
                settings = get_settings()
                engine = create_async_engine(settings.postgres.get_pg_dsn())
                
                # Вот замена Alembic:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                
                await engine.dispose()
                console.log("[bold green]✔[/bold green] Database tables created successfully.")
            except Exception as e:
                console.log(f"[bold red]✖[/bold red] Database initialization FAILED: {e}")
                raise typer.Exit(code=1)
        
        asyncio.run(_create_tables())

    # 2. MinIO Bucket (остается без изменений)
    with console.status("Initializing MinIO storage bucket...", spinner="dots"):
        async def _init_storage():
            try:
                client = create_data_client()
                await client.minio.check_connection()
                console.log(f"[bold green]✔[/bold green] MinIO bucket '{client.minio._bucket}' is ready.")
            except DataClientError as e:
                console.log(f"[bold red]✖[/bold red] MinIO storage initialization FAILED: {e}")
                raise typer.Exit(code=1)
        asyncio.run(_init_storage())
    
    console.print("\n[bold green]✅ All services initialized successfully![/bold green]")

@app.command()
def check():
    """Checks connectivity to all external services (PostgreSQL, MinIO)."""
    # Эта команда остается без изменений
    console.rule("[bold cyan]Connection Check[/bold cyan]")
    async def _check():
        client = create_data_client()
        statuses = await client.check_connections()
        
        pg_status = statuses.get("postgres", "unknown error")
        if pg_status == "ok":
            console.print("[bold green]✔[/bold green] PostgreSQL connection: OK")
        else:
            console.print(f"[bold red]✖[/bold red] PostgreSQL connection: FAILED ({pg_status})")

        minio_status = statuses.get("minio", "unknown error")
        if minio_status == "ok":
            console.print(f"[bold green]✔[/bold green] MinIO connection: OK (bucket: '{client.minio._bucket}')")
        else:
            console.print(f"[bold red]✖[/bold red] MinIO connection: FAILED ({minio_status})")

    asyncio.run(_check())