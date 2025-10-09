"""
---------------------------------------------------------------------------------------
gpframe: 並行・並列処理向け汎用フレームワーク
---------------------------------------------------------------------------------------

【このフレームワークの目的と特徴】
目的:
    同期/非同期/サブプロセスの実行方式の選択の簡略化と相互通信

特徴:
    1. 実行中のタスクとの双方向通信
    - 実行に対する基礎状態の取得(environment)
    - Session -> Frame への指示送信（request）
    - Frame -> Session への状態報告（common, ipc）
    - Frame <-> Frame 間での相互通信(common, ipc)
    - 単一フレーム内での通信(local)
    - スレッドセーフな状態管理

    2. 柔軟なライフサイクル管理（オプション）
    - on_open, on_close でFrame全体のリソースの管理
    - on_start, on_end でRoutine用のリソースの管理
    - on_redo でRoutineのリトライロジック
    - on_exceptionで制御用例外のハンドリング

    3. 複数の例外に対する統一的な処理手順
    - ReraisedError で例外の出所を明確化
    - consume() で処理済みをマーク

    注意: 非デーモンスレッドの実行には対応していません。

    
用語:
    - ルーティン
        開発者が実装する処理の本体。このフレームワークは概念的にこのルーティンをフレームで
        ラップして実行する。
        ルーティンは同期/非同期/サブプロセスの3形態の実行形式を選択することができる。
    - ハンドラ
        開発者が実装するフレーム内のイベントのフックポイントの処理。
    - フレーム
        ルーティンを元にした実行内容のビルダー、ハンドラや実行に必要な情報の注入を行う。
        またはライフサイクルを含む実行単位（スレッド）を指す。
        フレーム構成は木構造であり、一つのルートフレームを根として、任意の数のサブフレームが
        枝葉となる。ただし、IPCサブフレームは必ず葉となる（サブフレームを持ていない）。
        また、IPCルートフレームもサブフレームを持つことはできない。
    - セッション
        実行中のフレームに対して監視、指示、待ち合わせを行うインターフェース。
    - コンテキスト
        ルーティン及びハンドラに引数として渡されるインターフェース。
        主に、メッセージによる相互通信の手段を提供する。
    - メッセージ
        セッション、コンテキストからアクセスし、フレーム内、フレーム間、
        サブプロセス間の相互通信を行うためのコンテナインターフェース。


===========================================================
フレームの実行形態
===========================================================

【基本構造】
-----------------------------------------------------------
各フレーム（ルート／サブ）は独立したスレッド上で実行される。

  [メインスレッド]
       │
       ├─▶ [フレームスレッド]
       │       └─ サーキット（非同期関数）
       │              ├─ 各ハンドラの実行
       │              └─ ルーティンの実行

-----------------------------------------------------------

【サーキット】
- フレームスレッド内で常に非同期関数（async）として動作する。
- フレームのライフサイクル制御（on_open → on_start → routine → ...）を担う。

【ハンドラ】
- on_open / on_start / on_end / on_close などのイベントハンドラ。
- 同期・非同期どちらでも定義可能。
- 実行時には すべて非同期関数としてラップ され、サーキット内で await される。

【ルーティン】
- フレームのメイン処理部分。
- 以下のいずれかの形態に対応します：
    1. 同期関数（スレッド内で同期的に実行）
    2. 非同期関数（await により非同期実行）
    3. サブプロセス（IPCフレームなどで独立プロセスとして実行）

===========================================================
フレームの例外のハンドリング
===========================================================
フレームが送出した例外は消費済みか未消費かに分類される

未消費例外を残したままフレームを終了(withブロックを抜ける）した場合、警告が発生する。
この警告はsession.supress_unconsumed_error()を呼ぶことで抑制することができる。

消費済み例外の定義
    - session.reraise(unwrap = True)の形で再スローを行った場合。
    - session.reraise()の形で再スローを行った場合に、捕捉したReraisedErrorの
      session.consume()を呼びだした場合。
    - session.drain(consume = True)から取得された場合。

例外が消費済みであるか否かは、そのあとに続くsession.reraise()やsession.drain()などの
挙動に影響を与える。いったん消費済みとなった場合、これらのメソッドからその例外が
再スローまたは取り出されることはない。session.faulted()の評価の対象からも外れる。

また、session.reraise()は一度再スローした例外が消費済みにされなかったとしても、同じ例外
を再スローすることはない。これにより、繰り返し処理のでの重複した例外ハンドリングが防止される。


未消費例外を残さないための実装方法
    with frame.start() as session:
        ...
        session.wait_done_and_raise()

    または

    with frame.start() as session:
        ...
        while session.running():
            ...
            time.sleep(1)
        
        if session.faulted():
            raise FrameError(session)

            
未消費例外に対する警告を抑制するfail-silentな実装
    with frame.start() as session:
        session.wait_done()
        session.suppres_unconsumed_error()


タイムアウト後の未消費例外に対する警告を抑制する実装
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
                session.supress_unconsumed_error()
            else:
                # タイムアウトしたが、P1からP2までの間に、フレームが終了した可能性がある
                # 残っている未消費例外を取り出して消費済みする
                error = session.drain()
                if error:
                    ... # エラー処理


    フレームの停止と例外ハンドリングの限界
    完全な例外のハンドリングは完全なフレームの停止が前提になる。しかし、session.stop()は
    確実なフレームの停止を保証しない。このため、すべての例外を確実に捕捉するということは
    実質的に不可能である。


===========================================================
フレームのライフサイクル
===========================================================

処理の本質はルーティンであり、それを取り巻くライフサイクルと各ハンドラ
はこのフレームワークを使用する際に必須のものではない。
すべてはオプショナルであり、必要に応じて目的のハンドラを設定して使用すること。

【正常系の流れ】
-----------------------------------------------------------
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
-----------------------------------------------------------
  ...
    ↓
  on_exception（例外ハンドラ）
      ├─ True を返す → 例外を抑制し、正常系として継続
      └─ False を返す → 例外を再スロー
    ↓
  on_close（shielded）



===========================================================
利用例
===========================================================

【最小構成の例】
-----------------------------------------------------------
ルートフレームのみハンドラなしの最小サンプル。

    from gpframe import create_frame, Context

    def routine(ctx: Context):
        print(f"Hello gpframe! from {ctx.frame_name}.")

    root = create_frame("rootframe", routine)

    with root.start() as session:
        session.wait_done_and_raise()


【サブフレームを伴う例（例外ハンドリング付き）】
-----------------------------------------------------------
複数サブフレームを並行実行する

    import time
    from gpframe import create_frame, Context

    def sub1(ctx: Context):
        # 短時間で終了するサブフレーム
        for i in range(3):
            ctx.common.update("progress_sub1", i + 1)
            time.sleep(1)

    def sub2(ctx: Context):
        # 少し長く動作するサブフレーム
        for i in range(5):
            ctx.common.update("progress_sub2", i + 1)
            time.sleep(1)

    def routine(ctx: Context):
        # ルートフレームのルーチン
        s1 = ctx.create_subframe("sub1", sub1)
        s2 = ctx.create_subframe("sub2", sub2)

        with ctx.start_subframes(s1, s2) as session:
            while session.running():
                p1 = ctx.common.getd("progress_sub1", int, 0)
                p2 = ctx.common.getd("progress_sub2", int, 0)
                print(f"[{ctx.frame_name}] progress: sub1={p1}/3, sub2={p2}/5")
                time.sleep(1)
        
            session.wait_done(10)
            if session.running():
                raise FrameTimeoutError(session) # 内部でsession.drain(consume = True)が呼ばれる
            elif session.faulted():
                raise FrameError(session) # 内部でsession.drain(consume = True)が呼ばれる
        
    # フレーム生成
    root = create_frame("root", routine)

    # 起動と待機
    with root.start() as session:
        session.wait_done_and_raise()

【特定フレームのみ例外を監視し、監視対象以外は再スロー】
-----------------------------------------------------------
ループ内では指定したサブフレーム（ここではsubframe1）の例外だけを処理し、
その他の例外はブロック終了後に FrameError でまとめて再スローする。

    import time
    from gpframe import create_frame, Context, ReraisedError

    class ExpectedError(Exception):
        pass

    def sub1(ctx: Context):
        time.sleep(2)
        raise ExpectedError("expected error from sub1")

    def sub2(ctx: Context):
        time.sleep(4)
        raise RuntimeError("unexpected error from sub2")

    def routine(ctx: Context):
        # 2つのサブフレームを起動
        s1 = ctx.create_subframe("subframe1", sub1)
        s2 = ctx.create_subframe("subframe2", sub2)

        with ctx.start_subframes(s1, s2) as session:
            while session.running():
                try:
                    session.reraise()  # unwrap=False: ReraisedError でラップされる
                except ReraisedError as e:
                    if e.frame_name == "subframe1" and isinstance(e.cause, ExpectedError):
                        print(f"✅ handled expected error from {e.frame_name}: {e.cause}")
                        e.consume()  # 消費済みにする。
                    else:
                        # .consume() を呼ばなければ未消費例外のまま。
                        pass
                time.sleep(1)

            # .faulted()は未消費例外が存在するとTrueを返す
            if session.faulted():
                raise FrameError(session) # session.drain(consume = True)が呼ばれる


    # ルートフレームの生成
    root = create_frame("mainframe", routine)

    # 実行と監視
    with root.start() as session:
        session.wait_done_and_raise()


【IPCルートフレームの利用例】
-----------------------------------------------------------
通常の create_frame ではなく、プロセス間通信（IPC）専用の
create_ipc_frame を使ってルートフレームを作成する。

IPC の要点
- サブフレームは持てない
- すべてのメッセージは pickle 化可能である必要がある
- Routine / Handler どちらにも IPCContext が渡される

    import time
    from gpframe import create_ipc_frame, IPCContext

    def ipc_routine(ctx: IPCContext):
        # サブプロセス側：進捗値を ipc に書き込んでいく
        for i in range(5):
            ctx.ipc.update("progress", i + 1)
            print(f"[{ctx.frame_name}] progress: {i + 1}/5")
            time.sleep(1)

        ctx.ipc.update("status", "done")

    # IPCフレームの生成
    root = create_ipc_frame("ipcframe", ipc_routine)

    # --- ホスト側 ---
    with root.start() as session:
        print("[host] started IPC frame")

        while session.running():
            try:
                session.reraise()
                
                progress = session.ipc().geta("progress", 0)
                print(f"[host] current progress: {progress}/5")
                
                time.sleep(1)
            
            except ReraisedError:
                # 消費せずに処理を抜ける
                break

        session.wait_done_and_raise()

【補足】
-----------------------------------------------------------
- サブフレームよりも先にルートフレームが終了することは想定されている。
  RootSessionFrame.wait_done()を使用するとすべてのフレームの終了を待機できる。
"""

