"""
---------------------------------------------------------------------------------------
gpframe: 並行・並列処理のための統合制御フレームワーク
---------------------------------------------------------------------------------------

このフレームワークは並行処理、並列処理における実行形態の構築のサポート、シームレスな実行形態
の移行、同期的な通信手段の提供、および例外処理のサポートを行う。

想定するユースケース
    - 複数のアプリケーションコンポーネントの連結と制御

        +-----------------------------+
        |           gpframe           |
        |-----------------------------|
        | - Lifecycle management      |
        | - Inter-frame communication |
        | - Unified error handling    |
        | - Shared state management   |
        +-----------------------------+
            |           |           |
        +---v---+   +---v---+   +---v---+
        |HTTP   |   |Worker |   |  CLI  |
        |Server |   |Task   |   | Input |
        +-------+   +-------+   +-------+

    - 同期的な処理が必要なシステムの基礎


概念:
    Frame: このフレームワークの処理単位。Routine の実行とそのライフサイクルを管理する。
    Routine: 処理の本体。ユーザーの実装。
    Context: ユーザーの実装にフレームのメタ情報、メッセージチャンネルを提供する実行環境。
    Message: フレーム間または、フレーム外部からのフレームへの通信用インターフェース。
    Session: フレーム群を制御し、共有メッセージを定義・監視する制御層。
    Handler: イベントに対応するフックポイントの処理。ユーザーの実装。
    
RoutineおよびHandlerは同期/非同期のどちらの関数にも対応している。

=======================================================================================
インポート
=======================================================================================

ユーザーが明示的にインポートする必要がある実体はcreate_frame(エントリポイント)とContext

最小構成
    from gpframe import create_frame, Context

    def routine(ctx: Context):
        ctx.logger.info("hellow gpframe!")
        
    root = create_frame(routine)

    with root.start() as session:
        session.wait_done_and_raise()


エントリポイントは他にcreate_concurret_frameとcreate_parallel_frameがある。
並行処理と並列処理を固定して生成する場合に使用する。

このAPIに定義されているそのほかのプロトコルはIDEによる補完用にあるものでユーザーは直接
インポートまたは生成する必要はない。

=======================================================================================
並行処理・並列処理の分類
=======================================================================================

エントリポイントであるcreate_frameのsubprocessフラグにより並列か並行かを選択する。
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

    root = create_frame(routine, subprocess = True, handler = False)
    try:
        con = root.as_handler_capable() # raises NoHandlerCapableError
        con.set_on_open(...)
    except NoHandlerCapableError:
        pass
        
ただし、これはHandlerがなくてもRoutineが動くように設計されている場合のみ採用できるあくまでも
選択的なやり方であり、並行並列を切り替える必要がない場合はcreate_concurrent_frame()または
create_parallel_frame()を明示して使う。

=======================================================================================
メッセージの仕様と分類
=======================================================================================

メッセージはキーと値からなり、次の仕様に従う。
- キーおよび値にNoneを設定することはできない。
- キーは一度作成されると「定義済み」となり、型情報と共に値が削除されても存在し続ける。
- 一度定義済みのキーを再度定義することはできない。
- 値はキーの定義と同時に有効なものを型情報と共に設定する必要がある。
- 値はインターフェースを介して削除することができ。これを「消費済み」と表現する。

並行処理・並列処理ともに4つのメッセージチャンネルを提供している。
    - enviroment:
        不変メッセージチャンネル。RootFrameのスタート前に設定され、更新手段が提供されない。
        各セクションは読み取りのみを行う。
        Session, Frame(via Context) -> MessageReader
    - request:
        Sessionを通して、各フレームへ要求を伝えるためのメッセージチャンネル。
        メッセージはSessionで定義と更新を行い、各フレームは読み取りのみを行う。
        Session -> MessageManager
        Frame(via Context) -> MessageReader
    - common:
        フレーム間で共有されるメッセージチャンネル。
        メッセージはSessionで定義を行い、各フレームは更新・読み取りを行う。
        Session -> MessageDefiner
        Frame(via Context) -> MessageUpdater
    - local:
        一つのフレーム内で共有されるメッセージ。
        メッセージはフレーム内で定義・更新・読み取りを行う。
        他のセクションまたはフレーム間では共有されない。
        常にオンメモリ(非IPC)
        Session -> no supplied
        inter-Frame -> no supplied
        intra-Frame(via Context) -> MessageManager

注意:
    並列処理の場合、localを除くMessageの値はすべてIPCを用いるのでピッケル化に対応している
    必要がある。この制約はAPIに定義されているプロトコルから判別ができないので注意。


=======================================================================================
フレームの正常終了と例外終了の非対称性
=======================================================================================

フレームは結果を持たないため、正常終了したフレームに対する操作は限定的になっている。
gather()は主にログ出力とリソース解放（clear_ended_frame）のために使用する。

対照的に、例外は厳密な制御を要求する、drain()、reraise()、raise_if_faulted()など、
状態管理を伴うAPIを提供する。

=======================================================================================
Sessionの役割と制御構造
=======================================================================================

セッションは動作中のフレームの待機、リクエストの送信、終了に伴う例外処理などを行う。

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
            
            time.sleep(1)
    ```

1と2の組み合わせ。
    ```
    # 特定のフレーム(target)のみハンドリングしてあとは一括待機
    with frame.start() as session:
        while session.running():
            if completed := session.gather():
                if target in completed:
                    break
            try:
                session.reraise()
            except UncheckedError as e:
                if target == e.frame_name:
                    e.check()
                    break
            time.sleep(1)

        session.wait_done()
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
                session.abandon_unchecked_errors()
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

from gpframe._impl.common import _T, _noop, _any_str, _any_int, _any_float


import threading # noqa: F401  # for documentation / conceptual dependency
import asyncio # noqa: F401  # for documentation / conceptual dependency
import multiprocessing # noqa: F401  # for documentation / conceptual dependency


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
        .abandon_unchecked_errors()の呼び出しの有無には影響されない。  
        """
        ...
    
    def gather(self) -> list[str]:
        """終了したフレーム名を取得する  
        呼び出した時点で例外を伴わずに終了しているフレーム名のリストを返す。  
        例外を伴わず終了したフレームが存在しない場合、空のリストを返す。  
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
        """未チェック状態の例外がある場合CollectedErrorでラップしてスローする
        スローされた例外はすべてチェック済み例外となる。
        """
        ...
    
    def drain(self) -> dict[str, BaseException]:
        """未チェック状態の例外をチェック状態にして取得する
        未チェック例外が存在しない場合、空のdictを返す。
        """
        ...
    
    def peek_drain(self) -> dict[str, BaseException]:
        """未チェック状態の例外をチェック状態にせず取得する
        未チェック例外が存在しない場合、空のdictを返す。
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


