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

# Async waiting

非同期版で、すべてのフレームの終了と最初の失敗を、ループを止めずに待つ方法に関する規則。

## AWAIT_001

`AsyncSession.running()` はコルーチンではなく、まだ終了していないフレームがあれば `True` を返す。

title: Running frames

level: MUST

## AWAIT_002

`await AsyncSession.wait(timeout)` は、ループを止めずに、すべてのフレームが終了するまで最大 `timeout` 秒待ち、時間内にすべて終了すれば `True`、そうでなければ `False` を返す。待っている間に起動されたフレームの終了も待つ。

title: Waiting for all frames

level: MUST

## AWAIT_003

`await AsyncSession.wait_broken(timeout, *, idle=False)` は、ループを止めずに、次のどれかが成り立つまで最大 `timeout` 秒待たなければならない。呼び出した時点ですでに成り立っていれば、すぐに戻る。

- まだ承認されていない broken のフレームがある
- 実行中のフレームがない(`idle=False` のとき。`idle=True` の場合は AWAIT_008)
- `timeout` 秒が経った

title: Waiting for the first failure

level: MUST

related: [AFRAME_003](frame.md#aframe_003)

## AWAIT_004

`wait_broken()` は、戻る時点の `broken()` と同じ並びを返す。空なら失敗以外の理由で戻ったことを表し、どちらの理由かは `running()` で区別できる。stopped のフレームは失敗として扱わない。

title: Result of wait_broken

level: MUST

related: [ASESSION_009](session.md#asession_009)

## AWAIT_005

`wait_broken()` が返したフレームを、承認されたものとして扱ってはならない。

title: Waiting does not acknowledge

level: MUST NOT

related: [AFRAME_011](frame.md#aframe_011)

## AWAIT_006

`wait()` や `wait_broken()` で待っているタスクがキャンセルされた場合、待機はその `asyncio.CancelledError` で終わる。フレームはキャンセルも停止もされてはならない。

title: Cancelling a waiter does not stop frames

level: MUST NOT

related: [AFRAME_007](frame.md#aframe_007)

## AWAIT_007

長く動き続ける部品を連結し、どれか一つが失敗したら全体を止める処理は、次の形で書ける。同期版と違い、停止はキャンセルとして各部品の待機点に届く。

```python
async with gpframe.aio.session(timeout=10) as s:
    for component in components:
        s.spawn(component)
    if failed := await s.wait_broken():
        for frame in failed:
            frame.escalate()
        s.stop()
```

title: Supervising long-running components

level: INFORMATIVE

## AWAIT_008

`await wait_broken(idle=True)` は、実行中のフレームがないことでは戻らず、まだ承認されていない broken のフレームがあるか、セッションに停止が要求されているか、`timeout` 秒が経つまで待たなければならない。同期版の WAIT_007 と同じ。

title: Waiting while idle

level: MUST

## AWAIT_009

接続ごとにフレームを起動するサーバーは、`idle=True` で失敗を待ち続け、受け付けの階層で失敗を閉じる。停止はキャンセルとしてこの待機に届く。

```python
while True:
    for frame in await clients.wait_broken(idle=True):
        log(frame)
        frame.ignore()
```

title: Supervising a changing set of frames

level: INFORMATIVE
