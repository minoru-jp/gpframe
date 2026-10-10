"""イベントループの応答を監視するヘルスチェックに関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MAY,
    MUST,
    MUST_NOT,
    SHOULD,
    condition,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification_aio.limits import (
    SPECIFICATION_PART as LIMITS_SPEC,
)


@summary(
    "ループが応答しなくなったことを、ループの外から検出して報告するヘルスチェックに関する規則。セッションの約束の外側にある観測の道具。"
)
@canonical_source(
    "Health monitoring",
    filename="health.md",
    order=50,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """
    ループが応答しなくなったことを、ループの外から検出して報告するヘルスチェックに関する規則。

    ループがブロックされると、セッションの約束(待機の打ち切り、停止、報告)はすべて失われる。ヘルスチェックはその状態を、利用者が観測できるようにするための道具である。セッションの約束を取り戻すものではなく、ブロックを解くこともしない。
    """

    class AHEALTH_001:
        """ヘルスチェックは、ALIMIT_002 で失われる保証を補うものではなく、保証が失われていることを観測可能にするものである。セッションとは独立して動き、セッションの状態を変えない。"""

        title @= "Purpose and position"
        level @= INFORMATIVE
        related @= (LIMITS_SPEC.ALIMIT_002,)

    class AHEALTH_002:
        """ヘルスチェックは `gpframe.aio.monitor(threshold=1.0, *, interval=None, on_stall=None, on_recover=None)` で作り、`async with` で開いて使う。開いたときに動いていたイベントループを監視する。監視の単位はセッションではなくループである。"""

        title @= "Creating a monitor"
        level @= INFORMATIVE

    class AHEALTH_003:
        """`threshold` は 0 より大きい秒数でなければならず、省略時は 1.0 秒とする。`interval` は 0 より大きく `threshold` 以下でなければならず、省略時は `threshold / 4` とする。満たさない場合は作成時に `ValueError` を送出する。実際に使われる値は `LoopMonitor.threshold` と `LoopMonitor.interval` で読める。"""

        title @= "Parameter values"
        level @= MUST

    class AHEALTH_004:
        """`LoopMonitor` を `async with` で開けるのは一度だけで、二度目は `SessionStateError` を送出する。一つのループに複数のヘルスチェックを開いてよく、それぞれは独立して動く。"""

        title @= "Entering a monitor"
        level @= MUST

    class AHEALTH_005:
        """
        ヘルスチェックは、次の二つの部品で応答を測らなければならない。

        - ループ上で `interval` 秒ごとに時刻を記録する、心拍のタスク
        - ループの外のスレッドで `interval` 秒ごとに、最後の心拍からの経過時間(遅れ)を測る、監視スレッド

        遅れが `threshold` 秒を超えたとき、ループは停滞(stall)しているとみなす。
        """

        title @= "Heartbeat and watcher"
        level @= MUST

    class AHEALTH_006:
        """ヘルスチェックが測るのは、ループの応答の遅れである。一つのブロッキング呼び出しによる停滞と、多数の処理による過負荷を区別しない。"""

        title @= "What is measured"
        level @= INFORMATIVE

    class AHEALTH_007:
        """停滞の検出は、停滞が始まってから最大でおよそ `threshold + interval` 秒遅れる。`threshold` 秒より短い停滞は報告しない。"""

        title @= "Detection latency"
        level @= INFORMATIVE

    class AHEALTH_008:
        """一続きの停滞につき、停滞の検出は一度だけ報告しなければならない。ループが応答を取り戻したら(心拍が記録されたら)、回復を一度だけ報告し、次の停滞の検出に備える。"""

        title @= "One report per stall"
        level @= MUST

    class AHEALTH_009:
        """
        停滞を検出したら、`LoopStall` を `on_stall` に渡して呼ばなければならない。`LoopStall` は次の値を持つ。

        - `started`:最後に心拍を記録した時刻(`time.monotonic()` の値)
        - `detected`:停滞を検出した時刻(同上)
        - `stack`:検出した時点の、ループのスレッドのスタック(文字列の並び)。取得できなければ `None`

        `on_stall` を省略した場合は、遅れの秒数と `stack` の最後の行を含む `HealthWarning` を出す。停滞を黙って見過ごさないためである。
        """

        title @= "Reporting a stall"
        level @= MUST

    class AHEALTH_010:
        """`LoopStall.stack` は、検出した瞬間のループのスレッドのスタックの写しであり、取得した後にループが先へ進んでいることがある。停滞の原因の場所を正確に指すとは保証しない。CPython 以外では `None` になりうる。"""

        title @= "The stack is a best-effort snapshot"
        level @= INFORMATIVE

    class AHEALTH_011:
        """回復を検出したら、`LoopRecovery`(`started`、`recovered`、`duration`)を `on_recover` に渡して呼ばなければならない。`on_recover` を省略した場合は何もしない。"""

        title @= "Reporting a recovery"
        level @= MUST

    class AHEALTH_012:
        """`on_stall` と `on_recover` は、監視スレッドで呼ばれる。ループはブロックされているかもしれないので、コールバックの中でループ上の非同期 API を待ってはならない。スレッドセーフな操作(ログ、`AsyncSession.stop()` など)だけを使う。"""

        title @= "Callbacks run on the watcher thread"
        level @= MUST_NOT
        condition @= "`on_stall` と `on_recover` を書くとき。"
        related @= (LIMITS_SPEC.ALIMIT_007,)

    class AHEALTH_013:
        """コールバックの中で `AsyncSession.stop()` を呼んでもよい。ただし ALIMIT_008 により、キャンセルが届くのはループが再開したときである。ヘルスチェックがセッションを自動で止めることはない。"""

        title @= "Stopping sessions from a callback"
        level @= MAY
        related @= (LIMITS_SPEC.ALIMIT_008,)

    class AHEALTH_014:
        """コールバックが例外を送出した場合、その例外を `LoopMonitor.errors` に記録し、それを含む `HealthWarning` を出さなければならない。監視はその後も続ける。"""

        title @= "Errors in monitor callbacks"
        level @= MUST

    class AHEALTH_015:
        """`LoopMonitor.stalled` は停滞中なら `True` を、`LoopMonitor.lag` は最後の心拍からの経過秒数を返す。どちらもどのスレッドから読んでもよい。外部のヘルスチェックの窓口(HTTP の生存確認など)から、ループに頼らずに状態を答えるのに使える。"""

        title @= "Querying the state"
        level @= MUST

    class AHEALTH_016:
        """`async with` を抜けるとき、ヘルスチェックは心拍のタスクと監視スレッドを止めなければならない。抜けた後に `on_stall` や `on_recover` が呼ばれてはならない。"""

        title @= "Closing a monitor"
        level @= MUST

    class AHEALTH_017:
        """ブロックしている処理が GIL を手放さない場合(GIL を保持したまま長く動く一部の C 拡張など)、監視スレッドも動けず、検出はその処理が GIL を手放すまで遅れる。これはヘルスチェック自体の原理的な限界である。"""

        title @= "When the watcher cannot run"
        level @= INFORMATIVE

    class AHEALTH_018:
        """`threshold` は、そのアプリケーションで許容できる応答の遅れに合わせて選ぶべきである。小さすぎると、ガベージコレクションや一時的な負荷による短い遅れまで停滞として報告する。既定の 1.0 秒は、付けておくだけで秒単位の本当のブロック(非同期のコードに混ざった同期の I/O や、重い計算のループなど)を見つけ、正常な揺らぎは報告しないことを狙った、一般的な用途向けの値である。応答の速さが重要な用途では 0.2 から 0.5 秒程度、重い処理を含む用途では 5 秒程度が目安になる。"""

        title @= "Choosing a threshold"
        level @= SHOULD

    class AHEALTH_019:
        """
        典型的な使い方は次のとおり。

        ```python
        async with gpframe.aio.monitor() as monitor:  # 1 秒を超える停滞を報告する
            async with gpframe.aio.session(timeout=10) as s:
                ...
        ```

        同期版にはヘルスチェックを設けない。同期版のフレームはそれぞれのスレッドで動き、一つのフレームが固まってもセッションの待機と報告は動き続けるためである。
        """

        title @= "Typical use"
        level @= INFORMATIVE