def create_frame(
        routine: Routine,
        *,
        frame_name: str = "",
        subprocess: bool = False,
        handler: bool = True
    ) -> ConcurrentRootFrame | ParallelRootFrame:
    """ルートフレームを作成する  
    subprocessがTrueならParallelRootFrame、FalseならConcurrentRootFrameを返す。  
    ParallelRootFrameはハンドラ非対応であり、ConcurrentRootFrameはハンドラ対応する。  
    frame_nameにはこのフレームの名前を指定する。  
    frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
    どちらからも有効な識別子を得ることができなければFrameNameError  
    handlerがFalseの場合、フレームがハンドラ対応にしていてもハンドラの設定を拒絶する。  
    frame.as_handler_capable()はNoHandlerCapableErrorを送出するようになる。  
    subprocessがTrueの場合、handlerフラグは無視される。
    """
    ...

def create_concurrent_frame(
        routine: Routine,
        *,
        frame_name: str = "",
        handler: bool = True
    ) -> ConcurrentRootFrame:
    """並行ルートフレームを作成する  
    このルートフレームはハンドラを設定することができる。  
    frame_nameにはこのフレームの名前を指定する。  
    frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
    どちらからも有効な識別子を得ることができなければFrameNameError  
    handlerがFalseの場合、ハンドラの設定を拒絶する。  
    frame.as_handler_capable()はNoHandlerCapableErrorを送出するようになる。  
    """
    return cast(ConcurrentRootFrame, create_frame(
        routine, frame_name = frame_name, subprocess = False, handler = handler)
    )

