"""gpframe: 失敗を握りつぶさず、止まらなかった処理を報告するスレッドのスコープ。

```python
import gpframe

def work(ctx: gpframe.Context, n: int) -> int:
    return sum(range(n))

with gpframe.session(timeout=5) as s:
    frame = s.spawn(work, 1_000)
    s.wait()
    for broken in s.broken():
        broken.escalate()

print(frame.result())
```
"""

from gpframe._channel import Channel
from gpframe._errors import (
    ChannelClosedError,
    ChannelFullError,
    DeclaredTypeError,
    FrameAbortedError,
    FrameStateError,
    FrameStoppedError,
    FrameWarning,
    GpFrameError,
    SessionStateError,
)
from gpframe._session import (
    Context,
    Frame,
    IncompleteSessionError,
    Session,
    SessionFailed,
    SessionReport,
    StopHandle,
    session,
)
from gpframe._shared import Shared

__all__ = [
    "Channel",
    "ChannelClosedError",
    "ChannelFullError",
    "Context",
    "DeclaredTypeError",
    "Frame",
    "FrameAbortedError",
    "FrameStateError",
    "FrameStoppedError",
    "FrameWarning",
    "GpFrameError",
    "IncompleteSessionError",
    "Session",
    "SessionFailed",
    "SessionReport",
    "SessionStateError",
    "Shared",
    "StopHandle",
    "session",
]
