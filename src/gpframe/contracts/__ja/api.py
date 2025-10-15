"""
---------------------------------------------------------------------------------------
gpframe: 並行・並列処理のための統合制御フレームワーク
---------------------------------------------------------------------------------------

[概要]
このフレームワークは並行処理、並列処理における実行形態の構築のサポート、シームレスな実行形態
の移行、同期的な通信手段の提供、および例外処理のサポートを行う。

[ユースケース]

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

[ドキュメントについて]
このドキュメントはこのフレームワークが提供する並行・並列処理の制御の仕組みや、ユースケース別の
サンプルコードなどを記述している。
各インターフェースの詳細についてはドキュメント後のコード部分(API定義)を参照すること。

[主要な概念とプロトコルの概要]
    概念:
              frame: Routineを軸とした個別の実行単位。
        frame error: Routine,Handlerの例外の発生、または内包するSesisionの未完了。
                     この2つを以てframe errorとする。
       broken frame: frame error が起こったframe
 incomplete session: サブフレームにbroken frameがある場合や、すべてのサブフレームが停止
                     していない場合。Sessionの処理中に例外が発生した場合。

    プロトコル:
            Routine: 処理の本体。ユーザーの実装。
            Handler: イベントに対応するフックポイントの処理。ユーザーの実装。
        FrameBulder: Frameのビルダー。ハンドラの設定を行う（対応している場合）
        
            Context: ユーザーの実装にフレームのメタ情報、メッセージチャンネルを提供する
                     実行環境。
            Message: フレーム間または、フレーム外部からのフレームへの状態共有インターフェース。

        FrameResult: Frameの実行結果。内部で起こった例外や制御の完全性の記録。
            Session: フレーム群の同期とframe errorのハンドリングを行い、
                     共有メッセージを定義・監視する制御層。
        
        _Agent: Routineを新しいスレッドまたはプロセスで実行するためのアジャスター。
        
        - _AgentはAPIに直接出現しないが、フレームワークの構造の説明のために記載されている。
        - RoutineおよびHandlerは同期/非同期のどちらの関数にも対応している。

[目次]
---------------------------------------------------------------------------------------
    DOC 1. 同期と制御の仕組み
        1.1 FrameResultとマーク
        1.2 制御とその責務
        1.3 俯瞰図
        1.4 スレッド実行時（並行処理時）のライフサイクル
    DOC 2. スレッド/プロセスセーフな状態共有メカニズム
        2.1 Messageの仕様
        2.2 Message チャンネル
    DOC 3. サンプルコード
        3.1 Session
            3.1.1 broken frameのポーリングによるチェック(疑似コード)
            3.1.2 broken frameの一括チェック(疑似コード)
  -------------------------------------------------------------------------------------
    API A. Conceptual and Foundational Dependencies
        A.0 Conceptual Dependencies
        A.1 Foundational Protocols
    API B. Explicitly Importable Interfaces
        B.1 Entry Points
        B.2 Execution Context API
        B.3 Exception Hierarchy
    API C. Auto-Completion Definitions
        C.1 User-Defined Implementation Type Aliases
        C.2 Builder Protocols
        C.3 Message Protocols
        C.4 Session Protocols
        C.5 Result Protocols
---------------------------------------------------------------------------------------

=======================================================================================
[DOC 1] 同期と制御の仕組み
=======================================================================================

この章ではこのフレームワークがどのように制御を行うかの概要を説明する。制御とはフレームの
`実行方法`とその`待機`さらに`例外処理`といった根本的な部分を指し、状態共有に関しては、
[DOC 2] スレッド/プロセスセーフな状態共有メカニズム、に記述する。

---------------------------------------------------------------------------------------
[DOC 1.1] FrameResultとマーク
---------------------------------------------------------------------------------------

FrameResultはframeが終了した時、その状態を記録する。この項ではbroken frameについて説明する。

broken frameの場合、そのフレームが最終的に送出した例外、incomplete sessionのどちらか、または
両方が記録されている。

Sessionはこのbroken frameのFrameResultに対して、インターフェースを通して「マーク」を
行うことで、そのハンドリングを行う。

マークの種類とその後の挙動:
       unexpected: 想定外のエラーに対するマーク。RootSession終了後に例外が発生する。
          ignored: 想定され、かつ上位レイヤーの整合性が保たれる(継続可能)な場合のマーク。
                   RootSession終了時には何も起こらない
          no mark: マークがない場合、RootSession終了後に警告が発生する。

ignoredはそのbroken frameを明示的に無視することができる。これは部分的、全体的に fail-silent 
な設計が可能であることを示す。

---------------------------------------------------------------------------------------
[DOC 1.2] 制御とその責務
---------------------------------------------------------------------------------------

概念上の実行単位はframeだが、実際にその制御はSessionを通して行う。
Sessionは一つ、または複数のframeを制御する。

次の事柄が起こった場合、それらは未チェックのincomplete sessionとして記録される。

incomplete sessionになる原因:
    1. 管理下frameのいずれかがSessionの終了時に停止していない。
    2. 管理下frameから発生したすべての例外が解消されていない。
    3. Sessionがその処理中に例外を送出した。

Sessionの責務に関する重要な指摘:
    incomplete sessionができてしまうこと自体は問題ではない。また、incomplete sessionが
    発生しなかったからといって、バグがないということではない。すべては、Routineと
    Handlerの実装に依存する。
    たとえばincomplete sessionを発生させないために無理な例外の握りつぶしや、フレームに対する
    不必要な待ち合わせ時間の延長などを行うべきではない。
    incomplete sessionはそれが起こったことを上位レイヤーへ、また最終的には開発者に通知、
    ハンドリングの機会を提供するためのものであってSessionの実装にincomplete sessionの
    発生を厳格に防ぐことは`Sessionの責務ではない`。
    Sessionの実装は、想定され回復可能なbroken frameのみを解決し、それ以外のものは
    未解決のまま制御を終了するべきである。また、待ち合わせに関しても想定された時間内に停止しない
    場合には制御を終了して、「制御は終わったが、構成フレームが動作したまま」という事実を素直に
    上位レイヤーに伝えるべきである。また、Sessionの実装に不足している部分があり、
    incomplete sessionになった場合も最終的に警告として開発者が認識できる。

    incomplete sessionは問題が起こっている範囲を限定するための概念であり、問題自体を解決する
    ための概念ではない。

---------------------------------------------------------------------------------------
[DOC 1.3] 俯瞰図
---------------------------------------------------------------------------------------

RootSessionかSubSessionには次の違いがある。
    RootSession:
        - 常に一つの実行単位のみを制御する
    SubSession:
        - SubSessionは複数の実行単位を制御する可能性がある。
          (複数のサブフレームの割り当てが可能)

    - Sessionの終了は実行単位の`制御`の終了になる。

注意:
    実行単位は開始した後、その停止は保証されない。
    (例えばRoutine内でデッドロックが発生している場合は終了しない)
    Sessionの終了はその実行単位の`制御`を終了するのであって、実行単位の終了を意味しない。
    つまり、Sessionが終了した後も実行単位は動作を続けている可能性がある。


実行単位は終了するとFrameResultとして内部にストアされ(*1)、上位レイヤーは
session.get_frame_result()を使用してそれを取得する。

*1: すべてのFrameResultはRootFrameと同プロセス、同スレッドにストアされ管理される。
*2: Handlerはスレッドでの実行時のみ設定できる

                ┌─ gpframe ───────────────────────────────────────────┐
                │                                                     │
                │   RootFrame ──────────▶ _Agent ────┐                │
     broken     │       │                            │                │
  FrameResult  end      ▼                            │                │
     found   ◀──┼── RootSession ◀──┐                 │                │
       │        │       ▲          │                 │                │
       │        │       │       session.             │                │
       ▼        │       │── get_frame_result()       │                │
   Exception    │       │                            │                │
      if        │       │                            │                │
    marked      │   :internal                        ▼                │
      as        │   FrameResult Map         ----------------------    │
  unexpected    │       ExceptionRecord     thread or process(:EXE)   │
--------------  │       CoordinationError   -----------------------   │
   Warnning     │       ▲                            │                │
      if        │       │                         (worker)            │
    without     │       │                            │                │
     mark       │       │                            ▼                │
                │       │◀──────┐   ┌─────── Routine / Handler(*2)    │
                │       │       │   │                                 │
                │       │       │   │ create                          │
                │       │   end │   │                                 │
                │       │       │   │                                 │
                │       │       │   ▼      ┌──────────────────────┐   │
                │       │     SubFrame(1) ─┼────▶ _Agent          │   │
                │       │  ┌───────┼───────┘        │             │   │
                │       │  │       ▼                ▼             │   │
                │       │  │   SubSession  --------------------   │   │
                │       │  │       ▲       │       EXE        │   │   │
                │       │  │       │       --------------------   │   │
                │       │  │    session.         (worker)         │   │
                │       │──├── get_frame_           ▼             │   │
                │       │  │    _result()   Routine / Handler(*2) │   │
                │       │  │                        │             │   │
                │       │  │                        │ create      │   │
                │       │◀─├─────────────┐          │             │   │
                │       │  │        end  │          ▼             │   │
                │       │  │       ┌────────────────────────────┐ │   │ # TODO: 別プロセスまたは別スレッドにSubFrame(1-1)があるように見えるので要修正
                │       │  │       │ SubFrame (1-1) ...         │ │   │
                │       │  │       │  SubSession ...            │ │   │
                │       .  │       └────────────────────────────┘ │   │
                │       .  └──────────────────────────────────────┘   │
                │       .                                             │
                └─────────────────────────────────────────────────────┘

---------------------------------------------------------------------------------------
[DOC 1.4] スレッド実行時（並行処理時）のライフサイクル
---------------------------------------------------------------------------------------

並行処理時にはRoutineの前後に各種ハンドラを設定できる。
これらは全てオプショナルであって、必須のものは存在しない。必要な時に必要なものを設定すること。

ライフサイクルは以下の通り。

フレーム内部のライフサイクルの定義
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
【正常系】
  on_open
    ↓
  on_start *
    ↓
  Routine
    ↓
  on_end
    ↓
  on_redo
      ├─ True を返す → *（on_start から再実行）
      └─ False を返す → on_close
    ↓
  on_close（shielded：例外・キャンセルの影響を受けず必ず呼ばれる）
---------------------------------------------------------------------------------------
【例外発生時の流れ】
  ...
    ↓
  on_exception（shielded）
      ├─ True を返す → 例外を抑制し、正常系として継続
      └─ False を返す → 例外を再スロー
    ↓
  on_close（shielded）
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

shielded = asyncio.shield()による呼び出し


=======================================================================================
[DOC 2] スレッド/プロセスセーフな状態共有メカニズム
=======================================================================================

この章ではSessionまたはContextを介して提供されるSession<->Frame間、Frame<->Frame間の
状態共有を行うための仕組みを説明する。
状態共有はMessageというプロトコルに沿って行われ、それぞれ役割持つ複数のチャンネルを
使い分けて行う。

基本的にスレッド、サブプロセスで共通のインターフェースを提供するが、サブプロセスでの実行の
際にはIPCを用いる為、メッセージの値はlocalチャンネル以外、ピクル化可能でなければならない。
なお、この制約を静的型チェックから判別する方法をMessageプロトコル群は提供していない点に注意。

---------------------------------------------------------------------------------------
[DOC 2.1] Messageの仕様
---------------------------------------------------------------------------------------
メッセージはキーと値からなり、次の仕様に従う。
- キーおよび値にNoneを設定することはできない。
- キーは一度作成されると「定義済み」となり、型情報と共に値が削除されても存在し続ける。
- 一度定義済みのキーを再度定義することはできない。
- 値はキーの定義と同時に有効なものを型情報と共に設定する必要がある。
- 値はインターフェースを介して削除することができ、これを「消費済み」と表現する。

---------------------------------------------------------------------------------------
[DOC 2.2] Message チャンネル
---------------------------------------------------------------------------------------
役割別に4つのメッセージチャンネルが存在する。
    - environment:
        不変メッセージチャンネル。RootFrameのスタート前に設定され、更新手段が提供されない。
        各セクションは読み取りのみを行う。
        Session, Frame(via Context) -> MessageReader
    - request:
        Sessionを通して、各フレームへ要求を伝えるためのメッセージチャンネル。
        メッセージはRootSessionで定義と更新を行い、各フレームは読み取りのみを行う。
        RootSession -> MessageManager
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
    並列処理の場合、localを除くMessageの値はすべてIPCを用いるのでピクル化に対応している
    必要がある。この制約はAPIに定義されているプロトコルから判別ができないので注意。


=======================================================================================
[DOC 3] サンプルコード
=======================================================================================

---------------------------------------------------------------------------------------
[DOC 3.1] Session
---------------------------------------------------------------------------------------

----------[DOC 3.1.1] broken frameのポーリングによるエラーチェック(疑似コード)-------------

with root.start() OR ctx.start_subframes() as session:
    while session.running():
        if broken_frame := session.get_broken_frame():
            if incomp_session := broken_frame.get_incomplete_session():
                ...
                if error := incomp_session.get_error():
                    broken_frame.mark_as_unexpected()
            if error := broken_frame.error():
                ...
                if ...:
                    broken_frame.mark_as_unexpected()

            if broken_frame.ignorable():
                broken_frame.mark_as_ignored()
        time.sleep(1)

---------------[DOC 3.1.2] broken frameの一括エラーチェック(疑似コード)--------------------

with root.start() OR ctx.start_subframes() as session:

    # 最初に待ち合わせを行う
    session.wait_done()

    # 後からエラーのあったFrameResultを検証
    # root.start()のsessionの場合はlen(broken_frames) <= 1なので
    # if broken_frame := session.get_broken_frame():... の方がよい。
    if broken_frames := session.get_all_broken_frames():
        for bf in broken_frames:
            if incomp_session := bf.get_incomplete_session():
                ...
                if ...:
                    bf.mark_as_unexpected()
            if error := bf.get_error():
                ...
                if ...:
                    bf.mark_as_unexpected()

            if bf.ignorable():
                bf.mark_as_ignored()
"""
from __future__ import annotations

