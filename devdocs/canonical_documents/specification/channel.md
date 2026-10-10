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

# Channel

フレーム間で値を順に受け渡し、送受信の待ちが停止の要求で解ける `Channel` に関する規則。

## CHANNEL_001

`Channel` は、フレームの間で値を先入れ先出しで受け渡すための部品である。受け取る側は、値が届くか、停止が要求されるか、チャネルが閉じられるまで待つ。容量に上限を付けた場合は、加える側も空きが出るまで待つ。どちらの待ちも停止で解けるので、送受信のループを書くだけで止められるワーカーになる。

```python
jobs = gpframe.Channel(Job, maxsize=100)


def producer(ctx: gpframe.Context, jobs: gpframe.Channel[Job]) -> None:
    for job in source():
        if not jobs.put(job, ctx):  # 満杯なら空くまで待つ。停止なら False
            return
    jobs.close()


def consumer(ctx: gpframe.Context, jobs: gpframe.Channel[Job]) -> None:
    for job in jobs.receive(ctx):  # 停止か、閉じて空になったら終わる
        handle(job)
```

title: Purpose

level: INFORMATIVE

## CHANNEL_002

`Channel(typ, maxsize=0)` の `typ` は、`isinstance()` で検査できる実行時のクラスでなければならず、`NoneType` であってはならない。満たさない場合は `DeclaredTypeError` を送出する。宣言した型は `Channel.type` で読める。

title: Declared type

level: MUST

