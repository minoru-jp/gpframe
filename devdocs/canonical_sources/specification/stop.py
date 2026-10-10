"""協調的な停止と停止コールバックに関する仕様。"""

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

from devdocs.canonical_sources.specification.frame import (
    SPECIFICATION_PART as FRAME_SPEC,
)
from devdocs.canonical_sources.specification.session import (
    SPECIFICATION_PART as SESSION_SPEC,
)


@summary("停止の要求、停止の伝わり方、停止コールバックに関する規則。")
@canonical_source(
    "Stop", filename="stop.md", order=20, merge_policy="local", heading="identity"
)
class SPECIFICATION_PART:
    """停止の要求、停止の伝わり方、停止コールバックに関する規則。"""

    class STOP_001:
        """停止はすべて協調的である。gpframe はフレームに停止を要求するだけで、スレッドを強制的に止める手段は提供しない。要求に応えて止まるかどうかはルーティンに委ねられ、止まらなかったフレームは stuck frame として報告される。"""

        title @= "Cooperative stop"
        level @= INFORMATIVE
        related @= (SESSION_SPEC.SESSION_010,)

    class STOP_002:
        """`Session.stop()` は、そのセッションのすべてのフレームと、それらのフレームの中で開かれているサブセッションに停止を要求しなければならない。サブセッションへの要求は、さらにその中のサブセッションへ再帰的に伝わる。"""

        title @= "Stop propagates downward"
        level @= MUST

    class STOP_003:
        """停止を要求されたセッションのフレームの中で、要求の後に開かれたサブセッションは、開いた時点で停止を要求された状態でなければならない。"""

        title @= "Sub-sessions opened after a stop"
        level @= MUST

    class STOP_004:
        """`Session.stop()` は、フレームの終了や停止コールバックの完了を待たずに戻らなければならない。二度以上呼んでも、一度呼んだ場合と同じ状態になる。"""

        title @= "Stop is a request"
        level @= MUST

    class STOP_005:
        """停止の要求は取り消せない。一度停止を要求されたセッションが、要求されていない状態に戻ることはない。"""

        title @= "Stop cannot be withdrawn"
        level @= MUST

    class STOP_006:
        """`Context.stopping` は、そのフレームのセッションに停止が要求されていれば `True` を返さなければならない。"""

        title @= "Observing the stop request"
        level @= MUST

    class STOP_007:
        """`Context.wait_stop(timeout)` は、停止が要求されるまで最大 `timeout` 秒待つ。停止が要求されれば、`timeout` を待たずに `True` を返し、時間切れなら `False` を返さなければならない。すでに要求されていれば、すぐに `True` を返す。"""

        title @= "Waiting for a stop request"
        level @= MUST

    class STOP_008:
        """ルーティンは、繰り返し処理の条件に `Context.stopping` を使い、待機には `time.sleep()` ではなく `Context.wait_stop()` を使うべきである。"""

        title @= "Writing stoppable routines"
        level @= SHOULD

    class STOP_009:
        """セッション自身が停止を要求するのは、`with` ブロック内で例外が起きた場合と、終了時の待機の後に stuck frame が残った場合だけである。"""

        title @= "Implicit stop requests"
        level @= MUST
        related @= (SESSION_SPEC.SESSION_009,)

    class STOP_010:
        """
        `Context.on_stop(callback)` は、引数を取らない呼び出し可能オブジェクトを、そのフレームの停止コールバックとして登録し、登録を取り消すためのハンドル(`StopHandle`)を返す。

        停止コールバックは、`ctx.stopping` を確認できない処理を止めるためのものである。たとえばブロックしている `serve_forever()` を、`server.shutdown` を登録して止める。
        """

        title @= "Registering a stop callback"
        level @= INFORMATIVE

    class STOP_011:
        """停止コールバックは、フレームのセッションに停止が要求されたときに呼ばれなければならない。要求の経路(`stop()`、親からの伝播、セッション自身による要求)は問わない。一つの登録が呼ばれるのは多くても一度である(要求の伝わり方は STOP_002 と STOP_009 による)。"""

        title @= "When stop callbacks run"
        level @= MUST

    class STOP_012:
        """停止がすでに要求されているときに登録された停止コールバックは、登録の直後に、要求があったときと同じ方法で呼ばれなければならない。確認と登録の間に要求が来ても取りこぼさないためである。"""

        title @= "Registering after a stop request"
        level @= MUST

    class STOP_013:
        """停止コールバックは、停止を要求したスレッドでもフレームのスレッドでもない、別のスレッドで呼ばれなければならない。一つのフレームの停止コールバックは、登録した順に一つずつ呼ばれる。異なるフレームの間の呼び出し順は定めない。STOP_004 のとおり、`stop()` はコールバックの完了を待たない。"""

        title @= "Where stop callbacks run"
        level @= MUST

    class STOP_014:
        """フレームのルーティンが戻った後は、そのフレームのまだ呼ばれていない停止コールバックを呼んではならない。止めるべき処理がもう存在しないためである。"""

        title @= "Callbacks end with the routine"
        level @= MUST_NOT

    class STOP_015:
        """停止コールバックの呼び出し中にルーティンが戻った場合、フレームは、そのコールバックが戻るまで終了してはならない。"""

        title @= "A frame waits for a running callback"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_001,)

    class STOP_016:
        """`StopHandle.cancel()` を呼んだ後は、その停止コールバックを呼んではならない。取り消した登録はフレームから取り除き、コールバックへの参照を残してはならない。登録と取り消しを長く動くフレームの中で繰り返しても、登録が溜まらないためである(`Channel.get()` は待つたびにこれを行う)。すでに呼ばれた後や、フレームが終了した後の `cancel()` は何もしない。"""

        title @= "Cancelling a registration"
        level @= MUST

    class STOP_017:
        """停止コールバックが例外を送出した場合、その例外を `Frame.stop_errors` に記録し、フレームを broken frame にしなければならない。そのフレームの残りの停止コールバックは、引き続き呼ばれる。"""

        title @= "Errors in stop callbacks"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_001,)

    class STOP_018:
        """停止コールバックは短く終わり、ブロックし続けるべきではない。戻らないコールバックは、STOP_015 によってフレームを stuck frame にする。"""

        title @= "Keeping callbacks short"
        level @= SHOULD
        condition @= "停止コールバックを書くとき。"

    class STOP_019:
        """`Session.stop()` は、セッションの状態によらず、開く前でも閉じた後でも呼べなければならない。開く前に呼んだ場合、セッションは開いた時点で停止を要求された状態になり、その中の `spawn()` は stopped のフレームを返す。"""

        title @= "Stopping a session in any state"
        level @= MUST
        related @= (SESSION_SPEC.SESSION_004, FRAME_SPEC.FRAME_012)

    class STOP_020:
        """
        ルートのセッションを、`with` を実行しているスレッドとは別のスレッド(シグナルの処理、GUI のイベント、ほかのフレームなど)から止めるには、セッションを `with` の前に作って参照を渡しておき、その `stop()` を呼ぶ。STOP_019 により、`with` に入る前や起動の途中で呼ばれても取りこぼさない。

        ```python
        app = gpframe.session(timeout=5)  # 先に作っておく


        def run() -> None:
            with app:
                app.spawn(worker)
                ...


        # 別のスレッドから
        app.stop()
        ```
        """

        title @= "Stopping a root session from another thread"
        level @= INFORMATIVE