from enum import Enum
import logging

from typing import Protocol, Any, Awaitable, Callable, Union, ContextManager, cast

from gpframe._impl.common import _T, _noop, _any_str, _any_int, _any_float

# +====================================================================================+
# |  >>> [API A] CONCEPTUAL AND FOUNDATIONAL DEPENDENCIES                              |
# |      Internal conceptual modules and base protocols forming the framework core.    |
# +====================================================================================+

#=======================================================================================
# [API A.0] Conceptual Dependencies
#---------------------------------------------------------------------------------------

import threading # noqa: F401  # for documentation / conceptual dependency
import asyncio # noqa: F401  # for documentation / conceptual dependency
import multiprocessing # noqa: F401  # for documentation / conceptual dependency


#=======================================================================================
# [API A.1] Foundational Protocols
#---------------------------------------------------------------------------------------

FrameName = str
FrameQualname = str

class _HasFrameIdentity(Protocol):
    @property
    def frame_name(self) -> FrameName:
        """このフレームの名前"""
        ...
    @property
    def frame_qualname(self) -> FrameQualname:
        """このフレームの完全修飾名"""
        ...

SessionName = str
SessionQualname = str

class _HasSessionIdentity(Protocol):
    @property
    def session_name(self) -> SessionName:
        """このセッションの名前"""
        ...

    @property
    def session_qualname(self) -> SessionQualname:
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

        logger プロパティは指定されたロガーを返す
        """
        ...

class _HasLogging(Protocol):
    @property
    def logger(self) -> logging.Logger:
        ...

class _HasFrameCoordinating(Protocol):

    def running(self) -> bool:
        """フレームが実行中かどうかを判定する"""
        ...

    def wait_done(self, timeout: float | None = None) -> None:
        """フレームの終了を待ち合わせる  

        timeoutにfloat(sec)が渡され、その時間内にフレームが完了しなかった場合。待機を中断する。  
        """
        ...
    
    def get_finished_frame(self) -> FrameResult:
        """終了したフレームの結果を取得する  
        
        一度返されたフレームの結果はこのメソッドから2度と返らない。
        """
        ...
    
    def get_successful_frame(self) -> FrameResult:
        """正常終了したフレームの結果を取得する  
        
        一度返されたフレームの結果はこのメソッドから2度と返らない。
        """
        ...
    
    def get_broken_frame(self) -> FrameResult:
        """異常終了したフレームの結果を取得する  
        
        一度返されたフレームの結果はこのメソッドから2度と返らない。
        """
        ...
    
    def get_all_finished_frames(self) -> list[FrameResult]:
        """現時点で終了しているフレームの結果をすべて取得する  
        
        複数回呼び出した場合、前回の呼び出しから新たに終了したフレームの結果が  
        追加されている場合がある。
        """
        ...
    
    def get_all_successful_frames(self) -> list[FrameResult]:
        """現時点で正常終了しているフレームの結果をすべて取得する  
        
        複数回呼び出した場合、前回の呼び出しから新たに正常終了したフレームの結果が  
        追加されている場合がある。
        """
        ...
    
    def get_all_broken_frames(self) -> list[FrameResult]:
        """現時点で異常終了しているフレームの結果をすべて取得する  
        
        複数回呼び出した場合、前回の呼び出しから新たに異常終了したフレームの結果が  
        追加されている場合がある。
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

