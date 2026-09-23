from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from runtime.config.settings import Settings, get_settings


@asynccontextmanager
async def get_checkpointer(
    settings: Settings | None = None,
) -> AsyncIterator[BaseCheckpointSaver]:
    """
    Async context manager that yields an appropriate checkpoint saver.

    Dev  (env="dev") → AsyncSqliteSaver  (no external service needed)
    Prod (env!="dev") → AsyncPostgresSaver (durable, requires POSTGRES_DSN)

    Caller owns the lifecycle — do not cache this at module level.
    """
    s = settings or get_settings()
    if s.env == "dev":
        async with AsyncSqliteSaver.from_conn_string(s.sqlite_path) as saver:
            yield saver
    else:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(s.postgres_dsn) as saver:
            await saver.setup()
            yield saver
