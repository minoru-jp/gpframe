"""gpframe が送出する、セッションに依存しない例外と警告。"""

from __future__ import annotations

from typing import final


class GpFrameError(Exception):
    """gpframe が送出する例外の基底クラス。

    ただし `SessionFailed` は `ExceptionGroup` なので、この基底クラスを持たない。
    """


class SessionStateError(GpFrameError):
    """開いていないセッションに対して、開いている必要のある操作をした。"""


@final
class FrameStoppedError(GpFrameError):
    """stopped のフレームの結果を求めた。

    停止を要求されたセッションで起動されたフレーム(同期版・非同期版)と、
    停止の要求によるキャンセルで終わった非同期のフレームは、値を持たない。
    """


@final
class FrameStateError(GpFrameError):
    """フレームの状態に合わない操作をした。

    失敗していないフレームの承認や、承認済みフレームの再承認で送出される。
    """


@final
class DeclaredTypeError(GpFrameError, TypeError):
    """`Shared` や `Channel` に、宣言した型に合わない値を渡した。"""


@final
class ChannelClosedError(GpFrameError):
    """閉じた `Channel` に値を加えようとした。"""


@final
class ChannelFullError(GpFrameError):
    """満杯の `Channel` に、待たずに値を加えようとした(`ctx` を渡さない `put()`)。"""


@final
class FrameAbortedError(GpFrameError):
    """フレームが `Exception` 以外の `BaseException` で終わった。

    `SessionFailed` は `ExceptionGroup` なので、その中では元の例外を
    `__cause__` に持つこの例外で包む。
    """

    def __init__(self, frame_name: str, error: BaseException) -> None:
        super().__init__(f"frame {frame_name!r} aborted with {type(error).__name__}")
        self.frame_name: str = frame_name
        self.__cause__ = error


@final
class FrameWarning(UserWarning):
    """承認されていない失敗や、止まらなかったフレームの報告。"""