# +====================================================================================+
# |  >>> [API B] EXPLICITLY IMPORTABLE INTERFACES                                      |
# |      Entry points, context interface, and exception hierarchy for gpframe users.   |
# +====================================================================================+

#=======================================================================================
# [API B.1] Entry Points
#---------------------------------------------------------------------------------------

def create_frame(
        routine: Routine,
        *,
        frame_name: str = "",
        subprocess: bool = False,
        handler: bool = True
    ) -> ConcurrentRootFrameBuilder | ParallelRootFrameBuilder:
    """ルートフレームを作成する  

    subprocessがTrueならParallelRootFrame、FalseならConcurrentRootFrameを返す。  
    ParallelRootFrameはハンドラ非対応であり、ConcurrentRootFrameはハンドラ対応する。  
    frame_nameにはこのフレームの名前を指定する。  
    frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
    どちらからも有効な識別子を得ることができなければMissingNameError  
    handlerがFalseの場合、フレームがハンドラ対応にしていてもハンドラの設定を拒絶する。  
    frame.supports_handlers()はFalseを返すようになる。  
    subprocessがTrueの場合、handlerフラグは無視される。
    """
    ...

def create_concurrent_frame(
        routine: Routine,
        *,
        frame_name: str = "",
        handler: bool = True
    ) -> ConcurrentRootFrameBuilder:
    """並行ルートフレームを作成する  

    このルートフレームはハンドラを設定することができる。  
    frame_nameにはこのフレームの名前を指定する。  
    frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
    どちらからも有効な識別子を得ることができなければMissingNameError  
    handlerがFalseの場合、ハンドラの設定を拒絶する。  
    frame.supports_handlers()はFalseを返すようになる。  
    """
    return cast(ConcurrentRootFrameBuilder, create_frame(
        routine, frame_name = frame_name, subprocess = False, handler = handler)
    )

