"""共有セル `Shared` の契約。

旧設計の Message が守ろうとしていた整合性のうち、本当に必要だった
型の固定とアトミックな更新だけを約束する。
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

from contract.ports.surface import Shared


class SharedContract:
    subject @= Shared

    class ValueAlwaysMatchesType:
        """保持する値は常に宣言した型のインスタンスで、`None` にはならない。"""

        kind @= INV
        source @= "specification/shared.md#SHARED_002"
        rationale @= "フレームごとに型の想定がずれる「型の漂流」を防ぐ。"

    class set:
        member @= Shared.set

        class ValueMatchesType:
            """置く値は宣言した型のインスタンスで、`None` ではない。"""

            kind @= PRE
            source @= "specification/shared.md#SHARED_002"
            on_violation @= REJECTED

    class apply:
        member @= Shared.apply

        class ResultMatchesType:
            """`fn` の結果は宣言した型のインスタンスで、`None` ではない。違反した場合、値は変わらない。"""

            kind @= PRE
            source @= "specification/shared.md#SHARED_002"
            on_violation @= REJECTED

        class IsAtomic:
            """読み取りから書き込みまでを一つの操作として行い、並行した `apply()` の更新を失わない。"""

            kind @= POST
            source @= "specification/shared.md#SHARED_005"
            rationale @= "get() と set() の間に割り込まれる lost update を防ぐ。"
