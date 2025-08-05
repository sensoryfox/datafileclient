import asyncio
from functools import partial
from typing import Any, Callable

async def run_io_bound(func: Callable[..., Any], *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))