def create_parallel_frame(routine: Routine, frame_name: str = "") -> ParallelRootFrameBuilder:
    """並列ルートフレームを作成する  

    このルートフレームはハンドラを設定することできない。  
    frame_nameにはこのフレームの名前を指定する。  
    frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
    どちらからも有効な識別子を得ることができなければMissingNameError  
    """
    return cast(ParallelRootFrameBuilder, create_frame(
        routine, frame_name = frame_name, subprocess = True, handler = False)
    )


#=======================================================================================
# [API B.2] Execution Context API
#---------------------------------------------------------------------------------------

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

        SessionまたはCoordinatorが更新する。
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
        ルートフレームがParallelRootFrameの場合、このメッセージに対する値はピクル化
        可能でなくてはならない
        """
        ...

    def define_subframe(self, routine: Routine, frame_name: str = "", handler: bool = True) -> SubFrameBuilder:
        """フレームにサブフレームを追加する  

        SubFrameは個別に開始することができない。サブフレームの開始には
        .start_subframes()を使用する。  
        サブフレームの実行を開始した後、このメソッドを呼び出した場合ContextStateError  

        frame_nameがすでにこのフレームに存在する場合ValueError  
        frame_nameにはこのフレームの名前を指定する。  
        frame_nameが空文字列の場合routine.__name__がフレーム名として設定される。  
        どちらからも有効な識別子を得ることができなければMissingNameError  
        handlerがFalseの場合、フレームがハンドラ対応にしていてもハンドラの設定を拒絶する。  
        frame.supports_handlers()はFalseを返すようになる。  
        フレームがハンドラに対応していない場合、handlerフラグは無視される。
        """
        ...
    
    def supports_handlers(self) -> bool:
        """フレームがハンドラに対応しているか判定する"""
        ...
    
    def start_subframes(self) -> ContextManager[SubSession]:
        """コンテキストに設定されている全てのサブフレームをスタートする  
        
        このメソッドは一つのContextにつき、一度しか呼び出すことができない。  
        2回目以降の呼び出しがあった場合ContextStateError
        """
        ...


#=======================================================================================
# [API B.3] Exception Hierarchy
#---------------------------------------------------------------------------------------

class GpFrameBaseError(Exception):
    """フレームワーク由来例外のベースクラス  

    このクラスおよびその派生クラスは、通常フレームワーク内部で生成される。  
    """
    pass

class FrameStateError(GpFrameBaseError):
    """Frameの生成やハンドリングに由来する例外のベースクラス"""
    pass

class MissingNameError(FrameStateError):
    """有効なフレーム名が存在しない場合にスローされる"""
    pass

class FrameStillRunningError(FrameStateError):
    """フレームの動作中に削除を試みた場合にスローされる"""
    pass

class MessageError(GpFrameBaseError):
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

class MessageValueError(MessageError, ValueError):
    """メッセージの値に不整合があった場合にスローされる"""
    pass

class ConsumedError(MessageError):
    """値が存在しない場合にスローされる"""
    pass

class IPCError(MessageError):
    """IPCによる通信由来例外のベースクラス"""
    pass

class IPCValueError(IPCError, ValueError):
    """値のピクル化が失敗した場合にスローされる"""
    pass

class IPCConnectionError(IPCError):
    """IPCの通信自体が失敗した場合にスローされる"""
    pass

# +====================================================================================+
# |  >>> [API C] AUTO-COMPLETION PROTOCOLS (USER-VISIBLE, NOT DIRECTLY IMPORTED)       |
# |      Protocol interfaces exposed for IDE completion and static analysis support.   |
# +====================================================================================+

#=======================================================================================
# [API C.1] User-Defined Implementation Type Aliases
#---------------------------------------------------------------------------------------
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


#=======================================================================================
# [API C.2] Builder Protocols
#---------------------------------------------------------------------------------------
class FrameBuilder(Protocol):
    pass

class RootFrameBuilder(FrameBuilder, _HasFrameIdentity, _HasLogger, Protocol):
    def set_environments(self, environments: dict[str, Any]) -> None:
        """環境変数の初期値を設定する"""
        ...
    def set_requests(self, requests: dict[str, Any]) -> None:
        """リクエストの初期値を設定する"""
        ...

    def start(self) -> ContextManager[RootSession]:
        """このフレームを開始する  

        フレームのセッションはコンテキストマネージャーを通して取得する。
        """
        ...

    def supports_handlers(self) -> bool:
        """フレームがハンドラに対応しているか判定する"""
        ...

class ConcurrentRootFrameBuilder(RootFrameBuilder, _HasHandlerSetting, Protocol):
    def _for_concurrent(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ParallelRootFrameBuilder(RootFrameBuilder, Protocol):
    def _for_parallel(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...


class SubFrameBuilder(FrameBuilder, _HasFrameIdentity, _HasLogger, Protocol):
    """サブフレームのベースプロトコル  

    SubFrameはそれ自体を単独で起動することができない。  
    起動にはContext.start_subframes()を使用する。  
    """
    def _for_subframe(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ConcurrentSubFrameBuilder(SubFrameBuilder, _HasHandlerSetting, Protocol):
    def _for_concurrent(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class ParallelSubFrameBuilder(SubFrameBuilder, Protocol):
    def _for_parallel(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

#=======================================================================================
# [API C.3] Message Protocols
#---------------------------------------------------------------------------------------
class Message(Protocol):
    pass

KeyType = Union[str, Enum]

class MessageReader(Message, Protocol):
    """同期化メッセージ読み取り用インターフェース  

    メッセージはIPCで接続されている場合がある。  
    この時IPCの接続に問題があり、読み取りが失敗した場合IPCConnectionError
    """

    def exists(self, key: KeyType) -> bool:
        """キーが存在するか判定する"""
        ...
    
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

        値の取得はself.get(key, str)と同義。  
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

        値の取得はself.get(key, str)と同義。  
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

        値の取得はself.get(key, str)と同義。  
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

        値の取得はself.get(key, str)と同義。  
        prepは文字列に前もって行う処理を指定する。  
        trueとfalseにはそれぞれ、TrueとFalseに解釈する文字列を指定する。  
        どちらも指定しなかった場合bool(string)(:空文字列でなけばTrue)を返す。  
        どちらか一方のみ指定した場合、string in trueまたはstring in falseを返す。  
        いずれかの方法でも変換が行われなかった場合MessageValueError
        """
        ...

