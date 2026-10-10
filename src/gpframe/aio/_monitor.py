"""イベントループの応答を監視するヘルスチェック。

ループ上の心拍のタスクが時刻を記録し、ループの外の監視スレッドが最後の心拍からの
遅れを測る(AHEALTH_005)。セッションの約束の外側にある観測の道具であり、
ループのブロックを解くことはしない。
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import traceback
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Self, TypeVar, final

from gpframe._errors import SessionStateError

E = TypeVar("E")


@final
class HealthWarning(UserWarning):
    """ループの停滞や、ヘルスチェックのコールバックの失敗の報告。"""


@dataclass(frozen=True)
class LoopStall:
    """ループの停滞の検出。時刻はすべて `time.monotonic()` の値。"""

    started: float
    """最後に心拍を記録した時刻。"""

    detected: float
    """停滞を検出した時刻。"""

    stack: tuple[str, ...] | None
    """検出した時点のループのスレッドのスタックの写し。取得できなければ `None`。"""

    @property
    def lag(self) -> float:
        """検出した時点での遅れの秒数。"""
        return self.detected - self.started


@dataclass(frozen=True)
class LoopRecovery:
    """停滞からの回復。時刻はすべて `time.monotonic()` の値。"""

    started: float
    """停滞が始まった時刻(停滞の前の最後の心拍)。"""

    recovered: float
    """回復した時刻(停滞の後の最初の心拍)。"""

    @property
    def duration(self) -> float:
        """停滞していた秒数。"""
        return self.recovered - self.started


@final
class LoopMonitor:
    """`async with` で開いている間、そのループの応答の遅れを監視する。"""

    __slots__: tuple[str, ...] = (
        "_entered",
        "_errors",
        "_heartbeat",
        "_interval",
        "_last",
        "_loop_thread",
        "_on_recover",
        "_on_stall",
        "_stall_started",
        "_stop",
        "_threshold",
        "_watcher",
    )

    def __init__(
        self,
        threshold: float = 1.0,
        *,
        interval: float | None = None,
        on_stall: Callable[[LoopStall], object] | None = None,
        on_recover: Callable[[LoopRecovery], object] | None = None,
    ) -> None:
        if not threshold > 0:
            raise ValueError("threshold must be greater than 0")
        resolved = threshold / 4 if interval is None else interval
        if not 0 < resolved <= threshold:
            raise ValueError("interval must be greater than 0 and at most threshold")
        self._threshold: float = threshold
        self._interval: float = resolved
        self._on_stall: Callable[[LoopStall], object] | None = on_stall
        self._on_recover: Callable[[LoopRecovery], object] | None = on_recover
        self._entered: bool = False
        # 心拍のタスクが書き、監視スレッドが読む。float の代入は不可分である。
        self._last: float = time.monotonic()
        # 監視スレッドだけが書く。None でなければ停滞中。
        self._stall_started: float | None = None
        self._errors: list[BaseException] = []
        self._loop_thread: int | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._watcher: threading.Thread | None = None
        self._stop: threading.Event = threading.Event()

    @property
    def threshold(self) -> float:
        """停滞とみなす遅れの秒数。"""
        return self._threshold

    @property
    def interval(self) -> float:
        """心拍を記録し、遅れを測る間隔の秒数。"""
        return self._interval

    @property
    def stalled(self) -> bool:
        """停滞中なら `True`。どのスレッドから読んでもよい。"""
        return self._stall_started is not None

    @property
    def lag(self) -> float:
        """最後の心拍からの経過秒数。どのスレッドから読んでもよい。"""
        return time.monotonic() - self._last

    @property
    def errors(self) -> tuple[BaseException, ...]:
        """コールバックが送出した例外を、送出された順に返す。"""
        return tuple(self._errors)

    async def __aenter__(self) -> Self:
        if self._entered:
            raise SessionStateError("a monitor can be entered only once")
        self._entered = True
        self._loop_thread = threading.get_ident()
        self._last = time.monotonic()
        self._heartbeat = asyncio.get_running_loop().create_task(
            self._beat(), name="gpframe:monitor:heartbeat"
        )
        self._watcher = threading.Thread(
            target=self._watch, name="gpframe:monitor:watcher", daemon=True
        )
        self._watcher.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        self._stop.set()
        heartbeat = self._heartbeat
        if heartbeat is not None:
            _ = heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
        watcher = self._watcher
        if watcher is not None:
            # ループを止めずに監視スレッドの終了を待つ。抜けた後にコールバックは呼ばれない。
            await asyncio.to_thread(watcher.join)
        return False

    async def _beat(self) -> None:
        while True:
            self._last = time.monotonic()
            await asyncio.sleep(self._interval)

    def _watch(self) -> None:
        while not self._stop.wait(self._interval):
            last = self._last
            now = time.monotonic()
            started = self._stall_started
            if started is None:
                if now - last > self._threshold:
                    self._stall_started = last
                    self._report_stall(LoopStall(last, now, self._stack()))
            elif last > started:
                self._stall_started = None
                self._report_recovery(LoopRecovery(started, last))

    def _stack(self) -> tuple[str, ...] | None:
        thread = self._loop_thread
        if thread is None:
            return None
        # sys._current_frames() は CPython と PyPy にある。取得は取れた範囲での写しである(AHEALTH_010)。
        try:
            frame = sys._current_frames().get(thread)
        except AttributeError:
            return None
        return None if frame is None else tuple(traceback.format_stack(frame))

    def _report_stall(self, stall: LoopStall) -> None:
        if self._on_stall is None:
            where = (
                stall.stack[-1].strip().splitlines()[0] if stall.stack else "unknown"
            )
            self._warn(f"event loop stalled for {stall.lag:.3f}s at {where}")
            return
        self._call(self._on_stall, stall)

    def _report_recovery(self, recovery: LoopRecovery) -> None:
        if self._on_recover is not None:
            self._call(self._on_recover, recovery)

    def _call(self, callback: Callable[[E], object], event: E) -> None:
        try:
            _ = callback(event)
        except BaseException as error:  # noqa: BLE001 - 記録して監視を続ける(AHEALTH_014)
            self._errors.append(error)
            self._warn(f"monitor callback failed: {error!r}")

    def _warn(self, message: str) -> None:
        try:
            warnings.warn(HealthWarning(message), stacklevel=2)
        except Exception as error:  # noqa: BLE001 - 警告が例外に変えられていても監視は止めない
            self._errors.append(error)


def monitor(
    threshold: float = 1.0,
    *,
    interval: float | None = None,
    on_stall: Callable[[LoopStall], object] | None = None,
    on_recover: Callable[[LoopRecovery], object] | None = None,
) -> LoopMonitor:
    """ループの応答を監視するヘルスチェックを作る。`async with` で開いて使う。

    遅れが `threshold` 秒(既定は 1.0 秒)を超えたら停滞とみなし、`on_stall` を監視スレッドで呼ぶ
    (省略時は `HealthWarning`)。回復したら `on_recover` を呼ぶ。
    """
    return LoopMonitor(
        threshold, interval=interval, on_stall=on_stall, on_recover=on_recover
    )