"""
---------------------------------------------------------------------------------------
gpframe: 並行・並列処理向け汎用フレームワーク
---------------------------------------------------------------------------------------

このフレームワークは並行処理、並列処理における実行形態の構築のサポート、同期的な通信手段の提供、
および例外処理のサポートを行う。

用語:
    Frame: このフレームワークの処理単位。
    Routine: 処理の本体。ユーザーの実装。
    Handler: イベントに対応するフックポイントの処理。ユーザーの実装。
    Message: フレーム間または、フレーム外部からのフレームへの通信用インターフェース。

=======================================================================================
並行主体・並列主体の分類
=======================================================================================

ルートフレームの種類によって実行の主体が並行か並列かが決定する。
    concurrent_root = create_frame("concurrent_frame", ...)
    parallel_root = create_parallel("parallel_frame", ...)

根本的な分類であり、それ以降のフレームの定義が次のように異なる。

並行ルートフレーム:
    - 各フレーム内部でライフサイクルが管理され、フックポイントにイベントハンドラを適用できる。
    - サブフレームをサブプロセスで動作する場合、次の制限がある。
        1. サブプロセスで実行されるのはルーティンのみ。
        2. サブフレームはサブフレームを持つことができない。(常に葉となる)
    - メッセージは非IPC用のチャンネルとIPC用のチャンネルの2系統が使用できる。

並列ルートフレーム：
    - 各フレームはルーティンのみをサブプロセスで実行し、ライフサイクルおよびイベントハンドラは  
      存在しない。
    - サブフレームもすべて独立したサブプロセスで動作する。
    - メッセージはIPC用のチャンネルのみが使用できる。

=======================================================================================
並行動作時の基本
=======================================================================================

基本的な仕組み:
    FrameでRoutineとHandlerをラップして処理単位を構成する。
    Frameは非IPCとIPCに分かれており、IPCでの動作には制約がある。
    Frame外部から、またはフレーム内のRoutine,Handler間でのメッセージによる通信ができる。
    Frameはルートとサブに分かれていて、フレーム間でもメッセージによる通信ができる。
    
相互通信と役割:
    Frameの外部ではフレームに対してリクエストメッセージを使って指示を送る。
    また、外部では各フレームが送出した例外のハンドリングを行う。
    Frameの内部からはメッセージを通して外部に対して報告を行う。

    以下は処理内容を簡略化した生産・消費の実装サンプル
    ```
    def producer(ctx: Context):
        interval = ctx.common.get_or("producer-interval", float, default=0.5)
        
        while ctx.request.get_or("continue", bool, default=False):
            # 生成したデータ数をカウント
            ctx.common.apply("produced", int, lambda v: v + 1, default=0)
            time.sleep(interval)

    def consumer(ctx: Context):
        interval = ctx.common.get_or("consumer-interval", float, default=1.0)
        
        while ctx.request.get_or("continue", bool, default=False):
            produced = ctx.common.get_or("produced", int, default=0)
            consumed = ctx.common.get_or("consumed", int, default=0)
            
            # 生成されたデータがあれば消費
            if produced > consumed:
                ctx.common.apply("consumed", int, lambda v: v + 1, default=0)
            
            time.sleep(interval)

    def main(ctx: Context):
        ctx.common.update("produced", 0)
        ctx.common.update("consumed", 0)
        ctx.common.update("producer-interval", 0.5)
        ctx.common.update("consumer-interval", 1.0)
        
        # 生成速度 > 消費速度 の非対称な関係
        ctx.create_subframe("producer", producer).start()
        ctx.create_subframe("consumer", consumer).start()
        
    root = create_frame("rootframe", main)
    root.set_environments({
        "session-timeout": 15.0,
        "cleanup-timeout": 5.0,
    })
    root.set_requests({
        "continue": True
    })

    with root.start() as root_session:
        session_timeout = root_session.environment.get_or(
            "session-timeout", float, default = 15.0)
        cleanup_timeout = root_session.environment.get_or(
            "cleanup-timeout", float, default = 5.0)

        time.sleep(session_timeout)
        root_session.request.update("continue", False)
        
        root_session.wait_done(cleanup_timeout)
        if root_session.running():
            root_session.abandon_unchecked_error()
            raise RuntimeError("Rootframe was not finished")
        errors = root_session.drain()
        if errors:
            raise FrameError(errors)
    
    ```
    
IPCでの制限:
    別プロセスで動くのはフレームのうちルーティンのみ。
    ただしフレーム内のメッセージはすべてピッケル化可能なオブジェクトに限定されている。
    フレーム自体はピッケル化できない。
    IPCフレームはサブフレームを持てない。(サブフレームは持てないが、ルーティン内部で
    新しいルートフレームを作成することはできる)

その他:
    イベントハンドラ全てオプショナルで必要がなければ使用しなくていい。
    サブフレームの生成・終了を繰り返す実装に向けたリソースの開放手段の提供している


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
フレームのライフサイクル
=======================================================================================

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

"""

