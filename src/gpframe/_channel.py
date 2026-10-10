"""フレーム間で値を受け渡す、送受信の待ちが停止で解ける FIFO。"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from typing import Generic, Protocol, TypeVar, cast, final, overload

from gpframe._errors import ChannelClosedError, ChannelFullError, DeclaredTypeError
from gpframe._shared import _is_runtime_class

T = TypeVar("T")

_WAIT = object()
"""`_wait_for` の判定関数が「まだ待つ」ことを表す値。"""


class _Registration(Protocol):
    def cancel(self) -> None: ...


class _StopSource(Protocol):
    """`Channel` が使う `Context` の部分。呼んでいるフレームの `Context` を渡す。"""

    @property
    def stopping(self) -> bool: ...
    def on_stop(self, callback: Callable[[], object]) -> _Registration: ...


@final
class Channel(Generic[T]):
    """型を生成時に決める、フレーム間の先入れ先出しの受け渡し。

    - `get(ctx)` と `receive(ctx)` は、値が届くか、`ctx` のセッションに停止が要求
      されるか、チャネルが閉じられて空になるまで待つ。
    - `maxsize` が正なら容量に上限がある。`put(item, ctx)` は空きが出るまで待ち、
      `ctx` を渡さない `put(item)` は満杯なら `ChannelFullError` を送出する。
    - 停止が要求されている間は、値を取り出しも加えもしない。
    - `None` は入れられないので、`get()` の `None` は「値がない」ことだけを表す。
    """

    __slots__: tuple[str, ...] = ("_closed", "_cond", "_items", "_maxsize", "_type")

    def __init__(self, typ: type[T], maxsize: int = 0) -> None:
        if not _is_runtime_class(typ):
            raise DeclaredTypeError(f"typ must be a runtime class, not {typ!r}")
        if typ is type(None):
            raise DeclaredTypeError("typ must not be NoneType")
        if maxsize < 0:
            raise ValueError("maxsize must be 0 (unbounded) or a positive number")
        self._type: type[T] = typ
        self._maxsize: int = maxsize
        self._cond: threading.Condition = threading.Condition()
        self._items: deque[T] = deque()
        self._closed: bool = False

    @property
    def type(self) -> type[T]:
        """宣言した型。"""
        return self._type

    @property
    def maxsize(self) -> int:
        """容量の上限。0 なら上限なし。"""
        return self._maxsize

    @property
    def closed(self) -> bool:
        """閉じられていれば `True`。"""
        with self._cond:
            return self._closed

    @overload
    def put(self, item: T) -> None: ...
    @overload
    def put(self, item: T, ctx: _StopSource, timeout: float | None = None) -> bool: ...
    def put(
        self, item: T, ctx: _StopSource | None = None, timeout: float | None = None
    ) -> bool | None:
        """`item` を末尾に加える。

        `ctx` を渡さなければ待たずに加える。満杯なら `ChannelFullError`、閉じた後は
        `ChannelClosedError`。`ctx` を渡すと、満杯なら空きが出るまで最大
        `timeout` 秒待ち、加えたら `True` を返す。停止の要求、閉じられること、
        時間切れでは、何も加えずに `False` を返す。型が合わなければ
        `DeclaredTypeError`。
        """
        if item is None or not isinstance(item, self._type):
            raise DeclaredTypeError(
                f"expected {self._type.__qualname__}, got {type(item).__qualname__}"
            )
        _check_timeout(timeout)
        if ctx is None:
            with self._cond:
                if self._closed:
                    raise ChannelClosedError("the channel is closed")
                if self._full():
                    raise ChannelFullError(f"the channel holds {self._maxsize} items")
                self._append(item)
                return None

        def offer() -> object:
            if ctx.stopping or self._closed:
                return False
            if self._full():
                return _WAIT
            self._append(item)
            return True

        return self._wait_for(offer, ctx, timeout, expired=False) is True

    def get(self, ctx: _StopSource, timeout: float | None = None) -> T | None:
        """次の値を取り出す。

        空なら、値が届くか、`ctx` のセッションに停止が要求されるか、閉じられるか、
        `timeout` 秒が経つまで待つ。値がなければ `None` を返す。理由は
        `ctx.stopping` と `closed` で区別できる。
        """
        _check_timeout(timeout)

        def take() -> object:
            if ctx.stopping:
                return None
            if self._items:
                item = self._items.popleft()
                if self._maxsize:
                    self._cond.notify()  # 空きを待つ put() を起こす
                return item
            if self._closed:
                return None
            return _WAIT

        result = self._wait_for(take, ctx, timeout, expired=None)
        return None if result is None else self._typed(result)

    def receive(self, ctx: _StopSource) -> Iterator[T]:
        """`get(ctx)` が値を返す間、その値を順に返す。"""
        while (item := self.get(ctx)) is not None:
            yield item

    def close(self) -> None:
        """もう加えないことを知らせ、待っているすべての送り手と受け取り手を起こす。"""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def _full(self) -> bool:
        return 0 < self._maxsize <= len(self._items)

    def _append(self, item: T) -> None:
        """_cond を持って呼ぶ。"""
        self._items.append(item)
        self._cond.notify()  # 値を待つ get() を起こす

    def _typed(self, value: object) -> T:
        # _items から取り出した値なので、宣言した型であることは put() で確かめてある。
        return cast("T", value)

    def _wait_for(
        self,
        attempt: Callable[[], object],
        ctx: _StopSource,
        timeout: float | None,
        *,
        expired: object,
    ) -> object:
        """`attempt` が `_WAIT` 以外を返すまで、停止で起きられるように待つ。

        値を待つ受け取り手と空きを待つ送り手が同時に待つことはない(空と満杯は
        同時に成り立たない)ので、一つの Condition を共有する。
        """
        with self._cond:
            result = attempt()
            if result is not _WAIT:
                return result
        # 停止で待ちを起こす。停止の後の登録はすぐに呼ばれるので取りこぼさない。
        handle = ctx.on_stop(self._wake)
        try:
            deadline = None if timeout is None else time.monotonic() + timeout
            with self._cond:
                while (result := attempt()) is _WAIT:
                    if deadline is None:
                        _ = self._cond.wait()
                        continue
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return expired
                    _ = self._cond.wait(remaining)
                return result
        finally:
            handle.cancel()  # 登録を残さない(STOP_016)

    def _wake(self) -> None:
        with self._cond:
            self._cond.notify_all()

    def __repr__(self) -> str:
        with self._cond:
            state = "closed" if self._closed else "open"
            size = f"{len(self._items)}/{self._maxsize or '∞'}"
            return f"Channel({self._type.__qualname__}, {state}, {size} items)"


def _check_timeout(timeout: float | None) -> None:
    if timeout is not None and timeout < 0:
        raise ValueError("timeout must be None or a non-negative number")
