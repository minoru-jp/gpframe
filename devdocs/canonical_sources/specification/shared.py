"""共有セル `Shared` に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    SHOULD,
    condition,
    level,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title


@summary(
    "型の固定された共有セル Shared の生成、読み書き、アトミックな更新に関する規則。"
)
@canonical_source(
    "Shared", filename="shared.md", order=40, merge_policy="local", heading="identity"
)
class SPECIFICATION_PART:
    """型の固定された共有セル `Shared` の生成、読み書き、アトミックな更新に関する規則。"""

    class SHARED_001:
        """`Shared(typ, value)` の `typ` は、`isinstance()` で検査できる実行時のクラスでなければならず、`NoneType` であってはならない。満たさない場合は `DeclaredTypeError` を送出する。`list[int]` のような型式は拒否される。"""

        title @= "Declared type"
        level @= MUST

    class SHARED_002:
        """`Shared` が保持する値は、常に宣言した型のインスタンスであり、`None` であってはならない。生成時の値、`set()` と `swap()` に渡す値、`apply()` の関数の結果は、すべてこの条件で検査する。満たさない場合は `DeclaredTypeError` を送出し、値は変えない。"""

        title @= "The value always matches the type"
        level @= MUST

    class SHARED_003:
        """型の検査は `isinstance()` による。宣言した型のサブクラスのインスタンスも受け入れる(`Shared(int, 0)` は `True` を受け入れる)。"""

        title @= "Subclass instances"
        level @= INFORMATIVE

    class SHARED_004:
        """`get()` は現在の値を返す。`set(value)` は値を置き換える。`swap(value)` は値を置き換え、置き換える前の値を返す。"""

        title @= "Reading and replacing"
        level @= MUST

    class SHARED_005:
        """`apply(fn)` は、現在の値を `fn` に渡し、その結果で値を置き換え、置き換えた後の値を返す。読み取りから書き込みまでを一つの操作として行い、並行した `apply()`、`set()`、`swap()` の更新を失ってはならない。"""

        title @= "Atomic update"
        level @= MUST

    class SHARED_006:
        """`apply()` の `fn` が例外を送出した場合、その例外をそのまま送出し、値は変えない。"""

        title @= "Failing update functions"
        level @= MUST

    class SHARED_007:
        """`apply()` の `fn` はロックを持ったまま呼ばれるので、短く、副作用がなく、同じ `Shared` を操作しない関数にすべきである。"""

        title @= "Writing update functions"
        level @= SHOULD
        condition @= "`apply()` に渡す関数を書くとき。"

    class SHARED_008:
        """複数の値を常に一貫させたい場合は、不変のデータクラスを一つの `Shared` に入れ、`apply()` で丸ごと差し替えるべきである。複数の `Shared` にまたがる不可分な操作は提供しない。"""

        title @= "Keeping several values consistent"
        level @= SHOULD
