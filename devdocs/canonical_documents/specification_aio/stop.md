<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/specification_aio/__init__.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# Async stop

非同期版の停止の要求とキャンセルの配送、停止の伝わり方、停止コールバックに関する規則。

## ASTOP_001

非同期版の停止は、asyncio のタスクのキャンセルで行う。キャンセルはルーティンの次の待機点(`await`)に `asyncio.CancelledError` として届く。これは同期版の「フラグを立てて、ルーティンに確認してもらう」方式とは異なる、非同期版の停止の方式である。

title: Stop is cancellation

level: INFORMATIVE

## ASTOP_002

`AsyncSession.stop()` は、停止の要求を記録し、そのセッションの実行中のすべてのフレームのタスクをキャンセルし、それらのフレームの中で開かれているサブセッションにも再帰的に停止を要求しなければならない。

title: Stop cancels every frame

level: MUST

## ASTOP_003

gpframe が一つのフレームのタスクをキャンセルするのは、多くても一度である。`stop()` を何度呼んでも、キャンセルを捕まえて後始末をしているルーティンに、重ねてキャンセルを送ってはならない。

title: A frame is cancelled at most once

level: MUST NOT

## ASTOP_004

停止を要求されたセッションのフレームの中で、要求の後に開かれたサブセッションは、開いた時点で停止を要求された状態でなければならない。

title: Sub-sessions opened after a stop

level: MUST

## ASTOP_005

`stop()` はコルーチンではなく、フレームの終了や停止コールバックの完了を待たずに戻る。どのスレッドから呼んでもよい。二度以上呼んでも、一度呼んだ場合と同じ状態になる。停止の要求は取り消せない。

title: Stop is a thread-safe request

level: MUST

related: [ALIMIT_008](limits.md#alimit_008)

## ASTOP_006

`AsyncContext.stopping` は、そのフレームのセッションに停止が要求されていれば `True` を返す。キャンセルを捕まえたルーティンが、それが停止の要求によるものかを確かめるのに使う。

title: Observing the stop request

level: MUST

## ASTOP_007

非同期版には、同期版の `wait_stop()` に当たるものを設けない。停止はキャンセルとしてどの待機点にも届くので、停止だけを待つ必要がないためである。

title: No wait_stop in the async API

level: INFORMATIVE

## ASTOP_008

ルーティンは `asyncio.CancelledError` を握りつぶすべきではない。後始末のために捕まえる場合も、後始末の後で再送出するか、値を返して終わるべきである。捕まえたまま処理を続けると、そのフレームは stuck frame になりうる。

title: Writing cancellable routines

level: SHOULD

related: [AFRAME_004](frame.md#aframe_004), [ALIMIT_003](limits.md#alimit_003)

## ASTOP_009

セッション自身が停止を要求するのは、`async with` ブロック内で例外が起きた場合(所有タスク自身のキャンセルを含む)と、終了時の待機の後に stuck frame が残った場合だけである。

title: Implicit stop requests

level: MUST

related: [ASESSION_010](session.md#asession_010)

## ASTOP_010

`AsyncContext.on_stop(callback)` は、引数を取らない同期の呼び出し可能オブジェクトを、そのフレームの停止コールバックとして登録し、取り消し用の `gpframe.aio.StopHandle` を返す。主な用途は、キャンセルでは止まらない処理(`asyncio.to_thread()` で動かしているブロッキング処理など)の止め方を登録することである。

title: Registering a stop callback

level: INFORMATIVE

related: [ALIMIT_006](limits.md#alimit_006)

## ASTOP_011

コルーチン関数や、呼ぶとコルーチンを返すものは停止コールバックとして登録できない。登録時に `TypeError` を送出する。停止コールバックは同期で短く終わるものに限る。

title: Stop callbacks are synchronous

level: MUST

## ASTOP_012

停止コールバックは、フレームのセッションに停止が要求されたときに、要求の経路を問わず呼ばれなければならない。一つの登録が呼ばれるのは多くても一度である。

title: When stop callbacks run

level: MUST

## ASTOP_013

停止コールバックは、セッションのループのスレッドで、登録した順に呼ばれなければならない。さらに、そのフレームへのキャンセルがルーティンに届くより前に呼ばれる。ルーティンが後始末を始める時点で、止め方の通知が済んでいるようにするためである。

title: Where and when stop callbacks run

level: MUST

## ASTOP_014

停止がすでに要求されているときに登録された停止コールバックは、登録の後、ループが次に動いたときに呼ばれなければならない。この場合、キャンセルはすでにルーティンに届いているので、ASTOP_013 の「キャンセルより前に呼ぶ」という順序は成り立たない。

title: Registering after a stop request

level: MUST

## ASTOP_015

フレームのルーティンが終わった後は、そのフレームのまだ呼ばれていない停止コールバックを呼んではならない。

title: Callbacks end with the routine

level: MUST NOT

## ASTOP_016

`StopHandle.cancel()` を呼んだ後は、その停止コールバックを呼んではならない。取り消した登録はフレームから取り除き、コールバックへの参照を残してはならない。登録と取り消しを長く動くフレームの中で繰り返しても、登録が溜まらないためである。すでに呼ばれた後や、フレームが終了した後の `cancel()` は何もしない。

title: Cancelling a registration

level: MUST

## ASTOP_017

停止コールバックが例外を送出した場合、その例外を `AsyncFrame.stop_errors` に記録し、フレームを broken にしなければならない。そのフレームの残りの停止コールバックと、フレームのキャンセルは、引き続き行う。

title: Errors in stop callbacks

level: MUST

related: [AFRAME_003](frame.md#aframe_003)

## ASTOP_018

停止コールバックはループのスレッドで呼ばれるので、ブロックしてはならない。ブロックすると、ALIMIT_002 によりすべての保証が失われる。

title: Stop callbacks must not block

level: MUST NOT

condition: 停止コールバックを書くとき。

related: [ALIMIT_001](limits.md#alimit_001), [ALIMIT_002](limits.md#alimit_002)

## ASTOP_019

`AsyncSession.stop()` は、セッションの状態によらず、`async with` で開く前でも閉じた後でも呼べなければならない。開く前に呼んだ場合、セッションは開いた時点で停止を要求された状態になり、その中の `spawn()` は stopped のフレームを返す。別のスレッドからルートのセッションを止めるには、同期版の STOP_020 と同じく、先に作ったセッションの参照を渡しておく。

title: Stopping a session in any state

level: MUST

related: [ASESSION_005](session.md#asession_005), [AFRAME_015](frame.md#aframe_015)
