"""セッション、フレーム、コンテキスト。"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import threading
import time
import warnings
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from types import TracebackType
from typing import Generic, Literal, Self, TypeVar, TypeVarTuple, cast, final, overload

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


@dataclass(frozen=True)
class SessionReport:
    """不完全だったサブセッションの報告。

    フレームの中で開いたセッションが不完全に終わると、親フレームの
    `Frame.incomplete` から読める。
    """

    broken: tuple[Frame[object], ...]
    """`ignore()` されなかった broken frame。`escalate()` 済みのものも含む。"""

    stuck: tuple[Frame[object], ...]
    """セッションの終了時に、まだ止まっていなかったフレーム。"""

    errors: tuple[BaseException, ...]
    """セッションの `with` ブロック内で起きた例外。"""


def _merge(reports: Sequence[SessionReport]) -> SessionReport:
    return SessionReport(
        broken=tuple(f for r in reports for f in r.broken),
        stuck=tuple(f for r in reports for f in r.stuck),
        errors=tuple(e for r in reports for e in r.errors),
    )


@final
class IncompleteSessionError(GpFrameError):
    """フレーム自身は例外を出していないが、配下のセッションが不完全だった。

    `SessionFailed` の中で、例外を持たない broken frame の代わりに使われる。
    """

    def __init__(self, frame_name: str, report: SessionReport) -> None:
        super().__init__(f"frame {frame_name!r} has an incomplete session")
        self.frame_name: str = frame_name
        self.report: SessionReport = report


class SessionFailed(ExceptionGroup[Exception]):
    """ルートのセッションの終了時に、承認されなかった失敗があった。

    `escalate()` されたフレーム(`strict=True` ではマークのないフレームも)の
    例外をまとめて持つ。`except*` で例外の型ごとに受け取れる。
    `frames` は `exceptions` と同じ順に並んだ、対応するフレーム。
    """

    def __new__(
        cls,
        message: str,
        exceptions: Sequence[Exception],
        frames: Sequence[Frame[object]] = (),
    ) -> Self:
        return super().__new__(cls, message, exceptions)

    def __init__(
        self,
        message: str,
        exceptions: Sequence[Exception],
        frames: Sequence[Frame[object]] = (),
    ) -> None:
        super().__init__(message, exceptions)
        self.frames: tuple[Frame[object], ...] = tuple(frames)

    # 標準の derive() は任意の BaseException の列を受け取る型だが、split() と
    # subgroup() が渡すのは常にこのグループ自身が持つ Exception の部分集合である。
    def derive(self, excs: Sequence[Exception]) -> SessionFailed:  # pyright: ignore[reportIncompatibleMethodOverride]
        """`split()` と `subgroup()` のために、対応するフレームだけを引き継ぐ。"""
        kept = {id(e) for e in excs}
        frames = [
            frame
            for frame, error in zip(self.frames, self.exceptions, strict=True)
            if id(error) in kept
        ]
        return SessionFailed(self.message, excs, frames)


class _Registration(Enum):
    PENDING = auto()
    CALLED = auto()
    CANCELLED = auto()


@final
class StopHandle:
    """`Context.on_stop()` が返す、停止コールバックの登録。"""

    __slots__: tuple[str, ...] = ("_callback", "_frame", "_state")

    def __init__(self, frame: Frame[object], callback: Callable[[], object]) -> None:
        self._frame: Frame[object] = frame
        self._callback: Callable[[], object] = callback
        self._state: _Registration = _Registration.PENDING

    def cancel(self) -> None:
        """登録を取り消す。取り消した後、このコールバックは呼ばれない。

        すでに呼ばれた後や、フレームが終了した後に呼んでも何もしない。
        """
        frame = self._frame
        with frame._session._cond:
            if self._state is _Registration.PENDING:
                self._state = _Registration.CANCELLED
                # 登録を残さない(STOP_016)。生きている登録は少ないので、線形の除去で足りる。
                with contextlib.suppress(ValueError):
                    frame._handles.remove(self)


class Frame(Generic[R_co]):
    """`Session.spawn()` で起動した、一つのスレッドで動く処理。

    `concurrent.futures.Future` に近いハンドルで、終了後は戻り値と失敗の
    状態を持つ。例外で終わったか、配下のセッションが不完全だったか、
    停止コールバックが例外を出したフレームは broken frame になり、
    セッションを抜けるまでに `ignore()` か `escalate()` で承認されることを
    期待される。
    """

    __slots__: tuple[str, ...] = (
        "_args",
        "_dispatching",
        "_done",
        "_error",
        "_fn",
        "_handles",
        "_in_call",
        "_mark",
        "_name",
        "_reason",
        "_reports",
        "_returned",
        "_session",
        "_stop_errors",
        "_stopped",
        "_thread",
        "_value",
    )

    def __init__(
        self,
        session: Session,
        fn: Callable[..., object],
        args: tuple[object, ...],
        name: str,
    ) -> None:
        self._session: Session = session
        self._fn: Callable[..., object] = fn
        self._args: tuple[object, ...] = args
        self._name: str = name
        self._done: threading.Event = threading.Event()
        self._value: object = None
        self._error: BaseException | None = None
        self._reports: list[SessionReport] = []
        self._mark: _Mark | None = None
        self._reason: str = ""
        self._thread: threading.Thread = threading.Thread(
            target=self._run, name=f"gpframe:{name}", daemon=True
        )
        # 停止コールバックの状態。すべてセッションの _cond で守る。
        self._handles: list[StopHandle] = []
        self._stop_errors: list[BaseException] = []
        self._returned: bool = False
        self._dispatching: bool = False
        self._in_call: bool = False
        self._stopped: bool = False

    @property
    def name(self) -> str:
        """ログ用の名前。省略時は関数名になり、重複しても構わない。"""
        return self._name

    @property
    def running(self) -> bool:
        """まだ終わっていなければ `True`。"""
        return not self._done.is_set()

    @property
    def succeeded(self) -> bool:
        """終わったフレームが broken frame でなければ `True`。

        ルーティンが例外なく終わり、配下のセッションがすべて完全で、
        停止コールバックも例外を出さなかったことを表す。
        """
        return self._done.is_set() and not self._stopped and not self._has_failure()

    @property
    def stopped(self) -> bool:
        """停止を要求されたセッションで起動されたため、ルーティンを呼ばずに終わったなら `True`。

        失敗ではないので、承認を求めない。
        """
        return self._stopped

    @property
    def error(self) -> BaseException | None:
        """ルーティンが送出した例外。成功時や実行中は `None`。"""
        return self._error if self._done.is_set() else None

    @property
    def incomplete(self) -> SessionReport | None:
        """配下のセッションが不完全だった場合、その報告。なければ `None`。

        複数のサブセッションが不完全だった場合は、一つにまとめて返す。
        """
        reports = tuple(self._reports)
        return _merge(reports) if reports else None

    @property
    def stop_errors(self) -> tuple[BaseException, ...]:
        """停止コールバックが送出した例外を、送出された順に返す。"""
        return tuple(self._stop_errors)

    def result(self, timeout: float | None = None) -> R_co:
        """ルーティンの戻り値を返す。

        フレームが終わるまで最大 `timeout` 秒待ち、終わらなければ
        `TimeoutError`。ルーティンが例外で終わっていれば、その例外を再送出する。
        配下のセッションが不完全でも、戻り値があれば返す。

        この呼び出しは失敗の承認にはならない。
        """
        if not self._done.wait(timeout):
            raise TimeoutError(f"frame {self._name!r} did not finish in {timeout}s")
        if self._stopped:
            raise FrameStoppedError(f"frame {self._name!r} was stopped before it ran")
        if self._error is not None:
            raise self._error
        return cast("R_co", self._value)

    def wait(self, timeout: float | None = None) -> bool:
        """フレームが終わるまで最大 `timeout` 秒待ち、終わっていれば `True` を返す。

        終わり方によらず例外を送出しない。失敗の承認にもならない。
        """
        return self._done.wait(timeout)

    def ignore(self) -> None:
        """この失敗を想定内として承認する。

        セッションの終了時には何も起きない。配下のセッションの失敗も
        まとめて許したことになる。
        """
        self._session._acknowledge(self, _Mark.IGNORED, "")

    def escalate(self, reason: str = "") -> None:
        """この失敗を想定外として承認し、上へ伝える。

        ルートのセッションの終了時に `SessionFailed` として送出される。
        """
        self._session._acknowledge(self, _Mark.ESCALATED, reason)

    def _has_failure(self) -> bool:
        return self._error is not None or bool(self._reports) or bool(self._stop_errors)

    def _is_broken(self) -> bool:
        return self._done.is_set() and self._has_failure()

    def _run(self) -> None:
        context = Context(self)
        try:
            value = self._fn(context, *self._args)
            if inspect.iscoroutine(value):
                value = asyncio.run(cast("Coroutine[object, object, object]", value))
            self._value = value
        except BaseException as error:  # noqa: BLE001 - フレームの失敗として記録する
            self._error = error
        finally:
            self._finish()

    def _finish(self) -> None:
        cond = self._session._cond
        with cond:
            # ルーティンが戻った後は、まだ呼ばれていないコールバックを呼ばない(STOP_014)。
            self._returned = True
            # 呼び出し中のコールバックが戻るまでは終了しない(STOP_015)。
            while self._in_call:
                _ = cond.wait()
            # ルーティンと引数への参照を手放す(FRAME_013)。
            self._fn = _released
            self._args = ()
            self._handles = []
            self._done.set()
            if not self._is_broken():
                self._session._forget(self)  # 判定に要らない(SESSION_019)
            cond.notify_all()

    def _end_stopped(self) -> None:
        """ルーティンを呼ばずに、stopped として終わらせる(FRAME_012)。"""
        self._fn = _released
        self._args = ()
        self._stopped = True
        self._returned = True
        self._done.set()

    def _register_stop(self, callback: Callable[[], object]) -> StopHandle:
        handle = StopHandle(self, callback)
        with self._session._cond:
            if self._returned:
                # 止めるべき処理がもうないので、呼ばれない登録として扱う。
                handle._state = _Registration.CANCELLED
                return handle
            self._handles.append(handle)
            if self._session._stop.is_set():
                # 停止の後の登録は、要求があったときと同じ方法で呼ぶ(STOP_012)。
                self._start_dispatch()
        return handle

    def _start_dispatch(self) -> None:
        """停止コールバックを呼ぶスレッドを起こす。セッションの _cond を持って呼ぶ。"""
        if self._dispatching or self._returned:
            return
        if not any(h._state is _Registration.PENDING for h in self._handles):
            return
        self._dispatching = True
        threading.Thread(
            target=self._dispatch, name=f"gpframe:{self._name}:on_stop", daemon=True
        ).start()

    def _dispatch(self) -> None:
        """このフレームの停止コールバックを、登録した順に一つずつ呼ぶ(STOP_013)。"""
        cond = self._session._cond
        while True:
            with cond:
                handle = None
                if not self._returned:
                    handle = next(
                        (h for h in self._handles if h._state is _Registration.PENDING),
                        None,
                    )
                if handle is None:
                    self._dispatching = False
                    self._handles = [
                        h for h in self._handles if h._state is _Registration.PENDING
                    ]
                    return
                handle._state = _Registration.CALLED
                self._in_call = True
            error: BaseException | None = None
            try:
                _ = handle._callback()
            except BaseException as caught:  # noqa: BLE001 - フレームの失敗として記録する(STOP_017)
                error = caught
            with cond:
                if error is not None:
                    self._stop_errors.append(error)
                self._in_call = False
                cond.notify_all()

    def __repr__(self) -> str:
        if self.running:
            state = "running"
        elif self._is_broken():
            state = "broken"
        elif self._stopped:
            state = "stopped"
        else:
            state = "succeeded"
        return f"<Frame {self._name!r} {state}>"


class Context:
    """ルーティンの第 1 引数として渡される、フレームの実行環境。"""

    __slots__: tuple[str, ...] = ("_frame",)

    def __init__(self, frame: Frame[object]) -> None:
        self._frame: Frame[object] = frame

    @property
    def name(self) -> str:
        """このフレームの名前。"""
        return self._frame.name

    @property
    def stopping(self) -> bool:
        """このフレームのセッションに停止が要求されていれば `True`。"""
        return self._frame._session.stopping

    def wait_stop(self, timeout: float | None = None) -> bool:
        """`time.sleep()` の代わりに使う待機。

        最大 `timeout` 秒待つ。停止が要求されるとすぐに待ちを打ち切り、
        `True` を返す。時間切れなら `False`。
        """
        return self._frame._session._stop.wait(timeout)

    def on_stop(self, callback: Callable[[], object]) -> StopHandle:
        """停止が要求されたときに呼ぶコールバックを登録する。

        `ctx.stopping` を確認できない、ブロックする処理を止めるために使う
        (たとえば `ctx.on_stop(server.shutdown)`)。

        - 停止がどの経路で要求されても呼ばれ、一つの登録は多くても一度だけ呼ばれる。
        - 停止の後に登録したものは、すぐに呼ばれる。
        - 停止を要求したスレッドとは別のスレッドで、登録した順に一つずつ呼ばれる。
        - ルーティンが戻った後は呼ばれない。
        - 例外を送出すると `Frame.stop_errors` に記録され、フレームは broken になる。

        返されたハンドルの `cancel()` で登録を取り消せる。
        """
        return self._frame._register_stop(callback)

    def session(self, *, timeout: float | None = None) -> Session:
        """このフレームを親とするサブセッションを作る。

        サブセッションは `with` を抜けても例外も警告も出さず、不完全だった
        場合は報告を親フレームに付ける。親のセッションに停止が要求されると、
        サブセッションにも停止が伝わる。
        """
        return Session(timeout=timeout, _owner=self._frame)


class Session:
    """`with` で開き、その中で起動したフレームを管理するスコープ。

    ルートのセッションは `gpframe.session()` で、フレームの中のサブセッションは
    `Context.session()` で作る。
    """

    __slots__: tuple[str, ...] = (
        "_children",
        "_cond",
        "_frames",
        "_owner",
        "_state",
        "_stop",
        "_strict",
        "_timeout",
    )

    def __init__(
        self,
        *,
        timeout: float | None = None,
        strict: bool = False,
        _owner: Frame[object] | None = None,
    ) -> None:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be None or a non-negative number")
        self._timeout: float | None = timeout
        self._strict: bool = strict
        self._owner: Frame[object] | None = _owner
        self._cond: threading.Condition = threading.Condition()
        self._stop: threading.Event = threading.Event()
        # 判定と報告に要るフレームだけを、起動した順に持つ(SESSION_019)。
        self._frames: dict[Frame[object], None] = {}
        self._children: list[Session] = []
        self._state: _State = _State.NEW

    @property
    def stopping(self) -> bool:
        """停止が要求されていれば `True`。"""
        return self._stop.is_set()

    @overload
    def spawn(
        self,
        fn: Callable[[Context, *Ts], Coroutine[object, object, R]],
        *args: *Ts,
        name: str | None = None,
    ) -> Frame[R]: ...

    @overload
    def spawn(
        self,
        fn: Callable[[Context, *Ts], R],
        *args: *Ts,
        name: str | None = None,
    ) -> Frame[R]: ...

    def spawn(
        self,
        fn: Callable[..., object],
        *args: object,
        name: str | None = None,
    ) -> Frame[object]:
        """`fn(context, *args)` を新しいスレッドのフレームとして起動する。

        `fn` は `async def` でもよく、その場合はフレームのスレッド内で専用の
        イベントループを立てて実行する。開いていないセッションでは
        `SessionStateError`。停止が要求された後は、ルーティンを呼ばずに
        stopped のフレームを返す。
        """
        with self._cond:
            if self._state is not _State.OPEN:
                raise SessionStateError("spawn() needs an open session")
            frame = Frame[object](self, fn, args, name or _name_of(fn))
            if self._stop.is_set():
                frame._end_stopped()
            else:
                self._frames[frame] = None
                frame._thread.start()
        return frame

    def wait(self, timeout: float | None = None) -> bool:
        """すべてのフレームが終わるまで最大 `timeout` 秒待つ。

        待っている間に起動されたフレームも待つ。時間内にすべて終われば `True`。
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while any(frame.running for frame in self._frames):
                if deadline is None:
                    _ = self._cond.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                _ = self._cond.wait(remaining)
            return True

    def running(self) -> bool:
        """まだ終わっていないフレームがあれば `True`。"""
        with self._cond:
            return any(frame.running for frame in self._frames)

    def broken(self) -> list[Frame[object]]:
        """まだ承認されていない broken frame を、起動した順に返す。

        `ignore()` か `escalate()` を呼んだフレームは返らないので、
        ポーリングで繰り返し呼んでも同じフレームを二度処理しない。
        """
        with self._cond:
            return self._unacknowledged()

    def wait_broken(
        self, timeout: float | None = None, *, idle: bool = False
    ) -> list[Frame[object]]:
        """最初の失敗を待つ。

        未承認の broken frame が現れるか、実行中のフレームがなくなるか、
        `timeout` 秒が経つまで待ち、その時点の `broken()` を返す。空なら失敗
        以外の理由で戻ったことを表し、どちらの理由かは `running()` で区別できる。
        待っても失敗の承認にはならない。

        `idle=True` なら、実行中のフレームがなくても戻らず、失敗か、停止の
        要求か、時間切れまで待つ。フレームが増減するセッションで使う。
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while True:
                broken = self._unacknowledged()
                if broken:
                    return broken
                if idle:
                    if self._stop.is_set():
                        return broken
                elif not any(frame.running for frame in self._frames):
                    return broken
                if deadline is None:
                    _ = self._cond.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return broken
                _ = self._cond.wait(remaining)

    def stop(self) -> None:
        """すべてのフレームと、その中のサブセッションに停止を要求する。

        停止は協調的で、実際に止まるかどうかはルーティンに委ねられる。
        停止コールバックは別のスレッドで呼ばれ、この呼び出しはその完了を待たない。
        開く前や閉じた後に呼んでもよく、開く前なら開いた時点で止まっている。
        """
        self._stop.set()
        with self._cond:
            children = list(self._children)
            for frame in self._frames:
                frame._start_dispatch()
            self._cond.notify_all()  # wait_broken(idle=True) を起こす
        for child in children:
            child.stop()

    def _unacknowledged(self) -> list[Frame[object]]:
        """未承認の broken frame を起動した順に返す。_cond を持って呼ぶ。"""
        return [f for f in self._frames if f._is_broken() and f._mark is None]

    def __enter__(self) -> Self:
        with self._cond:
            if self._state is not _State.NEW:
                raise SessionStateError("a session can be entered only once")
            self._state = _State.OPEN
        if self._owner is not None:
            parent = self._owner._session
            with parent._cond:
                parent._children.append(self)
                if parent._stop.is_set():
                    self._stop.set()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if exc is not None:
            self.stop()
        _ = self.wait(self._timeout)
        with self._cond:
            self._state = _State.CLOSED
            stuck = tuple(f for f in self._frames if f.running)
            broken = tuple(f for f in self._frames if f._is_broken())
        if stuck:
            # 制御を終えるので、残ったフレームにも止まるよう伝えてから離れる。
            self.stop()

        unacknowledged = tuple(f for f in broken if f._mark is not _Mark.IGNORED)
        if self._owner is not None:
            self._close_sub(unacknowledged, stuck, exc)
        else:
            self._close_root(broken, stuck)
        return False

    def _close_sub(
        self,
        unacknowledged: tuple[Frame[object], ...],
        stuck: tuple[Frame[object], ...],
        exc: BaseException | None,
    ) -> None:
        owner = cast("Frame[object]", self._owner)
        parent = owner._session
        with parent._cond:
            if self in parent._children:
                parent._children.remove(self)
            if unacknowledged or stuck or exc is not None:
                owner._reports.append(
                    SessionReport(
                        broken=unacknowledged,
                        stuck=stuck,
                        errors=() if exc is None else (exc,),
                    )
                )

    def _close_root(
        self, broken: tuple[Frame[object], ...], stuck: tuple[Frame[object], ...]
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
        # broken は起動した順に並んでいる。その順を保って送出の対象を選ぶ。
        failing = [
            f
            for f in broken
            if f._mark is _Mark.ESCALATED or (self._strict and f._mark is None)
        ]
        if failing:
            raise SessionFailed(
                _failure_message(failing),
                [_exception_of(f) for f in failing],
                failing,
            )

    def _acknowledge(self, frame: Frame[object], mark: _Mark, reason: str) -> None:
        with self._cond:
            if not frame._is_broken():
                state = "still running" if frame.running else "did not fail"
                raise FrameStateError(f"frame {frame.name!r} {state}")
            if frame._mark is not None:
                raise FrameStateError(f"frame {frame.name!r} is already acknowledged")
            frame._mark = mark
            frame._reason = reason
            if mark is _Mark.IGNORED:
                self._forget(frame)  # 判定に要らない(SESSION_019)

    def _forget(self, frame: Frame[object]) -> None:
        """判定と報告に要らなくなったフレームを手放す。_cond を持って呼ぶ。"""
        _ = self._frames.pop(frame, None)


def _released(*_args: object) -> object:
    """終わったフレームが、ルーティンの代わりに持つもの。呼ばれることはない。"""
    raise AssertionError("the routine of a finished frame was released")


def session(*, timeout: float | None = None, strict: bool = False) -> Session:
    """ルートのセッションを作る。`with` で開いて使う。

    `with` を抜けるとき、まず最大 `timeout` 秒(`None` なら終わるまで)
    フレームの終了を待つ。そのうえで、止まらなかったフレームと、承認されて
    いない失敗を警告し、`escalate()` された失敗があれば `SessionFailed` を
    送出する。`strict=True` なら、承認されていない失敗も `SessionFailed` に
    含める。
    """
    return Session(timeout=timeout, strict=strict)


def _name_of(fn: Callable[..., object]) -> str:
    name = getattr(fn, "__name__", None)
    return name if isinstance(name, str) else type(fn).__name__


def _exception_of(frame: Frame[object]) -> Exception:
    """`SessionFailed` に入れる、フレームの例外を決める(SESSION_012)。"""
    error = frame.error
    if error is None and frame._stop_errors:
        error = frame._stop_errors[0]
    if isinstance(error, Exception):
        return error
    if error is not None:
        return FrameAbortedError(frame.name, error)
    return IncompleteSessionError(frame.name, _merge(frame._reports))


def _failure_message(frames: Sequence[Frame[object]]) -> str:
    parts: list[str] = []
    for frame in frames:
        reason = frame._reason
        parts.append(f"{frame.name} ({reason})" if reason else frame.name)
    count = len(frames)
    return f"{count} frame{'s' if count != 1 else ''} failed: {', '.join(parts)}"
