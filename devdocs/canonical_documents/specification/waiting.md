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

# Waiting

すべてのフレームの終了を待つ方法と、最初の失敗を待つ方法に関する規則。

## WAIT_001

`Session.running()` は、まだ終了していないフレームがあれば `True` を返さなければならない。

title: Running frames

level: MUST

## WAIT_002

`Session.wait(timeout)` は、すべてのフレームが終了するまで最大 `timeout` 秒待ち、時間内にすべて終了すれば `True`、そうでなければ `False` を返さなければならない。待っている間に起動されたフレームの終了も待つ。`timeout` が `None` なら、すべて終了するまで待つ。

title: Waiting for all frames

level: MUST

## WAIT_003

`Session.wait_broken(timeout, *, idle=False)` は、次のどれかが成り立つまで最大 `timeout` 秒待たなければならない。

- まだ承認されていない broken frame がある
- 実行中のフレームがない(`idle=False` のとき。`idle=True` の場合は WAIT_007)
- `timeout` 秒が経った

呼び出した時点ですでに成り立っていれば、すぐに戻る。`timeout` が `None` なら、時間切れにはならない。

title: Waiting for the first failure

level: MUST

related: [FRAME_001](frame.md#frame_001)

## WAIT_004

`wait_broken()` は、戻る時点の `broken()` と同じ並びを返さなければならない。空でなければ失敗によって、空なら終了か時間切れによって戻ったことを表す。この二つは `running()`(WAIT_001)で区別できる。

title: Result of wait_broken

level: MUST

related: [SESSION_008](session.md#session_008)

## WAIT_005

`wait_broken()` が返したフレームを、承認されたものとして扱ってはならない。続けて呼んだ `wait_broken()` は、承認されるまで同じフレームを返し続ける。

title: Waiting does not acknowledge

level: MUST NOT

related: [FRAME_005](frame.md#frame_005)

## WAIT_006

長く動き続ける部品を連結し、どれか一つが失敗したら全体を止める処理は、次の形で書ける。

```python
with gpframe.session(timeout=10) as s:
    for component in components:
        s.spawn(component)
    if failed := s.wait_broken():
        for frame in failed:
            frame.escalate()
        s.stop()
```

失敗した部品だけを起動し直す場合は、`wait_broken()` を繰り返し呼び、承認したうえで同じルーティンを `spawn()` し直す。

title: Supervising long-running components

level: INFORMATIVE

## WAIT_007

`wait_broken(idle=True)` は、実行中のフレームがないことでは戻らず、次のどれかが成り立つまで待たなければならない。

- まだ承認されていない broken frame がある
- セッションに停止が要求されている
- `timeout` 秒が経った

停止の要求で戻ることで、待ち続けるループを停止で抜けられる。戻り値は WAIT_004 と同じく、戻る時点の `broken()` である。

title: Waiting while idle

level: MUST

## WAIT_008

接続や要求ごとにフレームを起動するサーバーのように、セッションにフレームが増えたり減ったりする場合は、`idle=True` で失敗を待ち続け、一つの階層で失敗を閉じる。`selectors` のループと同じ形である。

```python
while not ctx.stopping:
    for frame in clients.wait_broken(idle=True):
        log(frame)
        frame.ignore()
```

title: Supervising a changing set of frames

level: INFORMATIVE