def create_parallel_frame(routine: Routine, frame_name: str = "") -> ParallelRootFrame:
    """並列ルートフレームを作成する  
    このルートフレームはハンドラを設定することできない。  
    frame_nameにはこのフレームの名前を指定する。  
    frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
    どちらからも有効な識別子を得ることができなければFrameNameError  
    """
    return cast(ParallelRootFrame, create_frame(
        routine, frame_name = frame_name, subprocess = True, handler = False)
    )


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
    def local(self) -> MessageManager:
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

    def create_subframe(self, routine: Routine, frame_name: str = "", handler: bool = True) -> SubFrame:
        """フレームにサブフレームを追加する  
        frame_nameがすでにこのフレームに存在する場合ValueError  
        frame_nameにはこのフレームの名前を指定する。  
        frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
        どちらからも有効な識別子を得ることができなければFrameNameError  
        handlerがFalseの場合、フレームがハンドラ対応にしていてもハンドラの設定を拒絶する。  
        frame.as_handler_capable()はNoHandlerCapableErrorを送出するようになる。  
        フレームがハンドラに対応していない場合、handlerフラグは無視される。
        """
        ...
    
    def as_handler_capable(self) -> ConcurrentSubFrame:
        """引数をConcurrentSubFrameにキャストして返す  
        subframeがConcurrentSubFrameではない、またはハンドラを明示的に拒絶している場合
        NoHandlerCapableError
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



class Message(Protocol):
    pass

KeyType = Union[str, Enum]

class MessageReader(Message, Protocol):
    """同期化メッセージ読み取り用インターフェース  
    メッセージはIPCで接続されている場合がある。  
    この時IPCの接続に問題があり、読み取りが失敗した場合IPCConnectionError
    """
    def get(self, key: KeyType, typ: type[_T]) -> _T:
        """キーに対応する値を取得する
        キーに対応する値がない場合MessageKeyError  
        typがkeyが要求する型と同一でなければMessageTypeError  
        """
        ...

    def string(
        self,
        key: KeyType,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[str], bool] = _any_str,
    ) -> str:
        """文字列を取得する  
        値の取得はself.get(key, str)と同義  
        prepは文字列に前もって行う処理を指定する。  
        validはバリデーターを指定して、それがFalseを返した場合MessageValueError  
        """
        ...

    def string_to_int(
        self,
        key: KeyType,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[int], bool] = _any_int,
    ) -> int:
        """文字列をintに変換して取得する  
        値の取得はself.get(key, str)と同義  
        prepは文字列に前もって行う処理を指定する。  
        validはバリデーターを指定して、それがFalseを返した場合MessageValueError  
        変換はint(string, 0)で行う。
        """
        ...

    def string_to_float(
        self,
        key: KeyType,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        valid: Callable[[float], bool] = _any_float,
    ) -> float:
        """文字列をfloatに変換して取得する
        値の取得はself.get(key, str)と同義  
        prepは文字列に前もって行う処理を指定する。  
        validはバリデーターを指定して、それがFalseを返した場合MessageValueError  
        変換はfloat(string)で行う。
        """
        ...
        
    def string_to_bool(
        self,
        key: KeyType,
        *,
        prep: Callable[[str], str] | tuple[Callable[[str], str], ...] = _noop,
        true: tuple[str, ...] = (),
        false: tuple[str, ...] = (),
    ) -> bool:
        """文字列をboolに変換して取得する  
        値の取得はself.get(key, str)と同義  
        prepは文字列に前もって行う処理を指定する。  
        trueとfalseにはそれぞれ、TrueとFalseに解釈する文字列を指定する。  
        どちらも指定しなかった場合bool(string)(:空文字列でなけばTrue)を返す。  
        どちらか一方のみ指定した場合、string in trueまたはstring in falseを返す。  
        いずれかの方法でも変換が行われなかった場合MessageValueError
        """
        ...



class MessageUpdater(MessageReader, Protocol):
    """同期化メッセージ更新用インターフェース  
    メッセージの値がピッケル化可能に制限されている場合がある(IPC使用時)。  
    MessageUpdaterはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピッケル化に関してエラーが起こった場合IPCValueError  
    IPCの接続に問題があり、更新できなかった場合IPCConnectionError
    """


    def set(self, key: KeyType, typ: type[_T], value: _T) -> None:
        """値を無条件に更新する  
        キーが存在しない場合はMessageKeyError。  
        typがkeyの要求する型と同一でなければMessageTypeError
        valueがkeyの要求する型のインスタンスでない場合MessageTypeError  
        """
    
    def swap(self, key: KeyType, typ: type[_T], value: _T) -> _T:
        """値を入れ替え、更新前の値を返す  
        キーが存在しない場合はMessageKeyError  
        値が消費済みである場合はMessageConsumedError  
        typがkeyの要求する型と同一でなければMessageTypeError  
        valueがkeyの要求する型のインスタンスでない場合MessageTypeError  
        """
        ...

    def apply(self, key: KeyType, typ: type[_T], fn: Callable[[_T], _T]) -> _T:
        """値を反映して更新し、更新後の値を返す  
        キーが存在しない場合はMessageKeyError  
        値が消費済みである場合はMessageConsumedError  
        typがkeyの要求する型と同一でなければMessageTypeError  
        fnの戻り値がkeyの要求する型のインスタンスでない場合MessageTypeError  
        """
        ...
    
    def offer(self, key: KeyType, value: Any) -> bool:
        """値が存在しない場合のみ設定する  
        キーが存在しない場合はMessageKeyError  
        値が消費済みの場合、新しい値を設定し、Trueを返す。  
        値が消費済みでない場合は設定を行わず、Falseを返す。  
        """
        ...

    def ensure(self, key: KeyType, value: Any) -> bool:
        """値が存在する場合のみ設定する  
        キーが存在しない場合はMessageKeyError  
        値が消費済みでない場合、新しい値を設定し、Trueを返す。  
        値が消費済みの場合、設定を行わず、Falseを返す。  
        """
        ...
    
    def consume(self, key: KeyType, typ: type[_T]) -> _T:
        """値を削除する。削除した返す  
        キーが存在しない場合はMessageKeyError  
        キー自体は削除されない。  
        削除された値は「消費済み」として扱われる。  
        typがkeyの要求する型と同一でなければMessageTypeError  
        値が消費済みである場合はMessageConsumedError  
        """
        ...
    
    def consume_and(self, key: KeyType, typ: type[_T], value: _T) -> _T:
        """値を削除して新たな値を設定する。削除した値を返す  
        キーが存在しない場合はMessageKeyError  
        キー自体は削除されない。  
        typがkeyの要求する型と同一でなければMessageTypeError  
        valueがkeyの要求する型のインスタンスでなければMessageTypError  
        値が消費済みである場合はMessageConsumedError  
        """
        ...
    
    def batch(self) -> ContextManager[BatchOperator]:
        """不可分操作用のBatchOpertorを取得する  
        ロックを保持したままメッセージに対して複数の処理を行う。  
        withブロック内ではロックを保持しているので、BatchOperatorが提供する
        以外のメソッドを使用してメッセージを操作した場合、デッドロック
        が発生するので注意。
        """
        ...

class MessageDefiner(MessageReader, Protocol):
    """同期化メッセージ定義用インターフェース  
    メッセージの値がピッケル化可能に制限されている場合がある(IPC使用時)。  
    MessageDefinerはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピッケル化に関してエラーが起こった場合IPCValueError  
    IPCの接続に問題があり、更新できなかった場合IPCConnectionError
    """
    def define(self, key: KeyType, typ: type[_T], value: _T) -> None:
        """キーを定義し型と値を設定する  
        すでに定義済みのキーであった場合DefinedKeyError  
        typにtype(None)を指定した場合MessageTypeError  
        valueがtypのインスタンスでない場合MessageTypeError  
        """
        ...

class MessageManager(MessageUpdater, MessageDefiner, Protocol):
    """同期化メッセージ定義・更新用(フルコントロール)インターフェース  
    メッセージの値がピッケル化可能に制限されている場合がある(IPC使用時)。  
    MessageManagerはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピッケル化に関してエラーが起こった場合IPCValueError  
    IPCの接続に問題があり、更新できなかった場合IPCConnectionError
    """
    pass

class BatchOperator(Protocol):
    """メッセージの不可分操作用オペレーター  
    値の読み書きとクエリを提供する。  
    既存キーに対してのみ操作を行うことができる。  
    keyの新規作成はMessageUpdater.embed()を使用する。
    """
    def exists_key(self, key: KeyType) -> bool:
        """キーが存在するか判定する"""
        ...

    def get_value(self, Key: KeyType, typ: type[_T]) -> _T:
        """値を取得する  
        キーが存在しない場合はMessageKeyError  
        値が消費済みである場合はMessageConsumedError  
        """
        ...

    def consumed(self, key: KeyType) -> bool:
        """値の消費済みを判定する"""
        ...
    
    def set_value(self, key: KeyType, value: Any) -> None:
        """値を更新する  
        キーが存在しない場合はMessageKeyError。  
        valueがkeyの要求する型のインスタンスでない場合MessageTypeError  
        """
        ...
    
    def consume_value(self, key: KeyType, typ: type[_T]) -> _T:
        """値を削除する。削除した値を返す
        キーが存在しない場合はMessageKeyError  
        キー自体は削除されない。  
        削除された値は「消費済み」として扱われる。  
        typがkeyの要求する型と同一でなければMessageTypeError  
        値が消費済みである場合はMessageConsumedError  
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


