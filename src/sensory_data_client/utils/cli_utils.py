from importlib import resources
from rich.console import Console
from typing import Optional
import re

def get_rich_console() -> Console: return Console(stderr=True)

def parse_image_hash_from_md(content: str) -> Optional[str]:
    """
    Достаем hash из плейсхолдера вида ![](something.png) -> 'something'.
    """
    if not content:
        return None
    m = re.search(r"!\[[^\]]*\]\(([^)]+)\)", content)
    if not m:
        return None
    fname = m.group(1).strip().split("/")[-1]
    if "." in fname:
        return fname.split(".")[0] or None
    return None