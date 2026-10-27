from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pymongo.errors import PyMongoError

from echogtfs.services.database import mongo_base
from echogtfs.services.database.mongo_base import MongoRepositoryBase
from echogtfs.services.database.mongo_indexes import (
    SERVICE_ALERTS_COLLECTION,
    TRIP_UPDATES_COLLECTION,
    VEHICLE_POSITIONS_COLLECTION,
    realtime_index_definitions,
)


class _FakeSession:
    def __init__(self, events: list):
        self.events = events
        self.in_transaction = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def start_transaction(self):
        self.in_transaction = True
        self.events.append("start")

    async def commit_transaction(self):
        self.in_transaction = False
        self.events.append("commit")

    async def abort_transaction(self):
        self.in_transaction = False
        self.events.append("abort")

    async def with_transaction(self, callback):
        self.events.append("with_transaction")
        await callback(self)


class _FakeCollection:
    def __init__(self, name: str, events: list):
        self.name = name
        self.events = events
        self.create_indexes = AsyncMock()

    async def bulk_write(self, operations, ordered=True, session=None):
        self.events.append(("bulk_write", self.name, list(operations), session is not None))


class _FakeClient:
    def __init__(self, events: list):
        self.events = events
        self.collections: dict[str, _FakeCollection] = {}
        self.session = _FakeSession(events)
        self.snapshot_flags: list[bool] = []
        self.admin = type("Admin", (), {"command": AsyncMock()})()
        self.close = AsyncMock()

    def __getitem__(self, _database_name):
        return self

    def __getattr__(self, name):
        raise AttributeError(name)

    def get_collection(self, name):
        return self.collections.setdefault(name, _FakeCollection(name, self.events))

    def start_session(self, snapshot=False):
        self.snapshot_flags.append(snapshot)
        return self.session


class _FakeDatabase:
    def __init__(self, client: _FakeClient):
        self._client = client

    def __getitem__(self, name):
        return self._client.get_collection(name)


def _make_repository(events: list) -> tuple[MongoRepositoryBase, _FakeClient]:
    client = _FakeClient(events)
    client.__class__ = type("FakeClientWithDb", (_FakeClient,), {"__getitem__": lambda self, _n: _FakeDatabase(self)})

    with patch.object(mongo_base, "AsyncMongoClient", return_value=client):
        repository = MongoRepositoryBase("mongodb://test", "db")

    return repository, client


class TestMongoRepositoryBase(unittest.IsolatedAsyncioTestCase):
    async def test_write_outside_transaction_executes_immediately(self):
        events: list = []
        repository, _client = _make_repository(events)

        await repository.write("a", "op1")

        self.assertEqual(events, [("bulk_write", "a", ["op1"], False)])

    async def test_transaction_without_flush_commits_via_with_transaction(self):
        events: list = []
        repository, _client = _make_repository(events)

        async with repository.transaction():
            await repository.write("a", "op1")
            await repository.write("a", "op2")
            await repository.write("b", "op3")
            self.assertEqual(events, [])

        self.assertEqual(
            events,
            [
                "with_transaction",
                ("bulk_write", "a", ["op1", "op2"], True),
                ("bulk_write", "b", ["op3"], True),
            ],
        )

    async def test_read_session_flushes_pending_writes_and_commit_follows(self):
        events: list = []
        repository, _client = _make_repository(events)

        async with repository.transaction():
            await repository.write("a", "op1")
            session = await repository.read_session()
            self.assertIsNotNone(session)
            await repository.write("a", "op2")

        self.assertEqual(
            events,
            [
                "start",
                ("bulk_write", "a", ["op1"], True),
                ("bulk_write", "a", ["op2"], True),
                "commit",
            ],
        )

    async def test_read_session_is_none_outside_transaction(self):
        repository, _client = _make_repository([])

        self.assertIsNone(await repository.read_session())

    async def test_nested_transaction_reuses_outer_transaction(self):
        events: list = []
        repository, client = _make_repository(events)

        async with repository.transaction():
            async with repository.transaction():
                await repository.write("a", "op1")

        self.assertEqual(events.count("with_transaction"), 1)
        self.assertEqual(len(client.snapshot_flags), 1)

    async def test_failure_after_flush_aborts_and_discards_pending_writes(self):
        events: list = []
        repository, _client = _make_repository(events)

        with self.assertRaises(ValueError):
            async with repository.transaction():
                await repository.write("a", "op1")
                await repository.read_session()
                await repository.write("a", "op2")
                raise ValueError("boom")

        self.assertEqual(events, ["start", ("bulk_write", "a", ["op1"], True), "abort"])

    async def test_failure_without_flush_sends_nothing(self):
        events: list = []
        repository, _client = _make_repository(events)

        with self.assertRaises(ValueError):
            async with repository.transaction():
                await repository.write("a", "op1")
                raise ValueError("boom")

        self.assertEqual(events, [])

    async def test_commit_retries_unknown_commit_result(self):
        events: list = []
        repository, client = _make_repository(events)
        error = PyMongoError("unknown")
        error._add_error_label("UnknownTransactionCommitResult")
        original_commit = client.session.commit_transaction
        attempts = {"count": 0}

        async def flaky_commit():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise error
            await original_commit()

        client.session.commit_transaction = flaky_commit

        async with repository.transaction():
            await repository.write("a", "op1")
            await repository.read_session()

        self.assertEqual(attempts["count"], 2)
        self.assertIn("commit", events)

    async def test_snapshot_opens_snapshot_session(self):
        repository, client = _make_repository([])

        async with repository.snapshot() as session:
            self.assertIs(session, client.session)

        self.assertEqual(client.snapshot_flags, [True])

    async def test_initialize_pings_and_creates_indexes(self):
        repository, client = _make_repository([])
        repository.index_definitions = lambda: realtime_index_definitions()

        await repository.initialize()

        client.admin.command.assert_awaited_once_with("ping")
        for name in (SERVICE_ALERTS_COLLECTION, TRIP_UPDATES_COLLECTION, VEHICLE_POSITIONS_COLLECTION):
            client.collections[name].create_indexes.assert_awaited_once()


class TestRealtimeIndexDefinitions(unittest.TestCase):
    def test_defines_three_collections_with_unique_trip_keys(self):
        definitions = realtime_index_definitions()

        self.assertEqual(
            set(definitions),
            {SERVICE_ALERTS_COLLECTION, TRIP_UPDATES_COLLECTION, VEHICLE_POSITIONS_COLLECTION},
        )

        trip_updates = {index.document["name"]: index.document for index in definitions[TRIP_UPDATES_COLLECTION]}
        vehicles = {index.document["name"]: index.document for index in definitions[VEHICLE_POSITIONS_COLLECTION]}
        alerts = {index.document["name"]: index.document for index in definitions[SERVICE_ALERTS_COLLECTION]}

        self.assertTrue(trip_updates["trip_id_unique"]["unique"])
        self.assertTrue(vehicles["trip_trip_id_unique"]["unique"])
        self.assertEqual(
            alerts["has_invalid_reference_partial"]["partialFilterExpression"],
            {"has_invalid_reference": True},
        )


if __name__ == "__main__":
    unittest.main()
