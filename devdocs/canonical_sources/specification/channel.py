"""フレーム間で値を受け渡す Channel に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    MUST_NOT,
    condition,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification.shared import (
    SPECIFICATION_PART as SHARED_SPEC,
)
from devdocs.canonical_sources.specification.stop import (
    SPECIFICATION_PART as STOP_SPEC,
)


@summary(
    "フレーム間で値を順に受け渡し、送受信の待ちが停止の要求で解ける Channel に関する規則。"
)
@canonical_source(
    "Channel",
    filename="channel.md",
    order=50,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """フレーム間で値を順に受け渡し、送受信の待ちが停止の要求で解ける `Channel` に関する規則。"""

    class CHANNEL_001:
        """
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
        """

        title @= "Purpose"
        level @= INFORMATIVE

    class CHANNEL_002:
        """`Channel(typ, maxsize=0)` の `typ` は、`isinstance()` で検査できる実行時のクラスでなければならず、`NoneType` であってはならない。満たさない場合は `DeclaredTypeError` を送出する。宣言した型は `Channel.type` で読める。"""

        title @= "Declared type"
        level @= MUST
        related @= (SHARED_SPEC.SHARED_001,)

    class CHANNEL_016:
        """`maxsize` は 0 以上の整数でなければならず、負の数は作成時に `ValueError` で拒否する。0 は上限なしを表す。正の数なら、チャネルが持つ値の数は `maxsize` を超えてはならない。設定した値は `Channel.maxsize` で読める。"""

        title @= "Capacity"
        level @= MUST

    class CHANNEL_003:
        """`put(item, ctx=None, timeout=None)` の `item` は、宣言した型のインスタンスで `None` でないものでなければならない。満たさない場合は `DeclaredTypeError` を送出し、何も加えない。`None` を入れられないので、受け取りの `None` は「値がない」ことだけを表す。"""

        title @= "Putting values"
        level @= MUST
        related @= (SHARED_SPEC.SHARED_002,)

    class CHANNEL_004:
        """
        `ctx` を渡さない `put(item)` は、待たずに戻らなければならない。フレームの外のスレッドからも呼べる。戻り値で確かめることがないので、`None` を返す(`ctx` を渡す `put()` だけが `bool` を返す)。

        | 状態 | 結果 |
        | --- | --- |
        | 空きがある(上限なしなら常に) | 末尾に加える(戻り値は `None`) |
        | 満杯 | 何も加えずに `ChannelFullError` を送出する |
        | 閉じられている | 何も加えずに `ChannelClosedError` を送出する(CHANNEL_005) |
        """

        title @= "Putting without a context never waits"
        level @= MUST

    class CHANNEL_005:
        """`ctx` を渡さない `put()` は、閉じられたチャネルには何も加えずに `ChannelClosedError` を送出しなければならない。`ctx` を渡した `put()` は、閉じられていれば何も加えずに `False` を返す(CHANNEL_017)。"""

        title @= "Putting after close"
        level @= MUST

    class CHANNEL_017:
        """
        `ctx` を渡した `put(item, ctx, timeout=None)` は、空きがあれば末尾に加えて `True` を返す。満杯なら、次のどれかが起きるまで最大 `timeout` 秒待たなければならない。`timeout` が `None` なら上限なく待つ。

        | 起きたこと | 結果 |
        | --- | --- |
        | 空きができた | 末尾に加え、`True` を返す |
        | `ctx` のセッションに停止が要求された | 何も加えずに `False` を返す |
        | チャネルが閉じられた | 何も加えずに `False` を返す |
        | `timeout` 秒が経った | 何も加えずに `False` を返す |

        呼んだ時点で停止が要求されているか、閉じられている場合も、空きによらず何も加えずに `False` を返す。停止の後に新しい仕事を流さないためであり、同じ条件の結果が呼んだ時点によって変わらないためである。停止による待ちの解除は CHANNEL_010 の `get()` と同じく、取りこぼしなく起き、登録を残さない。`timeout` は `None` か 0 以上の数でなければならず、負の数は `ValueError` で拒否する。
        """

        title @= "Putting with a context waits for space"
        level @= MUST
        related @= (STOP_SPEC.STOP_011, STOP_SPEC.STOP_016)

    class CHANNEL_018:
        """`put()` が `False` を返した理由は、`ctx.stopping` と `Channel.closed` で区別できる。どちらでもなければ時間切れである。"""

        title @= "Telling why put() returned False"
        level @= INFORMATIVE

    class CHANNEL_006:
        """値は、加えられた順に取り出されなければならない。一つの値を受け取るのは、一つの受け取り手だけである。複数のフレームが同じチャネルから受け取る場合、値はそれらの間で分け合われる。"""

        title @= "Order and delivery"
        level @= MUST

    class CHANNEL_007:
        """
        `get(ctx, timeout=None)` は、次の値を取り出して返す。チャネルが空なら、次のどれかが起きるまで最大 `timeout` 秒待たなければならない。`timeout` が `None` なら上限なく待つ。

        | 起きたこと | 結果 |
        | --- | --- |
        | 値が加えられた | その値を返す |
        | `ctx` のセッションに停止が要求された | `None` を返す |
        | チャネルが閉じられた | `None` を返す |
        | `timeout` 秒が経った | `None` を返す |

        `timeout` は `None` か 0 以上の数でなければならず、負の数は `ValueError` で拒否する。
        """

        title @= "Getting a value"
        level @= MUST

    class CHANNEL_008:
        """`ctx` のセッションに停止が要求されている間、`get()` はチャネルに値が残っていても取り出さずに `None` を返さなければならない。停止の後に新しい仕事を始めないためである。取り出されなかった値はチャネルに残る。"""

        title @= "Stop takes precedence over values"
        level @= MUST
        related @= (STOP_SPEC.STOP_002,)

    class CHANNEL_009:
        """閉じられたチャネルに値が残っている間、`get()` はその値を返さなければならない。閉じることは「もう加えない」という知らせであり、加えた値は受け取り手に届く。`None` を返すのは、閉じられていて、かつ空になったときである。"""

        title @= "Close lets remaining values through"
        level @= MUST

    class CHANNEL_010:
        """`get()` の停止による待ちの解除は、停止がどの経路で要求されても(`stop()`、親からの伝播、セッション自身による要求)、停止コールバックと同じく取りこぼしなく起きなければならない。`get()` が戻った後に、そのための登録を残してはならない。"""

        title @= "Waking on a stop request"
        level @= MUST
        related @= (STOP_SPEC.STOP_011, STOP_SPEC.STOP_012)

    class CHANNEL_011:
        """`receive(ctx)` は、`get(ctx)` が値を返す間その値を順に返し、`None` を返したところで終わる反復子でなければならない。"""

        title @= "Receiving in a loop"
        level @= MUST

    class CHANNEL_012:
        """`get()` が `None` を返した理由は、`ctx.stopping` と `Channel.closed` で区別できる。どちらでもなければ時間切れである。"""

        title @= "Telling why get() returned None"
        level @= INFORMATIVE

    class CHANNEL_013:
        """`close()` はチャネルを閉じ、待っているすべての `get()` を起こさなければならない。二度以上呼んでも、一度呼んだ場合と同じ状態になる。閉じたチャネルを開き直す手段は提供しない。`closed` は閉じられていれば `True` を返す。"""

        title @= "Closing"
        level @= MUST

    class CHANNEL_014:
        """`get()`、`receive()`、`put()` に、それを呼んでいるフレーム以外の `Context` を渡してはならない。待ちは渡した `Context` のセッションの停止で解けるので、別のフレームの `Context` では、呼んでいるフレームが止められなくなることがある。"""

        title @= "Which context to pass"
        level @= MUST_NOT
        condition @= "`get()`、`receive()`、`ctx` を渡す `put()` を呼ぶとき。"

    class CHANNEL_015:
        """
        次のものは提供しない。

        - 満杯のときに古い値や新しい値を捨てる扱い。値を黙って失わないため、満杯は待つか(`ctx` あり)、例外(`ctx` なし)のどちらかで表す。
        - 複数のチャネルを同時に待つ手段(select)。
        - 非同期版の `Channel`。非同期版では停止がキャンセルなので、`asyncio.Queue` の待ちがそのまま止まる。`Channel` の `get()` をループの上で呼ぶと、ループをブロックする。
        """

        title @= "What Channel does not provide"
        level @= INFORMATIVE
