"""フレーム間で共有する、型の固定された値。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from gpframe._errors import DeclaredTypeError

T = TypeVar("T")


class Shared(Generic[T]):
    """型と初期値を生成時に決める、スレッドセーフな共有セル。

    - 保持する値は常に宣言した型のインスタンスで、`None` にはならない。
    - `apply()` は読み取りから書き込みまでを一つの操作として行う。

    複数の値を一貫させたいときは、不変のデータクラスを一つの `Shared` に入れ、
    `apply()` で丸ごと差し替える。
    """

    __slots__: tuple[str, ...] = ("_lock", "_type", "_value")

    def __init__(self, typ: type[T], value: T) -> None:
        if not _is_runtime_class(typ):
            raise DeclaredTypeError(f"typ must be a runtime class, not {typ!r}")
        if typ is type(None):
            raise DeclaredTypeError("typ must not be NoneType")
        self._type: type[T] = typ
        self._lock: threading.Lock = threading.Lock()
        self._value: T = self._checked(value)

    @property
    def type(self) -> type[T]:
        """宣言した型。"""
        return self._type

    def get(self) -> T:
        """現在の値を返す。"""
        with self._lock:
            return self._value

    def set(self, value: T) -> None:
        """値を置き換える。型が合わなければ `DeclaredTypeError`。"""
        checked = self._checked(value)
        with self._lock:
            self._value = checked

    def swap(self, value: T) -> T:
        """値を置き換え、置き換える前の値を返す。型が合わなければ `DeclaredTypeError`。"""
        checked = self._checked(value)
        with self._lock:
            previous = self._value
            self._value = checked
            return previous

    def apply(self, fn: Callable[[T], T]) -> T:
        """`fn` で値を更新し、更新後の値を返す。

        `fn` はロックを持ったまま呼ばれるので、短く副作用のない関数にする。
        `fn` が例外を送出した場合と、結果の型が合わない場合(`DeclaredTypeError`)は、
        値は変わらない。
        """
        with self._lock:
            updated = self._checked(fn(self._value))
            self._value = updated
            return updated

    def _checked(self, value: T) -> T:
        if value is None or not isinstance(value, self._type):
            raise DeclaredTypeError(
                f"expected {self._type.__qualname__}, got {type(value).__qualname__}"
            )
        return value

    def __repr__(self) -> str:
        return f"Shared({self._type.__qualname__}, {self.get()!r})"


def _is_runtime_class(value: object) -> bool:
    """`list[int]` のような型式は `isinstance()` で検査できないので、実行時に拒否する。"""
    return isinstance(value, type)
