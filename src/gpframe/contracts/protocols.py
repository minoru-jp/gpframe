"""
---------------------------------------------------------------------------------------
gpframe: 並行・並列処理向け汎用フレームワーク
---------------------------------------------------------------------------------------

このフレームワークは並行処理、並列処理における実行形態の構築のサポート、シームレスな実行形態
の移行、同期的な通信手段の提供、および例外処理のサポートを行う。

用語:
    Frame: このフレームワークの処理単位。
    Routine: 処理の本体。ユーザーの実装。
    Handler: イベントに対応するフックポイントの処理。ユーザーの実装。
    Message: フレーム間または、フレーム外部からのフレームへの通信用インターフェース。

RoutineおよびHandlerは同期/非同期のどちらの関数にも対応している。

=======================================================================================
並行処理・並列処理の分類
=======================================================================================

エントリポイントであるcreate_frameのparallelフラグにより並列か並行かを選択する。
この二つは根本的な分類であり、それ以降のフレームの定義が異なる。

並行ルートフレーム:
    - 各フレーム内部でライフサイクルが管理され、フックポイントにイベントハンドラを適用できる。
    - サブフレームをサブプロセスで動作することはできない。
    - メッセージは非IPCによる通信。

並列ルートフレーム：
    - 各フレームはルーティンのみをサブプロセスで実行し、ライフサイクルおよびイベントハンドラは  
      存在せず、設定することができない。
    - サブフレームもすべて独立したサブプロセスで動作する。
    - local以外のメッセージはすべてIPCによる通信。

    
並列フレームにはハンドラが設定できないが、以下のようにしてコードを変更することなく並行時のみ
ハンドラを設定することができる。
    ```
    root = create_frame("sample", routine, parallel=True)
    try:
        con = RootFrame.as_handler_capable(root) # raises NoHandlerCapableError
        con.set_on_open(...)
    except NoHandlerCapableError:
        pass
    ```

=======================================================================================
メッセージの分類と役割
=======================================================================================

並行処理・並列処理ともに4つのメッセージを提供している。
- enviroment: ユーザーがルートフレームのスタート前に設定して、変更手段が提供されないメッセージ
- request: セッションを通して、外部からフレームへ要求を伝えるためのメッセージ
- common: フレーム間で共有されるメッセージ。
- local: 一つのフレーム内で共有されるメッセージ。

並列処理の場合、Messageの値はすべてピッケル化に対応している必要がある。
ただし、localはオンメモリの非IPCによる通信が可能。

この制約はAPIに定義されているプロトコルから判別ができないので注意。

=======================================================================================
フレームの正常終了と例外終了の非対称性
=======================================================================================

フレームは結果を持たないため、正常終了したフレームに対する操作は限定的になっている。
gather()は主にログ出力とリソース解放（clear_ended_frame）のために使用する。

対照的に、例外は厳密な制御を要求する、drain()、reraise()、raise_if_faulted()など、
状態管理を伴うAPIを提供する。

=======================================================================================
セッションの役割と制御構造
=======================================================================================

セッションは動作中のフレームに対してリクエストを送ったり、終了に伴う例外処理などを行う。

大きく分けて二つの制御構造を提供する。

1. 一括待機
    ```
    with frame.start() as session:
        session.wait_done()
    ```

2. ポーリングによる監視
    ```
    with frame.start() as session:
        while session.running(): # .running()は待機しない
            # 終了したフレームの処理
            if completed := session.gather():
                for name in completed:
                    session.logger.info(f"{name} completed")
            
            # 例外が発生したフレームの処理
            try:
                session.reraise()
            except UncheckedError as e:
                handle_error(e)
                e.check()  # チェック済みに移行
            
            ... # time.sleep(...)などの適切なインターバル
    ```

=======================================================================================
フレームの例外のハンドリング
=======================================================================================

このフレームワークは例外を内部的に未チェック状態とチェック済み状態に分類する。
未チェック状態の例外を残したままwithブロックを抜けた場合、警告を発生する。

フレームが送出した例外はまず未チェック状態になる。

次の動作を行うことにより未チェック状態からチェック済み状態へ移行する
    - session.reraise(unwrap = True)の形で再スローを行った場合。
    - session.reraise()の形でスローを行った場合に、捕捉したUncheckedErrorの
      .check()を呼びだした場合。
    - session.drain()から取得された場合。

タイムアウトを伴うフレームの待機と例外のハンドリング:
    with frame.start() as session:
        ...
        try:
            session.wait_done_and_raise(10) # P1
        except FrameError as e:
            ... # エラー処理
        finally:
            if session.running(): # P2
                # タイムアウトしている
                session.logger.info("end with timeout")
                # さらに待つこともできるが限度がある。
                # 例外のハンドリングを諦めるのはフレームの終了待機を諦めるのと同義。
                session.abandon_unchecked_error()
            else:
                # 時間内に終了したのかと思いきや、実はタイムアウトしていて、P1からP2まで
                # の間に、最後のフレームが終了した可能性がある。それらのフレームが例外を
                # 投げているかもしれないので、残っている未チェック状態の例外を処理しながら
                # セッションを終了する
                session.raise_if_faulted()

                    
=======================================================================================
並行処理用フレームの実行方式とライフサイクル
=======================================================================================

並行処理用フレームの実行方式
---------------------------------------------------------------------------------------
各フレーム（ルート／サブ）は独立したスレッド上で実行される。

  [メインスレッド]
       │
       ├─▶ [フレームスレッド]
       │       └─ サーキット（非同期関数）
       │              ├─ 各ハンドラの実行
       │              └─ ルーティンの実行

---------------------------------------------------------------------------------------


フレーム全体はLOAD->ACTIVE->TERMINATEDと状態を変化して戻ることはない。
つまり、再起動(start()の二重呼び出し)はできない。

次はフレーム内部のライフサイクルの定義

【正常系】
---------------------------------------------------------------------------------------
  on_open
    ↓
  on_start *
    ↓
  routine（メイン処理）
    ↓
  on_end
    ↓
  on_redo
      ├─ True を返す → *（on_start から再実行）
      └─ False を返す → on_close
    ↓
  on_close（shielded：例外・キャンセルの影響を受けず必ず呼ばれる）

【例外発生時の流れ】
---------------------------------------------------------------------------------------
  ...
    ↓
  on_exception（例外ハンドラ）
      ├─ True を返す → 例外を抑制し、正常系として継続
      └─ False を返す → 例外を再スロー
    ↓
  on_close（shielded）
---------------------------------------------------------------------------------------
"""
from __future__ import annotations

