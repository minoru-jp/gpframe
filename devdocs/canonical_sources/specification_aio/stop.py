"""非同期版の停止(キャンセル)と停止コールバックに関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    MUST_NOT,
    SHOULD,
    condition,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification_aio.frame import (
    SPECIFICATION_PART as FRAME_SPEC,
)
from devdocs.canonical_sources.specification_aio.limits import (
    SPECIFICATION_PART as LIMITS_SPEC,
)
from devdocs.canonical_sources.specification_aio.session import (
    SPECIFICATION_PART as SESSION_SPEC,
)


@summary(
    "非同期版の停止の要求とキャンセルの配送、停止の伝わり方、停止コールバックに関する規則。"
)
@canonical_source(
    "Async stop", filename="stop.md", order=30, merge_policy="local", heading="identity"
)
class SPECIFICATION_PART:
    """非同期版の停止の要求とキャンセルの配送、停止の伝わり方、停止コールバックに関する規則。"""

    class ASTOP_001:
        """非同期版の停止は、asyncio のタスクのキャンセルで行う。キャンセルはルーティンの次の待機点(`await`)に `asyncio.CancelledError` として届く。これは同期版の「フラグを立てて、ルーティンに確認してもらう」方式とは異なる、非同期版の停止の方式である。"""

        title @= "Stop is cancellation"
        level @= INFORMATIVE

    class ASTOP_002:
        """`AsyncSession.stop()` は、停止の要求を記録し、そのセッションの実行中のすべてのフレームのタスクをキャンセルし、それらのフレームの中で開かれているサブセッションにも再帰的に停止を要求しなければならない。"""

        title @= "Stop cancels every frame"
        level @= MUST

    class ASTOP_003:
        """gpframe が一つのフレームのタスクをキャンセルするのは、多くても一度である。`stop()` を何度呼んでも、キャンセルを捕まえて後始末をしているルーティンに、重ねてキャンセルを送ってはならない。"""

        title @= "A frame is cancelled at most once"
        level @= MUST_NOT

    class ASTOP_004:
        """停止を要求されたセッションのフレームの中で、要求の後に開かれたサブセッションは、開いた時点で停止を要求された状態でなければならない。"""

        title @= "Sub-sessions opened after a stop"
        level @= MUST

    class ASTOP_005:
        """`stop()` はコルーチンではなく、フレームの終了や停止コールバックの完了を待たずに戻る。どのスレッドから呼んでもよい。二度以上呼んでも、一度呼んだ場合と同じ状態になる。停止の要求は取り消せない。"""

        title @= "Stop is a thread-safe request"
        level @= MUST
        related @= (LIMITS_SPEC.ALIMIT_008,)

    class ASTOP_006:
        """`AsyncContext.stopping` は、そのフレームのセッションに停止が要求されていれば `True` を返す。キャンセルを捕まえたルーティンが、それが停止の要求によるものかを確かめるのに使う。"""

        title @= "Observing the stop request"
        level @= MUST

    class ASTOP_007:
        """非同期版には、同期版の `wait_stop()` に当たるものを設けない。停止はキャンセルとしてどの待機点にも届くので、停止だけを待つ必要がないためである。"""

        title @= "No wait_stop in the async API"
        level @= INFORMATIVE

    class ASTOP_008:
        """ルーティンは `asyncio.CancelledError` を握りつぶすべきではない。後始末のために捕まえる場合も、後始末の後で再送出するか、値を返して終わるべきである。捕まえたまま処理を続けると、そのフレームは stuck frame になりうる。"""

        title @= "Writing cancellable routines"
        level @= SHOULD
        related @= (FRAME_SPEC.AFRAME_004, LIMITS_SPEC.ALIMIT_003)

    class ASTOP_009:
        """セッション自身が停止を要求するのは、`async with` ブロック内で例外が起きた場合(所有タスク自身のキャンセルを含む)と、終了時の待機の後に stuck frame が残った場合だけである。"""

        title @= "Implicit stop requests"
        level @= MUST
        related @= (SESSION_SPEC.ASESSION_010,)

    class ASTOP_010:
        """`AsyncContext.on_stop(callback)` は、引数を取らない同期の呼び出し可能オブジェクトを、そのフレームの停止コールバックとして登録し、取り消し用の `gpframe.aio.StopHandle` を返す。主な用途は、キャンセルでは止まらない処理(`asyncio.to_thread()` で動かしているブロッキング処理など)の止め方を登録することである。"""

        title @= "Registering a stop callback"
        level @= INFORMATIVE
        related @= (LIMITS_SPEC.ALIMIT_006,)

    class ASTOP_011:
        """コルーチン関数や、呼ぶとコルーチンを返すものは停止コールバックとして登録できない。登録時に `TypeError` を送出する。停止コールバックは同期で短く終わるものに限る。"""

        title @= "Stop callbacks are synchronous"
        level @= MUST

    class ASTOP_012:
        """停止コールバックは、フレームのセッションに停止が要求されたときに、要求の経路を問わず呼ばれなければならない。一つの登録が呼ばれるのは多くても一度である。"""

        title @= "When stop callbacks run"
        level @= MUST

    class ASTOP_013:
        """停止コールバックは、セッションのループのスレッドで、登録した順に呼ばれなければならない。さらに、そのフレームへのキャンセルがルーティンに届くより前に呼ばれる。ルーティンが後始末を始める時点で、止め方の通知が済んでいるようにするためである。"""

        title @= "Where and when stop callbacks run"
        level @= MUST

    class ASTOP_014:
        """停止がすでに要求されているときに登録された停止コールバックは、登録の後、ループが次に動いたときに呼ばれなければならない。この場合、キャンセルはすでにルーティンに届いているので、ASTOP_013 の「キャンセルより前に呼ぶ」という順序は成り立たない。"""

        title @= "Registering after a stop request"
        level @= MUST

    class ASTOP_015:
        """フレームのルーティンが終わった後は、そのフレームのまだ呼ばれていない停止コールバックを呼んではならない。"""

        title @= "Callbacks end with the routine"
        level @= MUST_NOT

    class ASTOP_016:
        """`StopHandle.cancel()` を呼んだ後は、その停止コールバックを呼んではならない。取り消した登録はフレームから取り除き、コールバックへの参照を残してはならない。登録と取り消しを長く動くフレームの中で繰り返しても、登録が溜まらないためである。すでに呼ばれた後や、フレームが終了した後の `cancel()` は何もしない。"""

        title @= "Cancelling a registration"
        level @= MUST

    class ASTOP_017:
        """停止コールバックが例外を送出した場合、その例外を `AsyncFrame.stop_errors` に記録し、フレームを broken にしなければならない。そのフレームの残りの停止コールバックと、フレームのキャンセルは、引き続き行う。"""

        title @= "Errors in stop callbacks"
        level @= MUST
        related @= (FRAME_SPEC.AFRAME_003,)

    class ASTOP_018:
        """停止コールバックはループのスレッドで呼ばれるので、ブロックしてはならない。ブロックすると、ALIMIT_002 によりすべての保証が失われる。"""

        title @= "Stop callbacks must not block"
        level @= MUST_NOT
        condition @= "停止コールバックを書くとき。"
        related @= (LIMITS_SPEC.ALIMIT_001, LIMITS_SPEC.ALIMIT_002)

    class ASTOP_019:
        """`AsyncSession.stop()` は、セッションの状態によらず、`async with` で開く前でも閉じた後でも呼べなければならない。開く前に呼んだ場合、セッションは開いた時点で停止を要求された状態になり、その中の `spawn()` は stopped のフレームを返す。別のスレッドからルートのセッションを止めるには、同期版の STOP_020 と同じく、先に作ったセッションの参照を渡しておく。"""

        title @= "Stopping a session in any state"
        level @= MUST
        related @= (SESSION_SPEC.ASESSION_005, FRAME_SPEC.AFRAME_015)
