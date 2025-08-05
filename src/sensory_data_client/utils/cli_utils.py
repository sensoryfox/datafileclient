from importlib import resources
from rich.console import Console
def get_rich_console() -> Console: return Console(stderr=True)