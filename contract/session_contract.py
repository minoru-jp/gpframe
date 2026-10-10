"""セッション、フレーム、コンテキストの契約。

失敗を握りつぶさないこと、止まらなかったものを報告すること、停止が
伝わること。gpframe が利用者に約束するのはこの三つで、ここにはそれを
支える振る舞いだけを置く。
"""

from shikumi_contrace import (
    INV,
    POST,
    PRE,
    REJECTED,
    depends_on,
    kind,
    member,
    on_violation,
    rationale,
    source,
    subject,
)

from contract.ports.surface import Context, Frame, Session, StopHandle


class SessionContract:
    subject @= Session

    class UnacknowledgedFailuresSurface:
        """承認されていない broken frame は、ルートのセッションの終了時に必ず警告か例外として表に出る。"""

        kind @= INV
        source @= "specification/session.md#SESSION_011"
        rationale @= "失敗を黙って捨てないことが、このフレームワークの存在理由である。"

    class IgnoredFailuresAreSilent:
        """`ignore()` されたフレームは、ルートのセッションの終了時に警告も例外も起こさない。"""

        kind @= INV
        source @= "specification/session.md#SESSION_011"

    class EscalatedFailuresRaise:
        """`escalate()` されたフレームがあると、ルートのセッションの終了時に、その例外を持つ `SessionFailed` を送出する。"""

        kind @= INV
        source @= "specification/session.md#SESSION_011"
        source @= "specification/session.md#SESSION_012"

    class StrictRaisesUnmarkedFailures:
        """`strict=True` のルートのセッションでは、マークのない broken frame も警告ではなく `SessionFailed` に含める。"""

        kind @= INV
        source @= "specification/session.md#SESSION_011"

    class ExitWaitIsBounded:
        """セッションの終了時の待機は `timeout` 秒で打ち切る。止まらなかったフレームは stuck frame として報告し、停止を要求する。"""

        kind @= INV
        source @= "specification/session.md#SESSION_009"
        source @= "specification/session.md#SESSION_010"
        rationale @= (
            "スレッドは外から止められない。待ち続けず、止まらなかった事実を伝える。"
        )

    class BodyErrorRequestsStop:
        """`with` ブロック内で例外が起きると、終了の待機より先に停止を要求する。"""

        kind @= INV
        source @= "specification/session.md#SESSION_009"
        source @= "specification/stop.md#STOP_009"

    class StopReachesSubSessions:
        """停止の要求は、フレームの中で開かれたサブセッションに伝わる。要求の後に開かれたサブセッションにも伝わる。"""

        kind @= INV
        source @= "specification/stop.md#STOP_002"
        source @= "specification/stop.md#STOP_003"

    class KeepsOnlyWhatJudgementNeeds:
        """succeeded・stopped・`ignore()` 済みのフレームと、終わったフレームのルーティンと引数は、セッションからもフレームからも参照されない。"""

        kind @= INV
        source @= "specification/session.md#SESSION_019"
        source @= "specification/frame.md#FRAME_013"
        rationale @= (
            "要求ごとにフレームを起動する長寿命のセッションで、メモリが溜まり続けない。"
        )

    class SubSessionReportsToOwner:
        """サブセッションは終了時に警告も独自の例外も出さない。不完全だった場合は、報告を親フレームに付ける。"""

        kind @= INV
        source @= "specification/session.md#SESSION_015"
        source @= "specification/session.md#SESSION_016"
        rationale @= "最終的な判断はルートのセッションだけが行う。"

    class spawn:
        member @= Session.spawn

        class SessionIsOpen:
            """開いているセッションでだけ、フレームを作れる。"""

            kind @= PRE
            source @= "specification/session.md#SESSION_004"
            on_violation @= REJECTED
            rationale @= "終了の判定から漏れるフレームを作らない。"

        class SpawnAfterStopIsStopped:
            """停止を要求された後は、ルーティンを呼ばずに stopped のフレームを返す。そのフレームは失敗ではなく、承認も判定も求めない。"""

            kind @= POST
            source @= "specification/session.md#SESSION_004"
            source @= "specification/frame.md#FRAME_012"
            rationale @= "止まる途中で始めようとした仕事は失敗ではない。停止との競合を例外にしない。"

    class broken:
        member @= Session.broken

        class ReturnsOnlyUnacknowledged:
            """失敗して終わり、まだ承認されていないフレームだけを、起動した順に返す。"""

            kind @= POST
            source @= "specification/session.md#SESSION_008"

    class stop:
        member @= Session.stop

        class DoesNotWaitForCallbacks:
            """`stop()` は、停止コールバックの完了やフレームの終了を待たずに戻る。"""

            kind @= POST
            source @= "specification/stop.md#STOP_004"
            source @= "specification/stop.md#STOP_013"
            rationale @= "フレーム自身や停止コールバックの中から stop() を呼んでもデッドロックしない。"

        class WorksInAnyState:
            """開く前に呼んでもよく、そのセッションは開いた時点で停止を要求された状態になる。"""

            kind @= POST
            source @= "specification/stop.md#STOP_019"
            rationale @= "別のスレッドから、起動の途中のルートのセッションを取りこぼしなく止められる。"

    class wait_broken:
        member @= Session.wait_broken

        class ReturnsOnFirstFailure:
            """未承認の broken frame が現れた時点で、ほかのフレームの終了を待たずに、その時点の `broken()` を返す。"""

            kind @= POST
            source @= "specification/waiting.md#WAIT_003"
            source @= "specification/waiting.md#WAIT_004"

        class ReturnsEmptyWithoutFailure:
            """失敗がないまま実行中のフレームがなくなるか、`timeout` が経つと、空の並びを返す。"""

            kind @= POST
            source @= "specification/waiting.md#WAIT_003"
            source @= "specification/waiting.md#WAIT_004"

        class DoesNotAcknowledge:
            """`wait_broken()` が返したフレームは承認されたことにならず、承認されるまで返され続ける。"""

            kind @= POST
            source @= "specification/waiting.md#WAIT_005"

        class IdleWaitsForFailureOrStop:
            """`idle=True` では、実行中のフレームがなくても戻らず、失敗、停止の要求、時間切れのどれかで戻る。"""

            kind @= POST
            source @= "specification/waiting.md#WAIT_007"
            rationale @= (
                "フレームが増減するセッションの失敗を、ポーリングなしで待ち続けられる。"
            )


