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

# Async frame

非同期のフレームの状態、結果の受け取り、失敗の承認に関する規則。

## AFRAME_001

非同期のフレーム(`AsyncFrame`)は `running` で始まり(AFRAME_015 の stopped のフレームを除く)、一度だけ終了する。終了したフレームは succeeded、stopped、broken のどれか一つであり、終了後に状態が変わってはならない。

| 状態 | 意味 |
| --- | --- |
| succeeded | ルーティンが値を返して終わり、失敗がない |
| stopped | gpframe の停止要求によるキャンセルで終わり、失敗がない。または、停止の後に起動されてルーティンを呼ばずに終わった(AFRAME_015) |
| broken | 失敗があり、承認が必要 |

title: Frame states

level: MUST

## AFRAME_002

フレームのセッションが停止を要求した後に、ルーティンが `asyncio.CancelledError` で終わった場合、そのフレームは stopped である。停止を頼んだ結果として止まったのは正常な結末なので、承認を求めない。

title: Stopped frames

level: MUST

## AFRAME_003

次のどれかに当てはまる終了したフレームは broken である。

- ルーティンが `asyncio.CancelledError` 以外の例外で終わった
- セッションが停止を要求していないのに、ルーティンが `asyncio.CancelledError` で終わった(gpframe が要求していないキャンセル)
- フレームの中で開いたサブセッションが不完全に終わった
- フレームの停止コールバックが例外を送出した

後の二つは、ルーティンが値を返した場合や stopped に当たる終わり方をした場合にも当てはまり、そのフレームを broken にする。

title: Broken frames

level: MUST

## AFRAME_004

ルーティンが `asyncio.CancelledError` を捕まえて値を返した場合、そのフレームは(他に失敗がなければ)succeeded である。

title: Returning after catching cancellation

level: MUST

## AFRAME_005

`await AsyncFrame.result(timeout)` は、フレームが終了するまで最大 `timeout` 秒待ち、終了した状態に応じて次のようにしなければならない。時間内に終了しなければ `TimeoutError` を送出する。

- ルーティンが値を返していれば、その値を返す(broken であっても)。
- stopped なら `FrameStoppedError` を送出する。
- ルーティンが例外で終わっていれば、その例外を送出する。ただしその例外が `asyncio.CancelledError` の場合は、それを `__cause__` に持つ `FrameAbortedError` を送出する。

title: Waiting for the result

level: MUST

## AFRAME_006

`result()` が、フレームの `asyncio.CancelledError` を呼び出し側にそのまま送出してはならない。呼び出し側のタスクが自分自身のキャンセルと取り違えるためである。

title: Cancellation does not leak into the caller

level: MUST NOT

## AFRAME_007

`await result()` で待っている呼び出し側がキャンセルされても、フレームはキャンセルも停止もされてはならない。待つのをやめるのは呼び出し側だけである。

title: Cancelling a waiter does not cancel the frame

level: MUST NOT

## AFRAME_008

`AsyncFrame.error` は、ルーティンが例外で終わった場合(gpframe が要求していないキャンセルを含む)はその例外を、それ以外の場合は `None` を返す。stopped のフレームと実行中のフレームでは `None` を返す。

title: Routine error

level: MUST

## AFRAME_009

`AsyncFrame.stopped` と `AsyncFrame.succeeded` は、それぞれ AFRAME_001 の状態であるときに `True` を返す。実行中は両方とも `False` を返す。

title: State properties

level: MUST

## AFRAME_010

`AsyncFrame.incomplete` は、不完全に終わったサブセッションの報告(`AsyncSessionReport`)を、終わった順に連結した一つの報告として返す。なければ `None` を返す。

title: Report of incomplete sub-sessions

level: MUST

## AFRAME_011

`result()` の呼び出しや `error` の参照によって、失敗が承認されたことになってはならない。

title: Reading a result does not acknowledge

level: MUST NOT

## AFRAME_012

失敗の承認は `ignore()` か `escalate(reason)` で行う。承認できるのは、broken のフレームのうち、まだ承認されていないものだけである。実行中、succeeded、stopped、承認済みのフレームに対しては、状態を変えずに `FrameStateError` を送出しなければならない。

title: Acknowledgement

level: MUST

condition: `ignore()` か `escalate()` を呼んだとき。

## AFRAME_013

承認は一度きりで、取り消しや付け替えの手段は提供しない。この点は同期版と同じ考え方による。

title: Acknowledgement is final

level: INFORMATIVE

## AFRAME_014

ルーティンが `KeyboardInterrupt` または `SystemExit` で終わった場合、フレームを broken として記録したうえで、その例外を握りつぶさずに asyncio へ渡さなければならない。中断や終了の要求をフレームの中で止めてしまうと、プログラムを止められなくなるためである。

渡した例外は、asyncio の通常の規則に従ってループの外(`asyncio.run()` の呼び出し側など)へ伝わる。そのため、セッションの終了処理は、ループの終了に伴うキャンセルとして行われうる(ASESSION_016)。例外はフレームに記録して呼び出し側にも届けるので、asyncio の「取り出されなかったタスクの例外」のログは出さない。

title: Interrupts are not swallowed

level: MUST

## AFRAME_015

停止を要求されたセッションの `spawn()` が返すフレームは、タスクを作らず、ルーティンを呼ばずに、終了した状態で返る stopped のフレームでなければならない。

- `stopped` は `True`、`running` と `succeeded` は `False` を返す。
- `error` と `incomplete` は `None`、`stop_errors` は空である。
- `await result()` は `FrameStoppedError` を送出する。
- broken ではないので、承認を求めない。

同期版の FRAME_012 と同じ考え方で、止まる途中で始めようとした仕事は失敗ではない。

title: Frames spawned after a stop

level: MUST

## AFRAME_016

終了したフレームは、ルーティンとその引数への参照を手放さなければならない。戻り値、例外、報告、停止コールバックの例外は保持する(例外のトレースバックが参照するものは、その例外とともに残る)。同期版の FRAME_013 と同じ。

title: Releasing the routine

level: MUST

## AFRAME_017

`await AsyncFrame.wait(timeout=None)` は、ループを止めずに、フレームが終了するまで最大 `timeout` 秒待ち、終了していれば `True`、時間切れなら `False` を返さなければならない。

- フレームがどう終わったかによらず、例外を送出しない(stopped のフレームではすぐに `True` を返す)。
- 失敗の承認にはならない。
- 待っている呼び出し側がキャンセルされても、フレームはキャンセルも停止もされない(AFRAME_007 と同じ)。

title: Waiting for a frame to end

level: MUST

## AFRAME_018

stopped のフレームはルーティンを呼ばないので、引数に渡したもの(受け付けたソケットなど)を後始末する責任は、`spawn()` を呼んだ側に残る。同期版の FRAME_015 と同じ。

title: Arguments of a stopped frame

level: INFORMATIVE