"""
---------------------------------------------------------------------------------------
gpframe: 並行・並列処理向け汎用フレームワーク
---------------------------------------------------------------------------------------

このフレームワークは並行処理、並列処理における実行形態の構築のサポート、同期的な通信手段の提供、
および例外処理のサポートを行う。

用語:
    Frame: このフレームワークの処理単位。
    Routine: 処理の本体。ユーザーの実装。
    Handler: イベントに対応するフックポイントの処理。ユーザーの実装。
    Message: フレーム間または、フレーム外部からのフレームへの通信用インターフェース。

RoutineおよびHandlerは同期/非同期のどちらの関数にも対応している。

=======================================================================================
並行主体・並列主体の分類
=======================================================================================

ルートフレームの種類によって実行の主体が並行か並列かが決定する。
    concurrent_root = create_frame("concurrent_frame", ...)
    parallel_root = create_parallel("parallel_frame", ...)

根本的な分類であり、それ以降のフレームの定義が次のように異なる。

並行ルートフレーム:
    - 各フレーム内部でライフサイクルが管理され、フックポイントにイベントハンドラを適用できる。
    - サブフレームをサブプロセスで動作する場合、次の制限がある。
        1. サブプロセスで実行されるのはルーティンのみ。
        2. サブフレームはサブフレームを持つことができない。(常に葉となる)
    - メッセージは非IPC用のチャンネルとIPC用のチャンネルの2系統が使用できる。

並列ルートフレーム：
    - 各フレームはルーティンのみをサブプロセスで実行し、ライフサイクルおよびイベントハンドラは  
      存在しない。
    - サブフレームもすべて独立したサブプロセスで動作する。
    - メッセージはIPC用のチャンネルのみが使用できる。

    
各プロトコルのプレフィクスによる並行・並列の分類:
    なし: 並行処理用プロトコル
    IPC: 並行処理中の部分的並列処理用プロトコル
    P: 並列処理用プロトコル

Messageに関してはIPCとPに区別はなく、両方ともIPCのプレフィクスがついている。

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
並行処理用フレームのライフサイクル
=======================================================================================

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

"""
from __future__ import annotations