from enum import Enum
import logging

from typing import Protocol, Any, Awaitable, Callable, Union, ContextManager, cast

from gpframe._impl.common import _T, _D, _NO_DEFAULT, _noop, _any_str, _any_int, _any_float

class _HasFrameIdentity(Protocol):
    @property
    def frame_name(self) -> str:
        """このフレームの名前"""
        ...
    @property
    def frame_qualname(self) -> str:
        """このフレームの完全修飾名"""
        ...

class _HasSessionIdentity(Protocol):
    @property
    def session_name(self) -> str:
        """このセッションの名前"""
        ...

class _HasLogger(Protocol):
    @property
    def default_logger(self) -> logging.Logger:
        """このセッションが内部的に使用するデフォルトロガー
        .set_logger() が呼ばれていない場合、logger プロパティはこのロガーを返す。
        """
        ...

    def set_logger(self, logger: logging.Logger | str) -> None:
        """ユーザー定義のロガーを設定する
        logger プロパティは指定されたロガーを返す"""
        ...

class _HasLogging(Protocol):
    @property
    def logger(self) -> logging.Logger:
        ...

class _HasFrameCoordinating(Protocol):

    def running(self) -> bool:
        """フレームが実行中かどうかを判定する"""
        ...
    
    def get_frame_status(self, frame_name: str) -> tuple[bool, BaseException | None]:
        """フレームの実行状態を取得する
        実行中であるか否かを表すフラグとエラー(なければNone)のtupleを返す。
        このメソッドで取り出された例外はチェック済みにならない。
        frame_nameが指すフレームが存在しない場合KeyError。
        """
        ...

    def clear_ended_frame(
            self, frame_name: str, *, suppress: bool = False, log: bool = False
    ) -> None:
        """終了済みサブフレームを削除する
        フレームが終了していない場合FrameStillRunningError。
        frame_nameが指すフレームが存在しない場合KeyError。
        フレームが未チェック状態の例外を持っていた場合、警告が発生する。
        suppressがTrueの場合、未チェック状態の例外に対する警告は抑制される。
        suppressの値に関わらずlogがTrueなら未チェック状態の例外はログされる。
        .abandon_unchecked_error()の呼び出しの有無には影響されない。
        """
        ...
    
    def gather(self) -> list[str] | None:
        """終了したフレーム名を取得する
        呼び出した時点で例外を伴わずに終了しているフレーム名のリストを返す。
        一度返したフレーム名を二度と返さない。
        .clear_ended_frame()で消去されたフレーム名は含まれない。
        """
        ...
    
    def reraise(self, *, unwrap: bool = False) -> None:
        """フレームの例外をUncheckedErrorでラップして送出する
        unwrapがTrueであれば、例外はUncheckedErrorにラップされずに元の例外がスローされる。
        ラップされずに例外が送出された場合、その例外はチェック済みとなる。
        一度スローした例外は未チェック状態のままであっても二度とスローされない。
        """
        ...

    def wait_done(self, timeout: float | None = None) -> None:
        """フレームの終了を待ち合わせる
        timeoutにfloat(sec)が渡され、その時間内にフレームが完了しなかった場合。待機を中断する。
        """
        ...
    
    def wait_done_and_raise(self, timeout: float | None = None) -> None:
        """フレームの終了を待ち合わせる
        timeoutにfloat(sec)が渡され、その時間内にフレームが完了しなかった場合。待機を中断する。
        待ち合わせが完了またはタイムアウトした時点で、未チェック状態の例外が存在すればそれらを
        CollectedErrorでラップして送出する。
        """
        ...

    def faulted(self) -> bool:
        """未チェック状態の例外の有無を判定する"""
        ...
    
    def raise_if_faulted(self):
        """未チェック状態の例外がある場合CollectedErrorでラップしてスローする"""
    
    def drain(self) -> dict[str, BaseException] | None:
        """未チェック状態の例外をチェック状態にして取得する
        未チェック例外が存在しない場合、Noneを返す。
        """
        ...
    
    def peek_drain(self) -> dict[str, BaseException] | None:
        """未チェック状態の例外をチェック状態にせず取得する
        未チェック例外が存在しない場合、Noneを返す。
        """
        ...

    def abandon_unchecked_errors(self, log: bool = True) -> None:
        """未チェック状態の例外に対する警告を抑制する  
        このメソッドはフレームの一部が予定通りに終了せず、それらのフレームのハンドリングを放棄して、
        自身を終了させる直前に使用することが想定されている。  
        この呼び出し以降、警告の抑制を解除する手段は提供されない。  
        logがTrueの場合、警告のかわりにログされる。
        """
        ...
    
