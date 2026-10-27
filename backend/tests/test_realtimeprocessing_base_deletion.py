from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _service_test_bootstrap  # noqa: F401

import unittest
from unittest.mock import AsyncMock

from echogtfs.services.realtimeprocessing.base import RealtimeProcessingServiceBase


class TestRealtimeProcessingBaseDeletion(unittest.IsolatedAsyncioTestCase):
    def test_split_deleted_records_separates_flagged_records(self):
        regular, deleted = RealtimeProcessingServiceBase._split_deleted_records(
            [{"id": "a"}, {"id": "b", "is_deleted": True}, {"id": "c", "is_deleted": False}]
        )

        self.assertEqual([record["id"] for record in regular], ["a", "c"])
        self.assertEqual([record["id"] for record in deleted], ["b"])

    async def test_delete_flagged_records_deletes_deduplicated_ids_once(self):
        delete_by_ids = AsyncMock(return_value=0)

        ids = await RealtimeProcessingServiceBase._delete_flagged_records(
            [{"id": "a"}, {"id": "a"}, {"id": "b"}],
            resolve_ids=lambda record: [record["id"]],
            delete_by_ids=delete_by_ids,
            extra_ids=["c"],
        )

        self.assertEqual(ids, {"a", "b", "c"})
        delete_by_ids.assert_awaited_once()
        self.assertEqual(set(delete_by_ids.await_args.args[0]), {"a", "b", "c"})

    async def test_delete_flagged_records_without_ids_does_not_delete(self):
        delete_by_ids = AsyncMock()

        ids = await RealtimeProcessingServiceBase._delete_flagged_records(
            [{"is_deleted": True}],
            resolve_ids=lambda record: [],
            delete_by_ids=delete_by_ids,
        )

        self.assertEqual(ids, set())
        delete_by_ids.assert_not_awaited()

    async def test_delete_flagged_records_ignores_delete_result(self):
        for result in (0, None, 5):
            with self.subTest(result=result):
                ids = await RealtimeProcessingServiceBase._delete_flagged_records(
                    [{"id": "a"}],
                    resolve_ids=lambda record: [record["id"]],
                    delete_by_ids=AsyncMock(return_value=result),
                )

                self.assertEqual(ids, {"a"})


if __name__ == "__main__":
    unittest.main()
