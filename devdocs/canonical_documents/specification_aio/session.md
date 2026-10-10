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

# Async session

非同期のセッションの開閉、同期版との型の分離、フレームの起動、終了時の判定、サブセッションに関する規則。

## ASESSION_001

ルートの非同期セッションは `gpframe.aio.session(timeout, strict)` で作り、フレームの中のサブセッションは `AsyncContext.session(timeout)` で作る。どちらも `async with` で開いて使う。

title: Creating sessions

level: INFORMATIVE

## ASESSION_002

非同期版は `gpframe.aio` に独自の型を持ち、同期版の型と混ぜてはならない。非同期版の型は `AsyncSession`、`AsyncFrame`、`AsyncContext`、`AsyncSessionReport`、`AsyncSessionFailed`、`AsyncIncompleteSessionError`、`gpframe.aio.StopHandle`、およびヘルスチェックの `LoopMonitor`、`LoopStall`、`LoopRecovery`、`HealthWarning` である。

同期版と共有するのは、実行モデルに依存しない型だけである。すなわち `Shared`、`FrameWarning`、およびフレームを持たない例外(`GpFrameError`、`SessionStateError`、`FrameStateError`、`FrameStoppedError`、`FrameAbortedError`、`DeclaredTypeError`)である。`Channel` は同期版だけの部品であり、非同期版では使わない。

title: Separation from the synchronous API

level: MUST

## ASESSION_003

非同期のセッションを `async with` で開けるのは一度だけである。二度目は `SessionStateError` を送出する。同期の `with` では開けない。

title: A session is entered once

level: MUST

## ASESSION_004

`timeout` は `None` か 0 以上の数でなければならない。負の数はセッションの作成時に `ValueError` で拒否する。

title: Timeout values

level: MUST

## ASESSION_005

`spawn()` は、開いているセッションでだけ使える。開く前または閉じた後は、フレームを作らずに `SessionStateError` を送出しなければならない。停止を要求された後は、タスクを作らずに stopped のフレームを返さなければならない(AFRAME_015)。ASESSION_006 の検査は、停止の後でも行う。

title: Spawning needs an open session

level: MUST

