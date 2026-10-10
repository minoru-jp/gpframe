"""非同期版のセッション、フレーム、コンテキスト。

内部状態はセッションが属するループのスレッドからしか触らないので、ロックを使わない
(ALIMIT_007)。スレッドをまたぐ入り口は `AsyncSession.stop()` だけである(ASTOP_005)。
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import warnings
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from types import TracebackType
from typing import Generic, Literal, Self, TypeVar, TypeVarTuple, cast, final

from gpframe._errors import (
    FrameAbortedError,
    FrameStateError,
    FrameStoppedError,
    FrameWarning,
    GpFrameError,
    SessionStateError,
)

R = TypeVar("R")
R_co = TypeVar("R_co", covariant=True)
Ts = TypeVarTuple("Ts")


class _Mark(Enum):
    IGNORED = auto()
    ESCALATED = auto()


class _State(Enum):
    NEW = auto()
    OPEN = auto()
    CLOSED = auto()


class _Ending(Enum):
    """ルーティンの終わり方。"""

    RETURNED = auto()
    STOPPED = auto()  # gpframe の停止要求によるキャンセル、または停止の後の起動
    RAISED = auto()  # 例外(gpframe が要求していないキャンセルを含む)


@dataclass(frozen=True)
class AsyncSessionReport:
    """不完全だった非同期のサブセッションの報告。"""

    broken: tuple[AsyncFrame[object], ...]
    """`ignore()` されなかった broken のフレーム。`escalate()` 済みのものも含む。"""

    stuck: tuple[AsyncFrame[object], ...]
    """セッションの終了時に、まだ終わっていなかったフレーム。"""

    errors: tuple[BaseException, ...]
    """セッションの `async with` ブロック内で起きた例外。"""


def _merge(reports: Sequence[AsyncSessionReport]) -> AsyncSessionReport:
    return AsyncSessionReport(
        broken=tuple(f for r in reports for f in r.broken),
        stuck=tuple(f for r in reports for f in r.stuck),
        errors=tuple(e for r in reports for e in r.errors),
    )


@final
class AsyncIncompleteSessionError(GpFrameError):
    """フレーム自身は例外を出していないが、配下の非同期セッションが不完全だった。"""

    def __init__(self, frame_name: str, report: AsyncSessionReport) -> None:
        super().__init__(f"frame {frame_name!r} has an incomplete session")
        self.frame_name: str = frame_name
        self.report: AsyncSessionReport = report


class AsyncSessionFailed(ExceptionGroup[Exception]):
    """ルートの非同期セッションの終了時に、承認されなかった失敗があった。

    `frames` は `exceptions` と同じ順に並んだ、対応するフレーム。
    """

    def __new__(
        cls,
        message: str,
        exceptions: Sequence[Exception],
        frames: Sequence[AsyncFrame[object]] = (),
    ) -> Self:
        return super().__new__(cls, message, exceptions)

    def __init__(
        self,
        message: str,
        exceptions: Sequence[Exception],
        frames: Sequence[AsyncFrame[object]] = (),
    ) -> None:
        super().__init__(message, exceptions)
        self.frames: tuple[AsyncFrame[object], ...] = tuple(frames)

    # 標準の derive() は任意の BaseException の列を受け取る型だが、split() と
    # subgroup() が渡すのは常にこのグループ自身が持つ Exception の部分集合である。
    def derive(self, excs: Sequence[Exception]) -> AsyncSessionFailed:  # pyright: ignore[reportIncompatibleMethodOverride]
        """`split()` と `subgroup()` のために、対応するフレームだけを引き継ぐ。"""
        kept = {id(e) for e in excs}
        frames = [
            frame
            for frame, error in zip(self.frames, self.exceptions, strict=True)
            if id(error) in kept
        ]
        return AsyncSessionFailed(self.message, excs, frames)


class _Registration(Enum):
    PENDING = auto()
    CALLED = auto()
    CANCELLED = auto()


@final
class StopHandle:
    """`AsyncContext.on_stop()` が返す、停止コールバックの登録。"""

    __slots__: tuple[str, ...] = ("_callback", "_frame", "_state")

    def __init__(
        self, frame: AsyncFrame[object], callback: Callable[[], object]
    ) -> None:
        self._frame: AsyncFrame[object] = frame
        self._callback: Callable[[], object] = callback
        self._state: _Registration = _Registration.PENDING

    def cancel(self) -> None:
        """登録を取り消す。すでに呼ばれた後や、フレームが終了した後は何もしない。"""
        if self._state is _Registration.PENDING:
            self._state = _Registration.CANCELLED
            # 登録を残さない(ASTOP_016)。
            with contextlib.suppress(ValueError):
                self._frame._handles.remove(self)


class AsyncFrame(Generic[R_co]):
    """`AsyncSession.spawn()` で起動した、ループ上のタスクとして動く処理。

    終了したフレームは succeeded、stopped、broken のどれか一つになる。broken の
    フレームは、セッションを抜けるまでに `ignore()` か `escalate()` で承認される
    ことを期待される。
    """

    __slots__: tuple[str, ...] = (
        "_args",
        "_done",
        "_ending",
        "_error",
        "_fn",
        "_handles",
        "_mark",
        "_name",
        "_reason",
        "_reports",
        "_session",
        "_stop_applied",
        "_stop_errors",
        "_task",
        "_value",
    )

    def __init__(
        self,
        session: AsyncSession,
        fn: Callable[..., Coroutine[object, object, object]],
        args: tuple[object, ...],
        name: str,
    ) -> None:
        self._session: AsyncSession = session
        self._fn: Callable[..., Coroutine[object, object, object]] = fn
        self._args: tuple[object, ...] = args
        self._name: str = name
        self._done: asyncio.Future[None] = session._require_loop().create_future()
        self._ending: _Ending | None = None
        self._value: object = None
        self._error: BaseException | None = None
        self._reports: list[AsyncSessionReport] = []
        self._stop_errors: list[BaseException] = []
        self._handles: list[StopHandle] = []
        self._stop_applied: bool = False
        self._mark: _Mark | None = None
        self._reason: str = ""
        self._task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        """ログ用の名前。省略時は関数名になり、重複しても構わない。"""
        return self._name

    @property
    def running(self) -> bool:
        """まだ終わっていなければ `True`。"""
        return self._ending is None

    @property
    def succeeded(self) -> bool:
        """ルーティンが値を返して終わり、失敗がなければ `True`。"""
        return self._ending is _Ending.RETURNED and not self._has_failure()

    @property
    def stopped(self) -> bool:
        """停止の要求によるキャンセルで終わり、失敗がなければ `True`。"""
        return self._ending is _Ending.STOPPED and not self._has_failure()

    @property
    def error(self) -> BaseException | None:
        """ルーティンが送出した例外。gpframe が要求していないキャンセルを含む。"""
        return self._error if self._ending is _Ending.RAISED else None

    @property
    def incomplete(self) -> AsyncSessionReport | None:
        """不完全だったサブセッションの報告を一つにまとめたもの。なければ `None`。"""
        return _merge(self._reports) if self._reports else None

    @property
    def stop_errors(self) -> tuple[BaseException, ...]:
        """停止コールバックが送出した例外を、送出された順に返す。"""
        return tuple(self._stop_errors)

    async def result(self, timeout: float | None = None) -> R_co:
        """フレームが終わるまで最大 `timeout` 秒待ち、結果を返す。

        値を返していればその値、stopped なら `FrameStoppedError`、例外で終わって
        いればその例外を送出する。フレームの `CancelledError` は呼び出し側に
        漏らさず `FrameAbortedError` で包む。待っている側がキャンセルされても、
        フレームはキャンセルされない。この呼び出しは失敗の承認にはならない。
        """
        _ = self._session._require_loop()
        if self._ending is None:
            try:
                await asyncio.wait_for(asyncio.shield(self._done), timeout)
            except TimeoutError:
                if self._ending is None:
                    raise TimeoutError(
                        f"frame {self._name!r} did not finish in {timeout}s"
                    ) from None
        if self._ending is _Ending.RETURNED:
            return cast("R_co", self._value)
        if self._ending is _Ending.STOPPED:
            raise FrameStoppedError(f"frame {self._name!r} was stopped")
        error = cast("BaseException", self._error)
        if isinstance(error, asyncio.CancelledError):
            raise FrameAbortedError(self._name, error)
        raise error

    async def wait(self, timeout: float | None = None) -> bool:
        """ループを止めずに、フレームが終わるまで最大 `timeout` 秒待つ。

        終わっていれば `True`、時間切れなら `False`。終わり方によらず例外を
        送出せず、失敗の承認にもならない。待っている側がキャンセルされても、
        フレームはキャンセルされない。
        """
        _ = self._session._require_loop()
        if self._ending is not None:
            return True
        try:
            await asyncio.wait_for(asyncio.shield(self._done), timeout)
        except TimeoutError:
            return self._ending is not None
        return True

    def ignore(self) -> None:
        """この失敗を想定内として承認する。"""
        self._session._acknowledge(self, _Mark.IGNORED, "")

    def escalate(self, reason: str = "") -> None:
        """この失敗を想定外として承認し、上へ伝える。"""
        self._session._acknowledge(self, _Mark.ESCALATED, reason)

    def _has_failure(self) -> bool:
        return (
            self._ending is _Ending.RAISED
            or bool(self._reports)
            or bool(self._stop_errors)
        )

    def _is_broken(self) -> bool:
        return self._ending is not None and self._has_failure()

    async def _run(self) -> None:
        context = AsyncContext(self)
        try:
            self._value = await self._fn(context, *self._args)
            self._ending = _Ending.RETURNED
        except asyncio.CancelledError as cancelled:
            if self._session._stopping:
                self._ending = _Ending.STOPPED
            else:
                self._error = cancelled
                self._ending = _Ending.RAISED
        except BaseException as error:
            self._error = error
            self._ending = _Ending.RAISED
            if isinstance(error, KeyboardInterrupt | SystemExit):
                # 中断の要求は握りつぶさない。記録したうえで asyncio に渡す。
                raise
        finally:
            if self._ending is None:  # 念のため。ここへは来ない
                self._ending = _Ending.RAISED
            self._handles.clear()  # ルーティンの後は停止コールバックを呼ばない(ASTOP_015)
            # ルーティンと引数への参照を手放す(AFRAME_016)。
            self._fn = _released
            self._args = ()
            if not self._done.done():
                self._done.set_result(None)
            if not self._is_broken():
                self._session._forget(self)  # 判定に要らない(ASESSION_021)
            self._session._changed()

    def _end_stopped(self) -> None:
        """ルーティンを呼ばずに、stopped として終わらせる(AFRAME_015)。"""
        self._fn = _released
        self._args = ()
        self._ending = _Ending.STOPPED
        self._done.set_result(None)

    def _apply_stop(self) -> None:
        """停止をこのフレームに適用する。ループのスレッドで呼ぶ。"""
        if self._ending is not None or self._stop_applied:
            return
        self._stop_applied = True
        # キャンセルがルーティンに届くより前に、停止コールバックを呼ぶ(ASTOP_013)。
        self._call_stop_callbacks()
        if self._task is not None:
            _ = self._task.cancel()  # 一度だけ(ASTOP_003)

    def _call_stop_callbacks(self) -> None:
        for handle in list(self._handles):
            if self._ending is not None:
                return
            if handle._state is not _Registration.PENDING:
                continue
            handle._state = _Registration.CALLED
            try:
                result = handle._callback()
                if inspect.iscoroutine(result):
                    result.close()
                    raise TypeError("a stop callback must not return a coroutine")
            except BaseException as error:  # noqa: BLE001 - フレームの失敗として記録する(ASTOP_017)
                self._stop_errors.append(error)
        self._handles = [h for h in self._handles if h._state is _Registration.PENDING]

    def _register_stop(self, callback: Callable[[], object]) -> StopHandle:
        if inspect.iscoroutinefunction(callback):
            raise TypeError("a stop callback must be a synchronous callable")
        handle = StopHandle(cast("AsyncFrame[object]", self), callback)
        if self._ending is not None:
            handle._state = _Registration.CANCELLED
            return handle
        self._handles.append(handle)
        if self._stop_applied:
            # 停止の後の登録は、ループが次に動いたときに呼ぶ(ASTOP_014)。
            _ = self._session._require_loop().call_soon(self._call_stop_callbacks)
        return handle

    def __repr__(self) -> str:
        if self._ending is None:
            state = "running"
        elif self._is_broken():
            state = "broken"
        elif self._ending is _Ending.STOPPED:
            state = "stopped"
        else:
            state = "succeeded"
        return f"<AsyncFrame {self._name!r} {state}>"


@final
class AsyncContext:
    """非同期のルーティンの第 1 引数として渡される、フレームの実行環境。"""

    __slots__: tuple[str, ...] = ("_frame",)

    def __init__(self, frame: AsyncFrame[object]) -> None:
        self._frame: AsyncFrame[object] = frame

    @property
    def name(self) -> str:
        """このフレームの名前。"""
        return self._frame.name

    @property
    def stopping(self) -> bool:
        """このフレームのセッションに停止が要求されていれば `True`。"""
        return self._frame._session._stopping

    def on_stop(self, callback: Callable[[], object]) -> StopHandle:
        """停止が要求されたときに呼ぶ、同期の停止コールバックを登録する。

        キャンセルでは止まらない処理(`asyncio.to_thread()` のブロッキング処理など)の
        止め方を登録するのに使う。ループのスレッドで、登録した順に、キャンセルが
        ルーティンに届く前に呼ばれる。コルーチン関数は `TypeError` で拒否する。
        """
        _ = self._frame._session._require_loop()
        return self._frame._register_stop(callback)

    def session(self, *, timeout: float | None = None) -> AsyncSession:
        """このフレームを親とする非同期のサブセッションを作る。"""
        return AsyncSession(timeout=timeout, _owner=self._frame)


@final
class AsyncSession:
    """`async with` で開き、その中で起動したフレームをタスクとして管理するスコープ。

    開いたときに動いていたループに属し、`stop()` 以外の操作はそのループの
    スレッドから行う。
    """

    __slots__: tuple[str, ...] = (
        "_changed_event",
        "_children",
        "_frames",
        "_loop",
        "_owner",
        "_state",
        "_stopping",
        "_strict",
        "_timeout",
    )

    def __init__(
        self,
        *,
        timeout: float | None = None,
        strict: bool = False,
        _owner: AsyncFrame[object] | None = None,
    ) -> None:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be None or a non-negative number")
        self._timeout: float | None = timeout
        self._strict: bool = strict
        self._owner: AsyncFrame[object] | None = _owner
        self._loop: asyncio.AbstractEventLoop | None = None
        # 判定と報告に要るフレームだけを、起動した順に持つ(ASESSION_021)。
        self._frames: dict[AsyncFrame[object], None] = {}
        self._children: list[AsyncSession] = []
        self._state: _State = _State.NEW
        # どのスレッドからも書き込まれうる。bool の代入は不可分である。
        self._stopping: bool = False
        self._changed_event: asyncio.Event | None = None

    @property
    def stopping(self) -> bool:
        """停止が要求されていれば `True`。どのスレッドから読んでもよい。"""
        return self._stopping

    def spawn(
        self,
        fn: Callable[[AsyncContext, *Ts], Coroutine[object, object, R]],
        *args: *Ts,
        name: str | None = None,
    ) -> AsyncFrame[R]:
        """`await fn(context, *args)` を、このセッションのループのタスクとして起動する。

        `fn` はコルーチン関数でなければならない(`TypeError`)。開いていない
        セッションでは `SessionStateError`。停止が要求された後は、タスクを
        作らずに stopped のフレームを返す。
        """
        loop = self._require_loop()
        if self._state is not _State.OPEN:
            raise SessionStateError("spawn() needs an open session")
        if not inspect.iscoroutinefunction(fn):
            raise TypeError("spawn() needs a coroutine function")
        frame = AsyncFrame[object](
            self,
            cast("Callable[..., Coroutine[object, object, object]]", fn),
            tuple(args),
            name or _name_of(fn),
        )
        if self._stopping:
            frame._end_stopped()
            return cast("AsyncFrame[R]", frame)
        self._frames[frame] = None
        frame._task = loop.create_task(frame._run(), name=f"gpframe:{frame.name}")
        frame._task.add_done_callback(_retrieve)
        return cast("AsyncFrame[R]", frame)

    def running(self) -> bool:
        """まだ終わっていないフレームがあれば `True`。"""
        _ = self._require_loop()
        return any(frame.running for frame in self._frames)

    def broken(self) -> list[AsyncFrame[object]]:
        """まだ承認されていない broken のフレームを、起動した順に返す。"""
        _ = self._require_loop()
        return self._unacknowledged()

    async def wait(self, timeout: float | None = None) -> bool:
        """ループを止めずに、すべてのフレームが終わるまで最大 `timeout` 秒待つ。"""
        _ = self._require_loop()
        return await self._wait_until(
            lambda: not any(f.running for f in self._frames), timeout
        )

    async def wait_broken(
        self, timeout: float | None = None, *, idle: bool = False
    ) -> list[AsyncFrame[object]]:
        """ループを止めずに、最初の失敗を待つ。

        未承認の broken のフレームが現れるか、実行中のフレームがなくなるか、
        `timeout` 秒が経つまで待ち、その時点の `broken()` を返す。

        `idle=True` なら、実行中のフレームがなくても戻らず、失敗か、停止の
        要求か、時間切れまで待つ。フレームが増減するセッションで使う。
        """
        _ = self._require_loop()

        def ready() -> bool:
            if self._unacknowledged():
                return True
            if idle:
                return self._stopping
            return not any(f.running for f in self._frames)

        _ = await self._wait_until(ready, timeout)
        return self._unacknowledged()

    def stop(self) -> None:
        """停止を要求する。どのスレッドから呼んでもよく、完了を待たずに戻る。

        すべてのフレームのタスクを一度だけキャンセルし、停止コールバックを
        キャンセルより前に呼び、サブセッションにも停止を伝える。別のスレッド
        から呼んだ場合、それらはループが次に動いたときに行われる。開く前や
        閉じた後に呼んでもよく、開く前なら開いた時点で止まっている。
        """
        if self._stopping:
            return
        self._stopping = True
        loop = self._loop
        if loop is None:
            return
        if _on_loop(loop):
            self._apply_stop()
            return
        try:
            _ = loop.call_soon_threadsafe(self._apply_stop)
        except RuntimeError:
            pass  # ループが閉じていれば、キャンセルは届かない(ALIMIT_008)

    async def __aenter__(self) -> Self:
        loop = asyncio.get_running_loop()
        if self._state is not _State.NEW:
            raise SessionStateError("a session can be entered only once")
        self._loop = loop
        self._changed_event = asyncio.Event()
        self._state = _State.OPEN
        if self._owner is not None:
            parent = self._owner._session
            parent._children.append(self)
            if parent._stopping:
                self._stopping = True  # 停止の後に開いたサブセッション(ASTOP_004)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if exc is not None:
            self.stop()
        cancelled_while_waiting = False
        try:
            _ = await self.wait(self._timeout)
        except asyncio.CancelledError:
            # 待機中にさらにキャンセルされたら、待機を打ち切る(ASESSION_011)。
            cancelled_while_waiting = True
        self._state = _State.CLOSED
        stuck = tuple(f for f in self._frames if f.running)
        if stuck:
            self.stop()  # 停止を要求して、待たずに切り離す
        broken = tuple(f for f in self._frames if f._is_broken())
        owner_cancelled = cancelled_while_waiting or isinstance(
            exc, asyncio.CancelledError
        )
        if self._owner is not None:
            self._close_sub(broken, stuck, exc)
        else:
            self._close_root(broken, stuck, owner_cancelled=owner_cancelled)
        if cancelled_while_waiting and exc is None:
            raise asyncio.CancelledError
        return False

    def _close_sub(
        self,
        broken: tuple[AsyncFrame[object], ...],
        stuck: tuple[AsyncFrame[object], ...],
        exc: BaseException | None,
    ) -> None:
        owner = cast("AsyncFrame[object]", self._owner)
        parent = owner._session
        if self in parent._children:
            parent._children.remove(self)
        unacknowledged = tuple(f for f in broken if f._mark is not _Mark.IGNORED)
        # 親のセッションの停止によるキャンセルは、不完全の原因に含めない(ASESSION_018)。
        counts = exc is not None and not (
            isinstance(exc, asyncio.CancelledError) and parent._stopping
        )
        if unacknowledged or stuck or counts:
            owner._reports.append(
                AsyncSessionReport(
                    broken=unacknowledged,
                    stuck=stuck,
                    errors=(cast("BaseException", exc),) if counts else (),
                )
            )

    def _close_root(
        self,
        broken: tuple[AsyncFrame[object], ...],
        stuck: tuple[AsyncFrame[object], ...],
        *,
        owner_cancelled: bool,
    ) -> None:
        if stuck:
            names = ", ".join(repr(f.name) for f in stuck)
            warnings.warn(
                FrameWarning(f"frames did not stop within {self._timeout}s: {names}"),
                stacklevel=3,
            )
        unmarked = [f for f in broken if f._mark is None]
        if unmarked and not self._strict:
            names = ", ".join(repr(f.name) for f in unmarked)
            warnings.warn(
                FrameWarning(f"failed frames were not acknowledged: {names}"),
                stacklevel=3,
            )
        failing = [
            f
            for f in broken
            if f._mark is _Mark.ESCALATED or (self._strict and f._mark is None)
        ]
        if not failing:
            return
        if owner_cancelled:
            # キャンセルの伝わり方を壊さないため、例外ではなく警告で報告する(ASESSION_016)。
            warnings.warn(
                FrameWarning(
                    f"the session was cancelled; not raising {_failure_message(failing)}"
                ),
                stacklevel=3,
            )
            return
        raise AsyncSessionFailed(
            _failure_message(failing),
            [_exception_of(f) for f in failing],
            failing,
        )

    def _acknowledge(self, frame: AsyncFrame[object], mark: _Mark, reason: str) -> None:
        _ = self._require_loop()
        if not frame._is_broken():
            if frame.running:
                state = "still running"
            elif frame._ending is _Ending.STOPPED:
                state = "was stopped"
            else:
                state = "did not fail"
            raise FrameStateError(f"frame {frame.name!r} {state}")
        if frame._mark is not None:
            raise FrameStateError(f"frame {frame.name!r} is already acknowledged")
        frame._mark = mark
        frame._reason = reason
        if mark is _Mark.IGNORED:
            self._forget(frame)  # 判定に要らない(ASESSION_021)

    def _apply_stop(self) -> None:
        """停止をすべてのフレームとサブセッションに適用する。ループのスレッドで呼ぶ。"""
        for frame in list(self._frames):
            frame._apply_stop()
        for child in list(self._children):
            child.stop()
        self._changed()  # wait_broken(idle=True) を起こす

    def _forget(self, frame: AsyncFrame[object]) -> None:
        """判定と報告に要らなくなったフレームを手放す。"""
        _ = self._frames.pop(frame, None)

    def _unacknowledged(self) -> list[AsyncFrame[object]]:
        return [f for f in self._frames if f._is_broken() and f._mark is None]

    def _changed(self) -> None:
        """フレームの状態が変わったことを、待っているタスクに知らせる。"""
        event = self._changed_event
        if event is not None:
            event.set()
            self._changed_event = asyncio.Event()

    async def _wait_until(
        self, condition: Callable[[], bool], timeout: float | None
    ) -> bool:
        loop = self._require_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while not condition():
            event = self._changed_event
            if event is None:
                return condition()
            if deadline is None:
                _ = await event.wait()
                continue
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            try:
                _ = await asyncio.wait_for(event.wait(), remaining)
            except TimeoutError:
                return condition()
        return True

    def _require_loop(self) -> asyncio.AbstractEventLoop:
        """属するループのスレッドから呼ばれていることを確かめる(ALIMIT_007)。"""
        loop = self._loop
        if loop is None:
            raise SessionStateError("the session has not been entered")
        if not _on_loop(loop):
            raise SessionStateError("the session belongs to another event loop")
        return loop


def session(*, timeout: float | None = None, strict: bool = False) -> AsyncSession:
    """ルートの非同期セッションを作る。`async with` で開いて使う。"""
    return AsyncSession(timeout=timeout, strict=strict)


def _retrieve(task: asyncio.Task[None]) -> None:
    """タスクの例外を取り出し済みにする。

    タスクから出る例外は KeyboardInterrupt と SystemExit だけで、それらはフレームに
    記録したうえで asyncio に渡している(AFRAME_014)。asyncio の「取り出されなかった
    例外」のログは重複した報告になるので出さない。
    """
    if not task.cancelled():
        _ = task.exception()


def _on_loop(loop: asyncio.AbstractEventLoop) -> bool:
    try:
        return asyncio.get_running_loop() is loop
    except RuntimeError:
        return False


def _name_of(fn: Callable[..., object]) -> str:
    name = getattr(fn, "__name__", None)
    return name if isinstance(name, str) else type(fn).__name__


def _exception_of(frame: AsyncFrame[object]) -> Exception:
    """`AsyncSessionFailed` に入れる、フレームの例外を決める(ASESSION_014)。"""
    error = frame.error
    if error is None and frame._stop_errors:
        error = frame._stop_errors[0]
    if isinstance(error, Exception):
        return error
    if error is not None:
        return FrameAbortedError(frame.name, error)
    return AsyncIncompleteSessionError(frame.name, _merge(frame._reports))


def _failure_message(frames: Sequence[AsyncFrame[object]]) -> str:
    parts = [f"{f.name} ({f._reason})" if f._reason else f.name for f in frames]
    count = len(frames)
    return f"{count} frame{'s' if count != 1 else ''} failed: {', '.join(parts)}"


async def _released(*_args: object) -> object:
    """終わったフレームが、ルーティンの代わりに持つもの。呼ばれることはない。"""
    raise AssertionError("the routine of a finished frame was released")