class MessageUpdater(MessageReader, Protocol):
    """同期化メッセージ更新用インターフェース  

    メッセージの値がピクル化可能に制限されている場合がある(IPC使用時)。  
    MessageUpdaterはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピクル化に関してエラーが起こった場合IPCValueError  
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
        valueがkeyの要求する型のインスタンスでなければMessageTypeError  
        値が消費済みである場合はMessageConsumedError  
        """
        ...
    
    def batch(self) -> ContextManager[BatchOperator]:
        """不可分操作用のBatchOperatorを取得する  

        ロックを保持したままメッセージに対して複数の処理を行う。  
        withブロック内ではロックを保持しているので、BatchOperatorが提供する
        以外のメソッドを使用してメッセージを操作した場合、デッドロック
        が発生するので注意。
        """
        ...

class MessageDefiner(MessageReader, Protocol):
    """同期化メッセージ定義用インターフェース  

    メッセージの値がピクル化可能に制限されている場合がある(IPC使用時)。  
    MessageDefinerはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピクル化に関してエラーが起こった場合IPCValueError  
    IPCの接続に問題があり、更新できなかった場合IPCConnectionError
    """
    def define(self, key: KeyType, typ: type[_T], value: _T) -> None:
        """キーを定義し型と値を設定する  

        すでに定義済みのキーであった場合RedefineError  
        typにtype(None)を指定した場合MessageTypeError  
        valueがtypのインスタンスでない場合MessageTypeError  
        """
        ...

