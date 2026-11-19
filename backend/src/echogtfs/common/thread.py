import asyncio
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable


def _call_with_thread_name(name: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    thread = threading.current_thread()
    previous_name = thread.name
    thread.name = name
    try:
        return func(*args, **kwargs)
    finally:
        thread.name = previous_name


async def create_named_thread(name: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Like asyncio.to_thread, but the worker thread carries a descriptive name while running func."""
    return await asyncio.to_thread(_call_with_thread_name, name, func, *args, **kwargs)


def create_named_worker_process(name: str) -> None:
    """Process pool initializer naming the worker process and its main thread."""
    process = multiprocessing.current_process()
    suffix = process.name.rsplit("-", 1)[-1]
    process.name = f"{name}-{suffix}"
    threading.current_thread().name = process.name


def name_process_pool_threads(pool: ProcessPoolExecutor, name: str) -> None:
    """Name the helper threads a ProcessPoolExecutor starts lazily in the parent process.

    Relies on CPython internals; silently does nothing if they are unavailable.
    """
    manager_thread = getattr(pool, "_executor_manager_thread", None)
    if manager_thread is not None:
        manager_thread.name = f"{name}-manager"

    feeder_thread = getattr(getattr(pool, "_call_queue", None), "_thread", None)
    if feeder_thread is not None:
        feeder_thread.name = f"{name}-feeder"
