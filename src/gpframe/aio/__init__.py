"""gpframe.aio: asyncio のイベントループの上でフレームをタスクとして動かす非同期版。

同期版の `gpframe` とは型を共有しない独立した API である。停止はタスクのキャンセルで
行う。制約と原理的な限界は Specification の「Constraints and limits」を参照。

```python
import gpframe.aio

async def work(ctx: gpframe.aio.AsyncContext, n: int) -> int:
    await asyncio.sleep(0.1)
    return n * 2

async def main() -> None:
    async with gpframe.aio.session(timeout=5) as s:
        frame = s.spawn(work, 21)
        for broken in await s.wait_broken():
            broken.escalate()
    print(await frame.result())
```
"""

from gpframe._errors import FrameStoppedError
from gpframe.aio._monitor import (
    HealthWarning,
    LoopMonitor,
    LoopRecovery,
    LoopStall,
    monitor,
)
from gpframe.aio._session import (
    AsyncContext,
    AsyncFrame,
    AsyncIncompleteSessionError,
    AsyncSession,
    AsyncSessionFailed,
    AsyncSessionReport,
    StopHandle,
    session,
)

__all__ = [
    "AsyncContext",
    "AsyncFrame",
    "AsyncIncompleteSessionError",
    "AsyncSession",
    "AsyncSessionFailed",
    "AsyncSessionReport",
    "FrameStoppedError",
    "HealthWarning",
    "LoopMonitor",
    "LoopRecovery",
    "LoopStall",
    "StopHandle",
    "monitor",
    "session",
]