class MessageManager(MessageUpdater, MessageDefiner, Protocol):
    """同期化メッセージ定義・更新用(フルコントロール)インターフェース  

    メッセージの値がピクル化可能に制限されている場合がある(IPC使用時)。  
    MessageManagerはこの制限に対して静的な型チェックを提供しない。  
    値の更新時にピクル化に関してエラーが起こった場合IPCValueError  
    IPCの接続に問題があり、更新できなかった場合IPCConnectionError
    """
    ...

class BatchOperator(Protocol):
    """メッセージの不可分操作用オペレーター  

    値の読み書きとクエリを提供する。  
    既存キーに対してのみ操作を行うことができる。  
    keyの新規作成を行うことはできない。  
    """
    def exists_key(self, key: KeyType) -> bool:
        """キーが存在するか判定する"""
        ...

    def get_value(self, key: KeyType, typ: type[_T]) -> _T:
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

#=======================================================================================
# [API C.4] Session Protocols
#---------------------------------------------------------------------------------------

class Session(
    _HasSessionIdentity,
    _HasFrameCoordinating,
    _HasLogger,
    _HasLogging,
    Protocol
):
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
    
class RootSession(Session, Protocol):
    def _for_root(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...
    
    @property
    def environment(self) -> MessageReader:
        """環境変数  

        不変の読み取り専用メッセージ
        """
        ...
    @property
    def request(self) -> MessageManager:
        """フレームに対する要求・指示  

        ルートフレームがParallelRootFrameの場合、このメッセージに対する値はピクル化
        可能でなくてはならない
        """
        ...

    @property
    def common(self) -> MessageDefiner:
        """フレーム間の共有状態  

        メッセージの定義と読み取りを行う。
        """
        ...

class SubSession(Session, Protocol):
    """サブフレーム群の部分的な同期を制御するためのセッション  

    Messageの読み書きはContextを使用する。  
    """
    def _for_subframe(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

#=======================================================================================
# [API C.5] Result Protocols
#---------------------------------------------------------------------------------------

class FrameErrorRecord(_HasFrameIdentity):
    def get(self) -> BaseException:
        """Frameが投げた例外を取得する"""
        ...

class SessionResult(Protocol):
    """Sessionの制御結果"""
    
    def completes(self) -> bool:
        """セッションが完全に終了しているか判定する  
        
        制御対象のframeにbroken frameが含まれる場合、制御終了時に動作を停止していないframe
        が存在する場合、セッションの処理中に例外が発生した場合はFalseを返す。
        """
        ...

    def get_frame_errors(self) -> list[FrameErrorRecord]:
        """broken frameの識別子と例外のペアのリストを返す"""
        ...
    
    def get_stuck_running_frames(self) -> list[tuple[FrameName, FrameQualname]]:
        """セッションの終了時に停止していないフレームの識別子のリストを返す  

        フレームはセッションが終了時に停止していないことを表し、このメソッドの呼び出し時点に
        おいて動作中であることは保証されない。
        """
        ...
    
    def get_error(self) -> BaseException | None:
        """セッション自体が送出した例外を取得する"""
        ...

class FrameResult(_HasFrameIdentity, Protocol):
    """Frameの実行結果  

    frameには戻り値の概念がないため、戻り値を得ることはできない。このプロトコルはフレームの  
    実行結果の成否とその原因の提供。または、結果を分類するためのマークインターフェースを提供  
    する。
    """
    def successful(self) -> bool:
        """frameが成功しているかどうかを判定する  

        frameが例外を送出している、ncomplete sessionを含んでいる。これらの場合Falseを返す。
        """
        ...
    
    def ignorable(self) -> bool:
        """実行結果が「想定外」にマークされていないかどうか判定する  
        
        ignorableとはignoredでマークされているかではなく、unexpectedで
        マークされていないかどうかのみで判定する。
        """
        ...
    
    def get_error(self) -> BaseException | None:
        """このフレームが送出した例外を取得する  

        内包するSessionから送出された例外はここに含まれない。
        """
        ...

    def get_session(self) -> SessionResult | None:
        """このフレームが内包するSessionの結果を取得する  

        Sessionを内包していない場合はNoneを返す。
        """
        ...
    
    def get_incomplete_session(self) -> SessionResult | None:
        """このフレームが内包するSessionがincompleteだった場合にSessionResultを返す  

        Sessionを内包していない場合やSessionが完全である場合にはNoneを返す。
        """
        ...

    def mark_as_ignored(self) -> None:
        """このFrameResultに「無視」をマークする  
        
        FrameResultを「無視」にマークするということはこの中に含まれる
        incomplete sessionも同時に「無視」にマークされる。
        frameが失敗していなくてもこの挙動は変わらない。
        """
        ...

    def mark_as_unexpected(self, reason: str = "") -> None:
        """このFrameResultを「想定外」にマークする  
        
        reasonには付加情報を表す文字列を指定する。
        """

