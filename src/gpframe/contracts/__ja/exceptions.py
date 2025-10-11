
from typing import Protocol


class FrameError(Exception):
    """フレームワーク由来例外のベースクラス"""
    pass

class MissingNameError(FrameError):
    """有効なフレーム名が存在しない場合にスローされる"""
    pass

class CrossContextError(FrameError):
    """サブフレームをそれを生成したコンテキスト以外のコンテキストから
    実行しようとした場合スローされる"""
    pass

class FrameStillRunningError(FrameError):
    """フレームの動作中に削除を試みた場合にスローされる"""
    pass

class UncheckedError(Protocol):
    """フレームが送出した例外の再スロー用ラッパー"""
    @property
    def frame_name(self) -> str:
        """この例外を送出したフレーム名"""
        ...
    @property
    def frame_qualname(self) -> str:
        """この例外を送出したフレームの完全修飾名"""
        ...
    
    @property
    def cause(self) -> BaseException:
        """フレームが送出した例外インスタンス"""
        ...

    def check(self) -> None:
        """フレームが送出した例外(self.cause)をチェック済み例外にする"""
        ...

class MessageError(FrameError):
    """Message由来例外のベースクラス"""

class RedefineError(MessageError):
    """すでに存在するキーを再度設定しようとした場合にスローされる"""
    pass

class MessageKeyError(MessageError, KeyError):
    """キーが存在しない場合にスローされる"""
    pass

class MessageTypeError(MessageError, TypeError):
    """キーが要求する型と一致しない場合スローされる  
    型の不一致は次の2通りが存在する。  
    値がキーが要求する型のインスタンスではない場合(共変でない)。  
    読み書きの際に指定する型がキーが要求する型と同一でない場合(不変でない)。
    """
    pass

class ConsumedError(MessageError):
    """値が存在しない場合にスローされる"""
    pass

class IPCError(MessageError):
    """IPCによる通信由来例外のベースクラス"""
    pass

class IPCValueError(IPCError, ValueError):
    """値のピッケル化が失敗した場合にスローされる"""
    pass

class IPCConnectionError(IPCError):
    """IPCの通信自体が失敗した場合にスローされる"""
    pass