import logging

from typing import Protocol, Any, Awaitable, Callable, Union, ContextManager

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

    def abandon_unchecked_error(self, log: bool = True) -> None:
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

# class _HasIPCHandlerSetting(Protocol):
#     def set_on_exception(self, handler: IPCExceptionHandler) -> None:
#         ...
#     def set_on_redo(self, handler: IPCRedoHandler) -> None:
#         ...
#     def set_on_open(self, handler: IPCEventHandler) -> None:
#         ...
#     def set_on_start(self, handler: IPCEventHandler) -> None:
#         ...
#     def set_on_end(self, handler: IPCEventHandler) -> None:
#         ...
#     def set_on_close(self, handler: IPCEventHandler) -> None:
#         ...

# =====================================================================================
# >>  MESSAGE COMMUNICATION LAYER  <<
#      Thread-safe inter-frame messaging interface for shared state and coordination.
# =====================================================================================

class MessageReader(Protocol):
    def get_any(self, key: str, default: Any = _NO_DEFAULT) -> Any:
        """キーに対応する値を取得する。
        defaultが設定されていない状態でkeyに対応する値が無ければKeyError
        """
        ...
    def get_or(self, key: str, typ: type[_T], default: _D) -> _T | _D:
        """キーに対応する値をデフォルト値を伴って取得する。  
        keyに対応する値がある場合、typによる型チェックを行った後値を返す。  
        型チェックが通らない場合、TypeErrorを送出。  
        対応する値が存在せず、default値を返す場合、型チェックは行われない。
        """
        ...
    def get(self, key: str, typ: type[_T]) -> _T:
        """キーに対応する値を取得する
        キーに対応する値がない場合、KeyErrorを送出。値がtyp型と互換性が無ければTypeError
        """
        ...
    def string(
        self,
        key: str,
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
        key: str,
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
        key: str,
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
        key: str,
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
    def update(self, key: str, value: _T) -> _T:
        """キーに対して値を設定する
        更新後の値を返す。
        更新前の値と更新しようとしている値に型互換性が無ければTypeError
        更新前の値が存在していない場合は型チェックは行われない。
        """
        ...
    
    def swap(self, key: str, value: _T, default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
        """キーに対して値を設定する
        更新前の値を返す。
        キーに対する値が存在せず、defaultも設定されていない場合KeyError
        defaultが使用された場合、それが更新後の値として設定される。また、
        更新前の値としても使用され、それが返る。
        更新前の値と更新しようとしている値に型互換性が無ければTypeError
        更新前の値が存在していない場合は型チェックは行われない。
        """
        ...

    def apply(self, key: str, typ: type[_T], fn: Callable[[_T], _T], default: _T | type[_NO_DEFAULT] = _NO_DEFAULT) -> _T:
        """キーに対応する値の読み取りと更新を同時に行う
        更新後の値を返す。
        keyに対応する値が存在せず、defaultが設定されていない場合KeyError。
        defaultがtypと型に互換性のない場合TypeError。
        defaultにはfnは適用されない。
        キーに対応する値が存在する場合、typと型に互換性がない場合TypeError。
        fnがtypと型に互換性がない値を返した場合TypeError。
        """
        ...
    def remove(self, key: str, default: Any = None) -> Any:
        """キーに対応した値を削除し、返す
        キーに対応する値が存在しない場合でも例外を送出せず、default値を返す。
        """
        ...

class IPCMessageReader(MessageReader, Protocol):
    """このメッセージの値はpickel化可能でなくてはならない"""
    def _for_ipc(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class IPCMessageUpdater(MessageUpdater, Protocol):
    """このメッセージの値はpickel化可能でなくてはならない"""
    def _for_ipc(self) -> None:
            """プロトコル分類用ダミーメソッド"""
            ...

# =====================================================================================
# >>  CONCURRENT EXECUTION REALM  <<
#      Cooperative multi-frame orchestration — mostly in-process,
#      yet capable of spawning parallel subprocess leaves.
# =====================================================================================

class Context(_HasFrameIdentity, _HasLogging, Protocol):
    @property
    def environment(self) -> MessageReader:
        ...
    
    @property
    def request(self) -> MessageReader:
        ...

    @property
    def local(self) -> MessageUpdater:
        ...
    
    @property
    def common(self) -> MessageUpdater:
        ...

    def create_subframe(self, frame_name: str, routine: Routine) -> SubFrame:
        """フレームにサブフレームを追加する
        frame_nameがすでにこのフレームに存在する場合ValueError
        """
        ...
    
    def start_subframes(
            self, *subframes: SubFrame
        ) -> ContextManager[SubFrameCoordinator]:
        """複数のサブフレームをスタートし、コーディネーターを返す
        サブフレームはself.create_subframe()またはself.create_ipc_subframe()で
        作成されたサブフレームでなければならない。他のContextによって作成された
        サブフレームを指定した場合TypeError
        subframesが空ならValueError
        """
        ...

# class Context(_HasFrameIdentity, _HasLogging, Protocol):
#     @property
#     def environment(self) -> MessageReader:
#         ...
#     @property
#     def request(self) -> MessageReader:
#         ...

#     @property
#     def ipc_environment(self) -> IPCMessageReader:
#         ...
    
#     @property
#     def ipc_request(self) -> IPCMessageReader:
#         ...

#     @property
#     def local(self) -> MessageUpdater:
#         ...
    
#     @property
#     def common(self) -> MessageUpdater:
#         ...

#     @property
#     def ipc(self) -> IPCMessageUpdater:
#         ...
    
#     def create_subframe(self, frame_name: str, routine: Routine) -> SubFrame:
#         """フレームにサブフレームを追加する
#         frame_nameがすでにこのフレームに存在する場合ValueError
#         """
#         ...
    
#     def create_ipc_subframe(self, frame_name: str, routine: IPCRoutine) -> IPCSubFrame:
#         """フレームにIPCサブフレームを追加する
#         frame_nameがすでにこのフレームに存在する場合ValueError
#         """
#         ...
    
#     def start_subframes(
#             self, *subframes: SubFrame | IPCSubFrame
#         ) -> ContextManager[SubFrameCoordinator]:
#         """複数のサブフレームをスタートし、コーディネーターを返す
#         サブフレームはself.create_subframe()またはself.create_ipc_subframe()で
#         作成されたサブフレームでなければならない。他のContextによって作成された
#         サブフレームを指定した場合TypeError
#         subframesが空ならValueError
#         """
#         ...



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


class FrameSessionBase(_HasSessionIdentity, _HasLogger, _HasLogging, _HasFrameCoordinating, Protocol):

    @property
    def environment(self) -> MessageReader:
        ...

    @property
    def common(self) -> MessageReader:
        ...
    
    def set_session_name(self, name: str) -> None:
        """このセッションの名前を設定する"""
        ...
    
    def offer_frame_stop(self, force: bool = False) -> None:
        """フレーム、サブフレームの停止を試みる
        強制的な停止はサポートされない。協調的な停止を促す。
        """
        ...
    
class RootFrameSession(FrameSessionBase, Protocol):
    def _for_root(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...
    @property
    def request(self) -> MessageUpdater:
        ...

    @property
    def ipc(self) -> IPCMessageReader:
        ...

class SubFrameSession(FrameSessionBase, Protocol):
    def _for_sub(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...
    @property
    def request(self) -> MessageReader:
        ...

    @property
    def ipc(self) -> IPCMessageUpdater:
        ...

class SubFrameCoordinator(_HasFrameCoordinating, Protocol):
    """サブフレーム群の部分的な同期を制御するためのコーディネーター"""
    def _for_subframe(self) -> None:
        """プロトコル分類用ダミーメソッド"""
        ...

class RootFrame(_HasFrameIdentity, _HasLogger, _HasHandlerSetting, Protocol):
    
    def set_environments(self, environments: dict[str, Any]) -> None:
        """環境変数の初期値を設定する"""
        ...
    def set_requests(self, requests: dict[str, Any]) -> None:
        """リクエストの初期値を設定する"""
        ...
    # def set_picklable_environments(self, environments: dict[str, Any]) -> None:
    #     """IPCフレーム向けの環境変数の初期値を設定する
    #     environmentsの値はpicklableでなければならない
    #     """
    #     ...
    # def set_picklable_requests(self, requests: dict[str, Any]) -> None:
    #     """IPCフレーム向けのリクエストの初期値を設定する
    #     requestsの値はpicklableでなければならない
    #     """
    #     ...

    def start(self) -> ContextManager[RootFrameSession]:
        """このフレームを開始する
        フレームのセッションはコンテキストマネージャーを通して取得する。
        """
        ...


class SubFrame(_HasFrameIdentity, _HasLogger, _HasHandlerSetting, Protocol):

    def start(self) -> ContextManager[SubFrameSession]:
        """このフレームを開始する
        フレームのセッションはコンテキストマネージャーを通して取得する。
        """
        ...

class ParallelRootFrame(_HasFrameIdentity, _HasLogger, Protocol):
    
    def set_environments(self, environments: dict[str, Any]) -> None:
        """IPCフレーム向けの環境変数の初期値を設定する
        environmentsの値はpicklableでなければならない
        """
        ...
    def set_requests(self, requests: dict[str, Any]) -> None:
        """IPCフレーム向けのリクエストの初期値を設定する
        requestsの値はpicklableでなければならない
        """
        ...

    def start(self) -> ContextManager[RootFrameSession]:
        """このフレームを開始する
        フレームのセッションはコンテキストマネージャーを通して取得する。
        """
        ...

# class IPCContext(_HasFrameIdentity, _HasLogging, Protocol):
#     @property
#     def ipc_environment(self) -> IPCMessageReader:
#         ...
    
#     @property
#     def ipc_request(self) -> IPCMessageReader:
#         ...

#     @property
#     def ipc(self) -> IPCMessageUpdater:
#         ...

# IPCRoutine = Callable[[IPCContext], Any] | Callable[[IPCContext], Awaitable[Any]]

# IPCEventHandler = Union[
#     Callable[[IPCContext], None],
#     Callable[[IPCContext], Awaitable[None]],
# ]

# IPCExceptionHandler = Union[
#     Callable[[IPCContext, BaseException], bool],
#     Callable[[IPCContext, BaseException], Awaitable[bool]]
# ]

# IPCRedoHandler = Union[
#     Callable[[IPCContext,], bool],
#     Callable[[IPCContext,], Awaitable[bool]],
# ]

# class IPCFrameSessionBase(_HasFrameIdentity, _HasLogger, _HasLogging, _HasFrameCoordinating, Protocol):
#     def set_session_name(self, name: str) -> None:
#         """このセッションの名前を設定する"""
#         ...

#     def offer_frame_stop(self, force: bool = False) -> None:
#         """このフレームの停止を試みる。
#         forceがTrueならプロセス（Routine）の.kill()を呼ぶ、そうでなければ.terminate()を呼ぶ。
#         """
#         ...

# class IPCSubFrameSession(IPCFrameSessionBase, Protocol):
#     @property
#     def environment(self) -> IPCMessageReader:
#         ...

#     @property
#     def request(self) -> IPCMessageReader:
#         ...

#     @property
#     def ipc(self) -> IPCMessageUpdater:
#         ...

# class IPCSubFrame(_HasFrameIdentity, _HasLogger, _HasIPCHandlerSetting, Protocol):

#     def start(self) -> ContextManager[IPCSubFrameSession]:
#         """このフレームを開始する
#         フレームのセッションはコンテキストマネージャーを通して取得する。
#         """
#         ...

# =====================================================================================
# >>  PARALLEL EXECUTION REALM  <<
#      Distributed multi-frame orchestration — fully multi-process,
#      each frame running as an independent execution unit.
# =====================================================================================

# class PContext(_HasFrameIdentity, _HasLogging, Protocol):
#     @property
#     def environment(self) -> IPCMessageReader:
#         ...
    
#     @property
#     def request(self) -> IPCMessageReader:
#         ...

#     @property
#     def ipc(self) -> IPCMessageUpdater:
#         ...

#     def create_subframe(self, frame_name: str, routine: Routine) -> PSubFrame:
#         """フレームにサブフレームを追加する
#         frame_nameがすでにこのフレームに存在する場合ValueError
#         """
#         ...


# PRoutine = Callable[[PContext], Any] | Callable[[PContext], Awaitable[Any]]

# class PRootFrame(_HasFrameIdentity, _HasLogger):

#     def set_picklable_environments(self, environments: dict[str, Any]) -> None:
#         """IPCフレーム向けの環境変数の初期値を設定する
#         environmentsの値はpicklableでなければならない
#         """
#         ...
#     def set_picklable_requests(self, requests: dict[str, Any]) -> None:
#         """IPCフレーム向けのリクエストの初期値を設定する
#         requestsの値はpicklableでなければならない
#         """
#         ...
    
#     def start(self) -> ContextManager[PRootFrameSession]:
#         """このフレームを開始する
#         フレームのセッションはコンテキストマネージャーを通して取得する。
#         """
#         ...

# class PSubFrame(_HasFrameIdentity, _HasLogger):
    
#     def start(self) -> ContextManager[PSubFrameSession]:
#         """このフレームを開始する
#         フレームのセッションはコンテキストマネージャーを通して取得する。
#         """
#         ...
    

# class PFrameSessionBase(_HasSessionIdentity, _HasLogger, _HasLogging, _HasFrameCoordinating, Protocol):
#     @property
#     def environment(self) -> IPCMessageReader:
#         ...
    
#     def set_session_name(self, name: str) -> None:
#         """このセッションの名前を設定する"""
#         ...

#     def offer_frame_stop(self, force: bool = False) -> None:
#         """このフレームの停止を試みる。
#         forceがTrueならプロセス（Routine）の.kill()を呼ぶ、そうでなければ.terminate()を呼ぶ。
#         """
#         ...

#     def start_subframes(
#             self, *subframes: PSubFrame
#         ) -> ContextManager[PSubFrameCoordinator]:
#         """複数のサブフレームをスタートし、コーディネーターを返す
#         サブフレームはself.create_subframe()またはself.create_ipc_subframe()で
#         作成されたサブフレームでなければならない。他のContextによって作成された
#         サブフレームを指定した場合TypeError
#         subframesが空ならValueError
#         """
#         ...

# class PRootFrameSession(PFrameSessionBase, Protocol):
#     @property
#     def request(self) -> IPCMessageUpdater:
#         ...

#     @property
#     def ipc(self) -> IPCMessageReader:
#         ...

#     def _for_parallel(self) -> None:
#         """プロトコル分類用ダミーメソッド"""
#         ...

# class PSubFrameSession(PFrameSessionBase, Protocol):
#     @property
#     def request(self) -> IPCMessageReader:
#         ...

#     @property
#     def ipc(self) -> IPCMessageUpdater:
#         ...
    
#     def _for_parallel_sub(self) -> None:
#         """プロトコル分類用ダミーメソッド"""
#         ...

# class PSubFrameCoordinator(_HasFrameCoordinating, Protocol):
#     """サブフレーム群の部分的な同期を制御するためのコーディネーター"""
#     def _for_parallel_coord(self) -> None:
#         """プロトコル分類用ダミーメソッド"""
#         ...


def create_frame(frame_name: str, routine: Routine) -> RootFrame:
    ...

def create_parallel_frame(frame_name: str, routine: Routine) -> ParallelRootFrame:
    ...