class FrameContract:
    subject @= Frame
    # 不完全なサブセッションの報告(SubSessionReportsToOwner)を前提にする。
    depends_on @= SessionContract

    class IncompleteSessionBreaksFrame:
        """配下のセッションが不完全だったフレームは、ルーティンが値を返していても broken frame になる。"""

        kind @= INV
        source @= "specification/frame.md#FRAME_002"

    class NoCallbacksAfterRoutineReturns:
        """ルーティンが戻った後は、まだ呼ばれていない停止コールバックを呼ばない。"""

        kind @= INV
        source @= "specification/stop.md#STOP_014"

    class WaitsForRunningCallback:
        """停止コールバックの呼び出し中にルーティンが戻っても、そのコールバックが戻るまでフレームは終了しない。"""

        kind @= INV
        source @= "specification/stop.md#STOP_015"

    class CallbackErrorsBreakFrame:
        """停止コールバックが例外を送出すると、その例外が `stop_errors` に記録され、フレームは broken frame になる。"""

        kind @= INV
        source @= "specification/stop.md#STOP_017"
        source @= "specification/frame.md#FRAME_001"

    class result:
        member @= Frame.result

        class WaitsForCompletion:
            """フレームが終わるまで待ち、戻り値を返すか、ルーティンの例外を再送出する。`timeout` 内に終わらなければ `TimeoutError` を送出する。"""

            kind @= POST
            source @= "specification/frame.md#FRAME_003"

        class DoesNotAcknowledge:
            """`result()` を呼んでも失敗の承認にはならない。"""

            kind @= POST
            source @= "specification/frame.md#FRAME_005"

    class wait:
        member @= Frame.wait

        class WaitsWithoutRaising:
            """終わるまで待って `True` を返し、時間切れなら `False` を返す。終わり方によらず例外を送出せず、承認にもならない。"""

            kind @= POST
            source @= "specification/frame.md#FRAME_014"

    class ignore:
        member @= Frame.ignore

        class OnlyUnacknowledgedFailures:
            """失敗して終わり、まだ承認されていないフレームだけを承認できる。"""

            kind @= PRE
            source @= "specification/frame.md#FRAME_008"
            source @= "specification/frame.md#FRAME_009"
            on_violation @= REJECTED

    class escalate:
        member @= Frame.escalate

        class OnlyUnacknowledgedFailures:
            """失敗して終わり、まだ承認されていないフレームだけを承認できる。"""

            kind @= PRE
            source @= "specification/frame.md#FRAME_008"
            source @= "specification/frame.md#FRAME_009"
            on_violation @= REJECTED


class ContextContract:
    subject @= Context

    class wait_stop:
        member @= Context.wait_stop

        class WakesOnStop:
            """停止が要求されると、`timeout` を待たずに `True` を返す。時間切れなら `False` を返す。"""

            kind @= POST
            source @= "specification/stop.md#STOP_007"

    class on_stop:
        member @= Context.on_stop

        class CalledOnceOnStop:
            """停止が要求されると、登録したコールバックは、停止を要求したスレッドともフレームのスレッドとも別のスレッドで、一度だけ呼ばれる。"""

            kind @= POST
            source @= "specification/stop.md#STOP_011"
            source @= "specification/stop.md#STOP_013"

        class CalledInRegistrationOrder:
            """一つのフレームの停止コールバックは、登録した順に一つずつ呼ばれる。"""

            kind @= POST
            source @= "specification/stop.md#STOP_013"

        class RegisteredAfterStopIsCalled:
            """停止の後に登録したコールバックも呼ばれる。"""

            kind @= POST
            source @= "specification/stop.md#STOP_012"


class StopHandleContract:
    subject @= StopHandle

    class cancel:
        member @= StopHandle.cancel

        class PreventsLaterCall:
            """`cancel()` の後、その停止コールバックは呼ばれない。すでに呼ばれた後の `cancel()` は何もしない。"""

            kind @= POST
            source @= "specification/stop.md#STOP_016"

        class ReleasesRegistration:
            """取り消した登録はフレームに残らず、登録と取り消しを繰り返しても溜まらない。"""

            kind @= POST
            source @= "specification/stop.md#STOP_016"
            rationale @= "Channel.get() は待つたびに登録と取り消しを行う。"
