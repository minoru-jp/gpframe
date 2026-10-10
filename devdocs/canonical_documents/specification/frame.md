<!--
この文書は `shikumi-devdoc` によって生成された canonical document です。
Canonical source は `devdocs/canonical_sources/specification/__init__.py` です。
直接編集しないでください。

公開文書作成方針

- `devdocs/canonical_documents/` にある日本語 canonical document を公開工程の入力とする。
- 翻訳では意味、構造、情報量を維持し、内容を勝手に追加・削除・要約しない。
- canonical document に `shikumi-devdoc:translation-metadata` が含まれる場合は、その `preserve_spelling` 指定の用語の表記を変更しない。
- コード、Python 識別子、コマンド、ファイルパス、URL は、翻訳上の必要がない限り変更しない。
- このコメントブロックは published document には含めない。
- published document は canonical document から派生する公開成果物として扱い、内容の変更が必要な場合は canonical source または realization context へ戻して canonical document を再生成する。
-->

# Frame

フレームの状態、戻り値と例外の受け取り、失敗の承認に関する規則。

## FRAME_001

フレームは `running` で始まり(FRAME_012 の stopped のフレームを除く)、一度だけ終了する。終了したフレームは succeeded、broken、stopped のどれか一つであり、終了後に状態が変わってはならない。

| 状態 | 意味 |
| --- | --- |
| succeeded | ルーティンが終わり、失敗がない |
| broken | 失敗があり、承認が必要 |
| stopped | 停止を要求されたセッションで起動されたため、ルーティンを呼ばずに終わった(FRAME_012) |

broken frame とは、終了したフレームのうち次のどれかに当てはまるものをいう。

- ルーティンが例外で終わった
- フレームの中で開いたサブセッションが不完全に終わった
- フレームの停止コールバックが例外を送出した

ルーティンを呼んで終了したフレームのうち、どれにも当てはまらないものが succeeded である。

title: Frame states

level: MUST

## FRAME_002

フレームの中で開いたサブセッションが不完全だった場合、ルーティンが値を返していても、そのフレームは broken frame でなければならない。

title: Incomplete sub-sessions break the frame

level: MUST

## FRAME_003

`Frame.result(timeout)` は、フレームが終了するまで最大 `timeout` 秒待たなければならない。終了していれば、ルーティンの戻り値を返すか、ルーティンが送出した例外を再送出する。stopped のフレームでは `FrameStoppedError` を送出する。時間内に終了しなければ `TimeoutError` を送出する。`timeout` が `None` なら終了するまで待つ。

title: Waiting for the result

level: MUST

## FRAME_004

ルーティンが値を返していれば、サブセッションが不完全だった場合や停止コールバックが例外を送出した場合でも、`result()` はその値を返す。

title: Result of a broken frame without a routine error

level: MUST

## FRAME_005

`result()` の呼び出しや `error` の参照によって、失敗が承認されたことになってはならない。

title: Reading a result does not acknowledge

level: MUST NOT

## FRAME_006

`Frame.error` は、ルーティンが例外で終わった場合はその例外を、それ以外の場合は `None` を返す。フレームの実行中も `None` を返す。

title: Routine error

level: MUST

## FRAME_007

`Frame.incomplete` は、フレームの中で不完全に終わったサブセッションの報告を返す。不完全なサブセッションが複数あった場合は、その `broken`、`stuck`、`errors` を終わった順に連結した一つの報告を返す。なければ `None` を返す。

title: Report of incomplete sub-sessions

level: MUST

## FRAME_008

失敗の承認は `ignore()` か `escalate(reason)` で行う。承認できるのは、終了した broken frame のうち、まだ承認されていないものだけである。

title: Acknowledgement

level: MUST

## FRAME_009

承認できないフレームに対する `ignore()` と `escalate()` は、フレームの状態を変えずに `FrameStateError` を送出しなければならない。

title: Rejected acknowledgement

level: MUST

condition: フレームが実行中、succeeded、stopped、または承認済みである。

## FRAME_010

一度付けた承認を取り消したり、別の承認に付け替えたりする手段は提供しない。承認は、失敗を見た人がその場で下す最終的な判断として扱う。

title: Acknowledgement is final

level: INFORMATIVE

## FRAME_011

`Exception` 以外の `BaseException`(`KeyboardInterrupt` など)でルーティンが終わった場合も、フレームの失敗として記録し、broken frame にしなければならない。

title: Non-Exception failures

level: MUST

## FRAME_012

停止を要求されたセッションの `spawn()` が返すフレームは、ルーティンを呼ばず、スレッドも作らずに、終了した状態で返る stopped のフレームでなければならない。

- `stopped` は `True`、`running` と `succeeded` は `False` を返す。
- `error` と `incomplete` は `None`、`stop_errors` は空である。
- broken frame ではないので、承認を求めない。セッションの終了時の判定にも含めない。

停止は頼んだ結果として起きる正常な結末であり、止まる途中で始めようとした仕事は失敗ではない。停止を確かめてから起動するまでの間に停止が来ても、例外にならない。

title: Frames spawned after a stop

level: MUST

## FRAME_013

終了したフレームは、ルーティンとその引数への参照を手放さなければならない。戻り値、例外、報告、停止コールバックの例外は保持する。引数に渡したもの(ソケットやバッファなど)が、フレームのハンドルを持ち続ける限り解放されない、ということを起こさないためである。ただし、保持する例外のトレースバックが参照するもの(例外が起きたときのローカル変数)は、その例外とともに残る。

title: Releasing the routine

level: MUST

## FRAME_014

`Frame.wait(timeout=None)` は、フレームが終了するまで最大 `timeout` 秒待ち、終了していれば `True`、時間切れなら `False` を返さなければならない。`timeout` が `None` なら終了するまで待つ。

- フレームがどう終わったかによらず、例外を送出しない(stopped のフレームではすぐに `True` を返す)。
- 失敗の承認にはならない(FRAME_005 と同じ)。

「一方が終わったら(正常でも失敗でも)、もう一方を止める」のように、終わり方を問わずに終わりだけを待つときに使う。結果は `result()` で、失敗の扱いは承認で決める。

title: Waiting for a frame to end

level: MUST

## FRAME_015

stopped のフレームはルーティンを呼ばないので、引数に渡したもの(受け付けたソケットなど)を後始末する責任は、`spawn()` を呼んだ側に残る。後始末が要るものを渡す場合は、`spawn()` の結果を確かめる。

```python
frame = clients.spawn(handle, conn)
if frame.stopped:
    conn.close()  # 走らないので、自分で閉じる
```

title: Arguments of a stopped frame

level: INFORMATIVE
