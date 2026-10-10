"""フレーム間で値を受け渡す `Channel` の契約。

型の固定、順序と一度きりの受け渡し、そして停止で受け取りの待ちが解けること。
最後のものが、この部品がある理由である。
"""

from shikumi_contrace import (
    INV,
    POST,
    PRE,
    REJECTED,
    kind,
    member,
    on_violation,
    rationale,
    source,
    subject,
)

from contract.ports.surface import Channel

C = "specification/channel.md#"


class ChannelContract:
    subject @= Channel

    class DeliversInOrderOnce:
        """値は加えられた順に取り出され、一つの値を受け取るのは一つの受け取り手だけである。"""

        kind @= INV
        source @= C + "CHANNEL_006"

    class NeverExceedsCapacity:
        """`maxsize` が正なら、チャネルが持つ値の数は `maxsize` を超えない。"""

        kind @= INV
        source @= C + "CHANNEL_016"
        rationale @= "加える側が速くても、メモリが入力の大きさに比例して増えない。"

    class put:
        member @= Channel.put

        class ItemMatchesType:
            """加える値は宣言した型のインスタンスで、`None` ではない。"""

            kind @= PRE
            source @= C + "CHANNEL_003"
            on_violation @= REJECTED
            rationale @= "受け取りの None を「値がない」ことだけに使える。"

        class WithoutContextChannelIsOpen:
            """`ctx` を渡さないなら、閉じたチャネルには加えられない(`ChannelClosedError`)。"""

            kind @= PRE
            source @= C + "CHANNEL_005"
            on_violation @= REJECTED

        class WithoutContextChannelHasSpace:
            """`ctx` を渡さないなら、満杯のチャネルには加えられない(`ChannelFullError`)。"""

            kind @= PRE
            source @= C + "CHANNEL_004"
            on_violation @= REJECTED
            rationale @= "値を黙って失わない。"

        class WithoutContextDoesNotWait:
            """`ctx` を渡さない `put()` は待たずに戻る。"""

            kind @= POST
            source @= C + "CHANNEL_004"

        class TimeoutIsValid:
            """`timeout` は `None` か 0 以上の数である。"""

            kind @= PRE
            source @= C + "CHANNEL_017"
            on_violation @= REJECTED

        class WithContextWaitsForSpace:
            """`ctx` を渡すと、満杯なら空きができるまで待って加え、`True` を返す。"""

            kind @= POST
            source @= C + "CHANNEL_017"

        class WithContextStopEndsTheWait:
            """`ctx` を渡した `put()` は、停止の要求、閉じられること、時間切れのどれでも、何も加えずに `False` を返す。呼んだ時点で停止か閉じられていても同じである。"""

            kind @= POST
            source @= C + "CHANNEL_017"
            source @= C + "CHANNEL_005"
            rationale @= (
                "加える側の待ちも、停止で解ける。結果が呼んだ時点によって変わらない。"
            )

    class get:
        member @= Channel.get

        class TimeoutIsValid:
            """`timeout` は `None` か 0 以上の数である。"""

            kind @= PRE
            source @= C + "CHANNEL_007"
            on_violation @= REJECTED

        class StopEndsTheWait:
            """空のチャネルを待っている間に停止が要求されると、どの経路の要求でも `None` を返す。"""

            kind @= POST
            source @= C + "CHANNEL_007"
            source @= C + "CHANNEL_010"
            rationale @= "受け取りのループを書くだけで、止められるワーカーになる。"

        class StopTakesPrecedence:
            """停止が要求されている間は、値が残っていても取り出さずに `None` を返す。"""

            kind @= POST
            source @= C + "CHANNEL_008"
            rationale @= "停止の後に新しい仕事を始めない。"

        class CloseLetsRemainingThrough:
            """閉じたチャネルからも残った値は取り出せ、空になってから `None` を返す。"""

            kind @= POST
            source @= C + "CHANNEL_009"

        class TimeoutReturnsNone:
            """`timeout` 秒のうちに値が来なければ `None` を返す。"""

            kind @= POST
            source @= C + "CHANNEL_007"

    class close:
        member @= Channel.close

        class WakesAllReceivers:
            """待っているすべての `get()` を起こす。"""

            kind @= POST
            source @= C + "CHANNEL_013"