class Session(_HasSessionIdentity, _HasLogger, _HasLogging, _HasFrameCoordinating, Protocol):
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
    
class RootFrameSession(Session, Protocol):
    def _for_root(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...
    @property
    def request(self) -> MessageManager:
        """フレームに対する要求・指示  
        ルートフレームがParallelRootFrameの場合、このメッセージに対する値はピッケル化
        可能でなくてはならない
        """
        ...

    @property
    def common(self) -> MessageDefiner:
        """フレーム間の共有状態  
        メッセージの定義と読み取りを行う。
        """
        ...

class SubFrameSession(_HasFrameCoordinating, Protocol):
    """サブフレーム群の部分的な同期を制御するためのセッション
    Messageの読み書きにはContextを使用する。
    """
    def _for_subframe(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class Frame(Protocol):
    pass

class RootFrame(Frame, _HasFrameIdentity, _HasLogger, Protocol):
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

    def as_handler_capable(self,) -> ConcurrentRootFrame:
        """引数をConcurrentRootFrameにキャストして返す  
        rootframeがConcurrentRootFrameはない、またはハンドラを明示的に拒絶している場合
        NoHandlerCapableError
        """
        ...

class ConcurrentRootFrame(RootFrame, _HasHandlerSetting, Protocol):
    def _for_concurrent(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ParallelRootFrame(RootFrame, Protocol):
    def _for_parallel(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...


class SubFrame(Frame, _HasFrameIdentity, _HasLogger, Protocol):
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