class _HasHandlerSetting(Protocol):
    def set_on_exception(self, handler: ExceptionHandler) -> None:
        ...
    def set_on_redo(self, handler: RedoHandler) -> None:
        ...
    def set_on_open(self, handler: EventHandler) -> None:
        ...
    def set_on_start(self, handler: EventHandler) -> None:
        ...
    def set_on_end(self, handler: EventHandler) -> None:
        ...
    def set_on_close(self, handler: EventHandler) -> None:
        ...

KeyType = Union[str, Enum]

class MessageReader(Protocol):
    """メッセージ読み取り用インターフェース  
    メッセージはIPCで接続されている場合がある。  
    この時IPCの接続に問題があり、読み取りが失敗した場合IPCConnectionError
    """
    def get_any(self, key: KeyType, default: Any = _NO_DEFAULT) -> Any:
        """キーに対応する値を取得する。
        defaultが設定されていない状態でkeyに対応する値が無ければKeyError
        """
        ...
    def get_or(self, key: KeyType, typ: type[_T], default: _D) -> _T | _D:
        """キーに対応する値をデフォルト値を伴って取得する。  
        keyに対応する値がある場合、typによる型チェックを行った後値を返す。  
        型チェックが通らない場合、TypeErrorを送出。  
        対応する値が存在せず、default値を返す場合、型チェックは行われない。
        """
        ...
    def get(self, key: KeyType, typ: type[_T]) -> _T:
        """キーに対応する値を取得する
        キーに対応する値がない場合、KeyErrorを送出。値がtyp型と互換性が無ければTypeError
        """
        ...
    def string(
        self,
        key: KeyType,
        default: Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[str], bool] = _any_str,
    ) -> str:
        """キーに対応する値を文字列として取得する
        値の型が何であっても前もってstr()を用いて文字列に変換される。
        キーに対応する値が存在せず、defaultが設定されていない場合KeyError。
        prepは文字列に前もって行う処理を指定する。
        validはバリデーターを指定して、それがFalseを返した場合ValueError
        """
        ...
    def string_to_int(
        self,
        key: KeyType,
        default: int | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[int], bool] = _any_int,
    ) -> int:
        """キーに対応する値をintとして取得する
        値の型が何であっても前もってstr()を用いて文字列に変換される。
        キーに対応する値が存在せず、defaultが設定されていない場合KeyError。
        prepは文字列に前もって行う処理を指定する。
        validはバリデーターを指定して、それがFalseを返した場合ValueError
        """
        ...
    def string_to_float(
        self,
        key: KeyType,
        default: float | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[float], bool] = _any_float,
    ) -> float:
        """キーに対応する値をfloatとして取得する
        値の型が何であっても前もってstr()を用いて文字列に変換される。
        キーに対応する値が存在せず、defaultが設定されていない場合KeyError。
        prepは文字列に前もって行う処理を指定する。
        validはバリデーターを指定して、それがFalseを返した場合ValueError
        """
        ...
    def string_to_bool(
        self,
        key: KeyType,
        default: bool | Any = _NO_DEFAULT,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        true: tuple[str, ...] = (),
        false: tuple[str, ...] = (),
    ) -> bool:
        """キーに対応する値をboolとして取得する
        値の型が何であっても前もってstr()を用いて文字列に変換される。
        キーに対応する値が存在せず、defaultが設定されていない場合KeyError。
        prepは文字列に前もって行う処理を指定する。
        trueとfalseにはそれぞれ、TrueとFalseに解釈する文字列を指定する。
        どちらも指定しなかった場合bool(string)(:空文字列でなけばTrue)を返す。
        どちらか一方のみ指定した場合、string in trueまたはstring in falseを返す。
        """
        ...