related: [SHARED_001](shared.md#shared_001)

## CHANNEL_016

`maxsize` は 0 以上の整数でなければならず、負の数は作成時に `ValueError` で拒否する。0 は上限なしを表す。正の数なら、チャネルが持つ値の数は `maxsize` を超えてはならない。設定した値は `Channel.maxsize` で読める。

title: Capacity

level: MUST

## CHANNEL_003

`put(item, ctx=None, timeout=None)` の `item` は、宣言した型のインスタンスで `None` でないものでなければならない。満たさない場合は `DeclaredTypeError` を送出し、何も加えない。`None` を入れられないので、受け取りの `None` は「値がない」ことだけを表す。

title: Putting values

level: MUST

related: [SHARED_002](shared.md#shared_002)

## CHANNEL_004

`ctx` を渡さない `put(item)` は、待たずに戻らなければならない。フレームの外のスレッドからも呼べる。戻り値で確かめることがないので、`None` を返す(`ctx` を渡す `put()` だけが `bool` を返す)。

| 状態 | 結果 |
| --- | --- |
| 空きがある(上限なしなら常に) | 末尾に加える(戻り値は `None`) |
| 満杯 | 何も加えずに `ChannelFullError` を送出する |
| 閉じられている | 何も加えずに `ChannelClosedError` を送出する(CHANNEL_005) |

title: Putting without a context never waits

level: MUST

## CHANNEL_005

`ctx` を渡さない `put()` は、閉じられたチャネルには何も加えずに `ChannelClosedError` を送出しなければならない。`ctx` を渡した `put()` は、閉じられていれば何も加えずに `False` を返す(CHANNEL_017)。

title: Putting after close

level: MUST

## CHANNEL_017

`ctx` を渡した `put(item, ctx, timeout=None)` は、空きがあれば末尾に加えて `True` を返す。満杯なら、次のどれかが起きるまで最大 `timeout` 秒待たなければならない。`timeout` が `None` なら上限なく待つ。

| 起きたこと | 結果 |
| --- | --- |
| 空きができた | 末尾に加え、`True` を返す |
| `ctx` のセッションに停止が要求された | 何も加えずに `False` を返す |
| チャネルが閉じられた | 何も加えずに `False` を返す |
| `timeout` 秒が経った | 何も加えずに `False` を返す |

呼んだ時点で停止が要求されているか、閉じられている場合も、空きによらず何も加えずに `False` を返す。停止の後に新しい仕事を流さないためであり、同じ条件の結果が呼んだ時点によって変わらないためである。停止による待ちの解除は CHANNEL_010 の `get()` と同じく、取りこぼしなく起き、登録を残さない。`timeout` は `None` か 0 以上の数でなければならず、負の数は `ValueError` で拒否する。

title: Putting with a context waits for space

level: MUST

related: [STOP_011](stop.md#stop_011), [STOP_016](stop.md#stop_016)

## CHANNEL_018

`put()` が `False` を返した理由は、`ctx.stopping` と `Channel.closed` で区別できる。どちらでもなければ時間切れである。

title: Telling why put() returned False

level: INFORMATIVE

## CHANNEL_006

値は、加えられた順に取り出されなければならない。一つの値を受け取るのは、一つの受け取り手だけである。複数のフレームが同じチャネルから受け取る場合、値はそれらの間で分け合われる。

title: Order and delivery

level: MUST

## CHANNEL_007

`get(ctx, timeout=None)` は、次の値を取り出して返す。チャネルが空なら、次のどれかが起きるまで最大 `timeout` 秒待たなければならない。`timeout` が `None` なら上限なく待つ。

| 起きたこと | 結果 |
| --- | --- |
| 値が加えられた | その値を返す |
| `ctx` のセッションに停止が要求された | `None` を返す |
| チャネルが閉じられた | `None` を返す |
| `timeout` 秒が経った | `None` を返す |

`timeout` は `None` か 0 以上の数でなければならず、負の数は `ValueError` で拒否する。

title: Getting a value

level: MUST

## CHANNEL_008

`ctx` のセッションに停止が要求されている間、`get()` はチャネルに値が残っていても取り出さずに `None` を返さなければならない。停止の後に新しい仕事を始めないためである。取り出されなかった値はチャネルに残る。

title: Stop takes precedence over values

level: MUST

related: [STOP_002](stop.md#stop_002)

## CHANNEL_009

閉じられたチャネルに値が残っている間、`get()` はその値を返さなければならない。閉じることは「もう加えない」という知らせであり、加えた値は受け取り手に届く。`None` を返すのは、閉じられていて、かつ空になったときである。

title: Close lets remaining values through

level: MUST

## CHANNEL_010

`get()` の停止による待ちの解除は、停止がどの経路で要求されても(`stop()`、親からの伝播、セッション自身による要求)、停止コールバックと同じく取りこぼしなく起きなければならない。`get()` が戻った後に、そのための登録を残してはならない。

title: Waking on a stop request

level: MUST

related: [STOP_011](stop.md#stop_011), [STOP_012](stop.md#stop_012)

## CHANNEL_011

`receive(ctx)` は、`get(ctx)` が値を返す間その値を順に返し、`None` を返したところで終わる反復子でなければならない。

title: Receiving in a loop

level: MUST

## CHANNEL_012

`get()` が `None` を返した理由は、`ctx.stopping` と `Channel.closed` で区別できる。どちらでもなければ時間切れである。

title: Telling why get() returned None

level: INFORMATIVE

## CHANNEL_013

`close()` はチャネルを閉じ、待っているすべての `get()` を起こさなければならない。二度以上呼んでも、一度呼んだ場合と同じ状態になる。閉じたチャネルを開き直す手段は提供しない。`closed` は閉じられていれば `True` を返す。

title: Closing

level: MUST

## CHANNEL_014

`get()`、`receive()`、`put()` に、それを呼んでいるフレーム以外の `Context` を渡してはならない。待ちは渡した `Context` のセッションの停止で解けるので、別のフレームの `Context` では、呼んでいるフレームが止められなくなることがある。

title: Which context to pass

level: MUST NOT

condition: `get()`、`receive()`、`ctx` を渡す `put()` を呼ぶとき。

## CHANNEL_015

次のものは提供しない。

- 満杯のときに古い値や新しい値を捨てる扱い。値を黙って失わないため、満杯は待つか(`ctx` あり)、例外(`ctx` なし)のどちらかで表す。
- 複数のチャネルを同時に待つ手段(select)。
- 非同期版の `Channel`。非同期版では停止がキャンセルなので、`asyncio.Queue` の待ちがそのまま止まる。`Channel` の `get()` をループの上で呼ぶと、ループをブロックする。

title: What Channel does not provide

level: INFORMATIVE
