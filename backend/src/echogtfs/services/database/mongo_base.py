from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from pymongo import AsyncMongoClient, IndexModel
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import PyMongoError


@dataclass
class _MongoTransaction:
    owner: object
    session: AsyncClientSession
    buffer: list[tuple[str, Any]] = field(default_factory=list)


_current_transaction: ContextVar[_MongoTransaction | None] = ContextVar(
    "echogtfs_current_mongo_transaction",
    default=None,
)


class MongoRepositoryBase:
    """Shared async MongoDB client lifecycle for document repositories.

    Writes issued inside transaction() are buffered and sent as ordered bulk writes, either
    before the next read of the same run (flush_writes) or at commit. Everything becomes
    visible to other readers atomically when the transaction commits.
    """

    _COMMIT_RETRIES = 5

    def __init__(self, mongo_url: str, database_name: str):
        self._client: AsyncMongoClient = AsyncMongoClient(mongo_url, tz_aware=True)
        self._database = self._client[database_name]

    async def initialize(self) -> None:
        """Validate connectivity and create all indices idempotently."""
        await self._client.admin.command("ping")
        await self.ensure_indexes()

    async def close(self) -> None:
        """Close the MongoDB client."""
        await self._client.close()

    def collection(self, name: str) -> AsyncCollection:
        return self._database[name]

    def index_definitions(self) -> dict[str, list[IndexModel]]:
        """Return the indices per collection; subclasses override this."""
        return {}

    async def ensure_indexes(self) -> None:
        """Create all configured indices; existing identical indices are left untouched."""
        for collection_name, indexes in self.index_definitions().items():
            if indexes:
                await self.collection(collection_name).create_indexes(indexes)

    @asynccontextmanager
    async def transaction(
        self,
        *,
        isolation_level: str | None = None,
    ) -> AsyncGenerator[AsyncClientSession, None]:
        """Run repository operations in one MongoDB transaction.

        isolation_level exists for signature parity with the SQL repositories and is ignored.
        """
        current = _current_transaction.get()
        if current is not None and current.owner is self:
            yield current.session
            return

        session = await self._open_session()
        async with session:
            context = _MongoTransaction(owner=self, session=session)
            token = _current_transaction.set(context)
            try:
                try:
                    yield session
                except Exception:
                    if session.in_transaction:
                        await session.abort_transaction()
                    raise

                await self._commit(context)
            finally:
                _current_transaction.reset(token)

    @asynccontextmanager
    async def snapshot(self) -> AsyncGenerator[AsyncClientSession, None]:
        """Yield a snapshot-read session: all reads see the data as of the first read.

        Writers are never blocked, and the 60 s transaction lifetime limit does not apply.
        """
        session = await self._open_session(snapshot=True)
        async with session:
            yield session

    async def write(self, collection_name: str, operation: Any) -> None:
        """Queue one write operation inside a transaction, or execute it directly outside of one."""
        context = self._current_context()
        if context is None:
            await self.collection(collection_name).bulk_write([operation], ordered=True)
            return

        context.buffer.append((collection_name, operation))

    async def flush_writes(self) -> None:
        """Send all queued writes of the current transaction so following reads see them."""
        context = self._current_context()
        if context is None or not context.buffer:
            return

        if not context.session.in_transaction:
            await context.session.start_transaction()

        buffer, context.buffer = context.buffer, []
        await self._bulk_write(buffer, context.session)

    async def read_session(self) -> AsyncClientSession | None:
        """Flush queued writes and return the session reads must use (None outside a transaction)."""
        context = self._current_context()
        if context is None:
            return None

        await self.flush_writes()

        return context.session if context.session.in_transaction else None

    def _current_context(self) -> _MongoTransaction | None:
        context = _current_transaction.get()
        if context is not None and context.owner is self:
            return context

        return None

    async def _open_session(self, snapshot: bool = False) -> AsyncClientSession:
        session = self._client.start_session(snapshot=snapshot)
        if inspect.isawaitable(session):
            session = await session

        return session

    async def _bulk_write(self, buffer: list[tuple[str, Any]], session: AsyncClientSession) -> None:
        index = 0
        while index < len(buffer):
            collection_name = buffer[index][0]
            operations = []
            while index < len(buffer) and buffer[index][0] == collection_name:
                operations.append(buffer[index][1])
                index += 1

            await self.collection(collection_name).bulk_write(operations, ordered=True, session=session)

    async def _commit(self, context: _MongoTransaction) -> None:
        session = context.session

        if not session.in_transaction:
            if not context.buffer:
                return

            buffer = context.buffer
            context.buffer = []

            # with_transaction re-runs the callback on transient errors, which is safe
            # because nothing has been sent yet.
            async def _write_all(transaction_session: AsyncClientSession) -> None:
                await self._bulk_write(buffer, transaction_session)

            await session.with_transaction(_write_all)
            return

        try:
            await self.flush_writes()
        except Exception:
            await session.abort_transaction()
            raise

        for attempt in range(self._COMMIT_RETRIES):
            try:
                await session.commit_transaction()
                return
            except PyMongoError as exc:
                is_unknown_result = exc.has_error_label("UnknownTransactionCommitResult")
                if not is_unknown_result or attempt == self._COMMIT_RETRIES - 1:
                    raise