class MessageUpdater(MessageReader, Protocol):
    """メッセージ更新用インターフェース  
    メッセージの値がピッケル化可能に制限されている場合がある(IPC使用時)。  
    MessageUpdaterはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピッケル化に関してエラーが起こった場合IPCValueError  
    IPCの接続に問題があり、更新できなかった場合IPCConnectionError
    """
    def update(self, key: KeyType, value: _T) -> _T:
        """キーに対して値を設定する
        更新後の値を返す。
        更新前の値と更新しようとしている値に型互換性が無ければTypeError
        更新前の値が存在していない場合は型チェックは行われない。
        """
        ...
    
    def swap(self, key: KeyType, value: _T, default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
        """キーに対して値を設定する
        更新前の値を返す。
        キーに対する値が存在せず、defaultも設定されていない場合KeyError
        defaultが使用された場合、それが更新後の値として設定される。また、
        更新前の値としても使用され、それが返る。
        更新前の値と更新しようとしている値に型互換性が無ければTypeError
        更新前の値が存在していない場合は型チェックは行われない。
        """
        ...

    def apply(self, key: KeyType, typ: type[_T], fn: Callable[[_T], _T], default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
        """キーに対応する値の読み取りと更新を同時に行う
        更新後の値を返す。
        keyに対応する値が存在せず、defaultが設定されていない場合KeyError。
        defaultがtypと型に互換性のない場合TypeError。
        defaultにはfnは適用されない。
        キーに対応する値が存在する場合、typと型に互換性がない場合TypeError。
        fnがtypと型に互換性がない値を返した場合TypeError。
        """
        ...
    def remove(self, key: KeyType, default: Any = None) -> Any:
        """キーに対応した値を削除し、返す
        キーに対応する値が存在しない場合でも例外を送出せず、default値を返す。
        """
        ...

class Context(_HasFrameIdentity, _HasLogging, Protocol):
    """RoutineまたはHandlerに提供される実行インターフェース  
    RoutineおよびHandler内で利用されることを前提とする。  
    フレーム終了後にContextを保持・再利用することはできない。  
    """
    @property
    def environment(self) -> MessageReader:
        """環境変数  
        不変の読み取り専用メッセージ
        """
        ...
    
    @property
    def request(self) -> MessageReader:
        """フレームに対する要求・指示  
        SessionまたはCoordinaterが更新する。
        """
        ...

    @property
    def local(self) -> MessageUpdater:
        """フレーム内の共有状態  
        このフレームの内部（=このContext）からのみ更新を行う。
        このメッセージは常に非IPC(オンメモリ)である。
        """
        ...
    
    @property
    def common(self) -> MessageUpdater:
        """フレーム間の共有状態  
        すべてのフレームとSubFrameSessionが更新を行う。  
        ルートフレームがParallelRootFrameの場合、このメッセージに対する値はピッケル化
        可能でなくてはならない
        """
        ...

    def create_subframe(self, frame_name: str, routine: Routine) -> SubFrame:
        """フレームにサブフレームを追加する
        frame_nameがすでにこのフレームに存在する場合ValueError
        """
        ...
    
    @staticmethod
    def as_handler_capable(subframe: SubFrame) -> ConcurrentSubFrame:
        """引数をConcurrentSubFrameにキャストして返す
        subframeがConcurrentSubFrameでない場合NoHandlerCapableError
        """
        ...
    
    def start_subframes(
            self, *subframes: SubFrame
        ) -> ContextManager[SubFrameSession]:
        """複数のサブフレームをスタートし、コーディネーターを返す
        サブフレームはself.create_subframe()またはself.create_ipc_subframe()で
        作成されたサブフレームでなければならない。他のContextによって作成された
        サブフレームを指定した場合CrossContextError
        subframesが空ならValueError
        """
        ...

Routine = Callable[[Context], Any] | Callable[[Context], Awaitable[Any]]


EventHandler = Union[
    Callable[[Context], None],
    Callable[[Context], Awaitable[None]],
]

ExceptionHandler = Union[
    Callable[[Context, BaseException], bool],
    Callable[[Context, BaseException], Awaitable[bool]]
]

RedoHandler = Union[
    Callable[[Context,], bool],
    Callable[[Context,], Awaitable[bool]],
]


class SessionBase(_HasSessionIdentity, _HasLogger, _HasLogging, _HasFrameCoordinating, Protocol):
    @property
    def environment(self) -> MessageReader:
        """環境変数  
        不変の読み取り専用メッセージ
        """
        ...
    
    def set_session_name(self, name: str) -> None:
        """このセッションの名前を設定する"""
        ...
    
    def offer_frame_stop(self, force: bool = False) -> None:
        """フレーム、サブフレームの停止を試みる  
        forceがTrueであれば並列処理時にプロセスに対して.kill()を使用する。  
        Falseなら.terminate()を使用する。  
        並行処理においてはこのフラグは現時点で意味を持たない
        """
        ...
    
class RootFrameSession(SessionBase, Protocol):
    def _for_root(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...
    @property
    def request(self) -> MessageUpdater:
        """フレームに対する要求・指示  
        ルートフレームがParallelRootFrameの場合、このメッセージに対する値はピッケル化
        可能でなくてはならない
        """
        ...

    @property
    def common(self) -> MessageReader:
        """フレーム間の共有状態  
        SessionまたはCoordinaterからは読み取りのみ
        """
        ...

class SubFrameSession(_HasFrameCoordinating, Protocol):
    """サブフレーム群の部分的な同期を制御するためのセッション
    Messageの読み書きは提供されない。Messageの読み書きにはContextを使用する。
    """
    def _for_subframe(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class RootFrame(_HasFrameIdentity, _HasLogger, Protocol):
    def set_environments(self, environments: dict[str, Any]) -> None:
        """環境変数の初期値を設定する"""
        ...
    def set_requests(self, requests: dict[str, Any]) -> None:
        """リクエストの初期値を設定する"""
        ...

    def start(self) -> ContextManager[RootFrameSession]:
        """このフレームを開始する
        フレームのセッションはコンテキストマネージャーを通して取得する。
        """
        ...

    @staticmethod
    def as_handler_capable(rootframe: RootFrame) -> ConcurrentRootFrame:
        """引数をConcurrentRootFrameにキャストして返す
        rootframeがConcurrentRootFrameでない場合NoHandlerCapableError
        """
        ...

class ConcurrentRootFrame(RootFrame, _HasHandlerSetting, Protocol):
    def _for_concurrent(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ParallelRootFrame(_HasFrameIdentity, _HasLogger, Protocol):
    def _for_parallel(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...


class SubFrame(_HasFrameIdentity, _HasLogger, Protocol):
    """サブフレームのベースプロトコル
    SubFrameはそれ自体を単独で起動することができない。  
    起動にはContext.start_subframes()を使用する。
    """
    def _for_subframe(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ConcurrentSubFrame(SubFrame, _HasHandlerSetting, Protocol):
    def _for_concurrent(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ParallelSubFrame(SubFrame, Protocol):
    def _for_parallel(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

def create_frame(
        frame_name: str, routine: Routine, *, parallel: bool = False
    ) -> ConcurrentRootFrame | ParallelRootFrame:
    """ルートフレームを作成する  
    parallelがTrueならParallelRootFrame、FalseならConcurrentRootFrameを返す。  
    ParallelRootFrameはハンドラ非対応であり、ConcurrentRootFrameはハンドラ対応する。  
    """
    ...

def create_concurrent_frame(frame_name: str, routine: Routine) -> ConcurrentRootFrame:
    """並行ルートフレームを作成する
    このルートフレームはハンドラを設定することができる。
    """
    return cast(ConcurrentRootFrame, create_frame(frame_name, routine, parallel = False))

def create_parallel_frame(frame_name: str, routine: Routine) -> ParallelRootFrame:
    """並列ルートフレームを作成する
    このルートフレームはハンドラを設定することできない。
    """
    return cast(ParallelRootFrame, create_frame(frame_name, routine, parallel = True))