related: [ALIMIT_007](limits.md#alimit_007), [AFRAME_015](frame.md#aframe_015)

## ASESSION_006

`spawn(fn, *args, name=None)` の `fn` はコルーチン関数でなければならない(`inspect.iscoroutinefunction()` が真)。そうでなければ、フレームを起動せずに `TypeError` を送出する。同期関数をループの上で呼ぶと、ループをブロックしうるためである。

title: Routines are coroutine functions

level: MUST

related: [ALIMIT_001](limits.md#alimit_001)

## ASESSION_007

`spawn()` は、セッションのループにタスクを作り、そのタスクの中で `await fn(context, *args)` を実行しなければならない。ルーティンへの引数は位置引数だけを渡す。`spawn()` 自体はコルーチンではなく、すぐに `AsyncFrame` を返す。

title: Running a routine

level: MUST

## ASESSION_008

`name` を省略した場合、フレームの名前はルーティンの `__name__`、それがなければ型名とする。名前はログと報告のためのもので、重複してもよい。

title: Frame names

level: MUST

## ASESSION_009

`broken()` は、まだ承認されていない broken のフレームだけを、起動した順に返さなければならない。実行中、succeeded、stopped、承認済みのフレームを含めてはならない。

title: Listing unacknowledged failures

level: MUST

related: [AFRAME_001](frame.md#aframe_001), [AFRAME_012](frame.md#aframe_012)

## ASESSION_010

`async with` を抜けるとき、セッションは次の順で処理しなければならない。

1. `async with` ブロック内で例外が起きていれば(所有タスク自身のキャンセルを含む)、停止を要求する。
2. 最大 `timeout` 秒、すべてのフレームの終了を待つ。
3. 閉じた状態に移り、まだ終わっていないフレームを stuck frame とする。
4. stuck frame があれば停止を要求し、待たずに切り離す。
5. ルートのセッションなら終了時の判定を、サブセッションなら親フレームへの報告を行う。

title: Exit procedure

level: MUST

related: [ALIMIT_003](limits.md#alimit_003), [ALIMIT_004](limits.md#alimit_004)

## ASESSION_011

2. の待機の間に `__aexit__` を実行しているタスク自身がさらにキャンセルされた場合は、待機をそこで打ち切り、3. 以降へ進む。キャンセルに応じることを、待機の完了より優先する。

title: Cancellation while waiting at exit

level: MUST

## ASESSION_012

ルートのセッションは、stuck frame があれば、その名前を挙げた `FrameWarning` を出さなければならない。

title: Reporting stuck frames

level: MUST

## ASESSION_013

ルートのセッションは、終了時の broken のフレームを承認に応じて次のように扱わなければならない。stopped のフレームについては何もしない。

| 承認 | 結果 |
| --- | --- |
| `ignore()` 済み | 何もしない |
| `escalate()` 済み | `AsyncSessionFailed` に含めて送出する |
| 承認なし(`strict=False`) | 名前を挙げた `FrameWarning` を出す |
| 承認なし(`strict=True`) | `AsyncSessionFailed` に含めて送出する |

承認されていない broken のフレームを、警告も例外もなしに捨ててはならない。

title: Judgement at the root

level: MUST

related: [AFRAME_002](frame.md#aframe_002), [AFRAME_012](frame.md#aframe_012)

## ASESSION_014

`AsyncSessionFailed` は `ExceptionGroup` であり、送出の対象になったフレームごとに一つの例外を、起動した順に持たなければならない。`frames` 属性は、同じ順に対応するフレームを持つ。各フレームの例外は次の優先順で決める。

1. ルーティンが `Exception` で終わった場合は、その例外。
2. ルーティンがそれ以外の `BaseException`(gpframe が要求していないキャンセルを含む)で終わった場合は、それを `__cause__` に持つ `FrameAbortedError`。
3. 停止コールバックが例外を送出した場合は、最初の例外(`Exception` 以外なら 2. と同様に包む)。
4. それ以外(サブセッションが不完全だった場合)は、報告を持つ `AsyncIncompleteSessionError`。

`split()` と `subgroup()` で分けた結果も `AsyncSessionFailed` であり、残った例外に対応するフレームだけを持つ。

title: Contents of AsyncSessionFailed

level: MUST

related: [AFRAME_003](frame.md#aframe_003)

## ASESSION_015

`async with` ブロック内の例外が `asyncio.CancelledError` 以外で、`AsyncSessionFailed` の送出と重なった場合は `AsyncSessionFailed` を送出し、ブロック内の例外はその `__context__` として残す。`AsyncSessionFailed` を送出しない場合は、ブロック内の例外をそのまま再送出する。

title: Body errors and AsyncSessionFailed

level: MUST

## ASESSION_016

`async with` ブロック内の例外が `asyncio.CancelledError` の場合(所有タスク自身がキャンセルされた場合)、`__aexit__` はそれを再送出しなければならず、`AsyncSessionFailed` に置き換えてはならない。本来 `AsyncSessionFailed` で送出するはずだった失敗は、名前を挙げた `FrameWarning` で報告する。asyncio のキャンセルの伝わり方を壊さないためである。

title: The owner's cancellation takes precedence

level: MUST

## ASESSION_017

サブセッションは、`async with` を抜けるときに警告を出してはならず、独自の例外を送出してはならない。最終的な判断はルートのセッションだけが行う。

title: Sub-sessions do not judge

level: MUST NOT

## ASESSION_018

サブセッションは、次のどれかに当てはまる場合に不完全であり、その報告(`AsyncSessionReport`)を親フレームに付けなければならない。

- `ignore()` されていない broken のフレームがある(`escalate()` 済みのものも含む)
- stuck frame がある
- `async with` ブロック内で例外が起きた。ただし、親フレームのセッションが停止を要求したことによる `asyncio.CancelledError` は含めない

報告の `broken`、`stuck`、`errors` は、それぞれ上の三つに対応する。stopped のフレームは、どれにも当たらない。

title: Incomplete sub-sessions

level: MUST

related: [AFRAME_003](frame.md#aframe_003), [AFRAME_010](frame.md#aframe_010)

## ASESSION_019

サブセッションの `async with` ブロック内で起きた例外は、報告に記録した場合も記録しない場合も、そのまま再送出しなければならない。

title: Body errors in sub-sessions

level: MUST

## ASESSION_020

ルートで親フレームを `ignore()` した場合、そのフレームの配下で起きた失敗もまとめて許したことになる。

title: Ignoring a parent forgives its children

level: INFORMATIVE

## ASESSION_021

セッションは、終了時の判定と報告に要らなくなったフレーム(succeeded、stopped、`ignore()` 済みの broken)を保持してはならない。終了した時点、または `ignore()` した時点で手放す。同期版の SESSION_019 と同じ。

title: A session keeps only what the judgement needs

level: MUST

related: [AFRAME_016](frame.md#aframe_016)
