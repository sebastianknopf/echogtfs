import asyncio

from echogtfs.common.intf_progress_report import ReportProgressInterface


class ReportProgressQueue(ReportProgressInterface):

    def __init__(self) -> None:
        self._queue = asyncio.Queue()

    async def report_progress(self, *, progress: float, message: str) -> None:
        event = {
            "event": "progress",
            "progress": progress,
            "message": message,
            "done": progress >= 100.0,
        }
        
        await self._queue.put(event)
        await asyncio.sleep(0)

    async def __aiter__(self):
        while True:
            event = await self._queue.get()
            yield event

            if event.get("done") or event.get("progress", 0.0) >= 100.0:
                break