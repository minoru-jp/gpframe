"""gpframe.aio(非同期版)の契約。

Specification の非同期版のうち、テストで守る約束だけを置く。各条項は根拠となる
規則を `source` で指す。「制約と限界」に書いた原理的な限界(ループのブロックなど)は
約束ではないので、契約にしない。
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

from contract.ports.aio_surface import (
    AsyncContext,
    AsyncFrame,
    AsyncSession,
    LoopMonitor,
    StopHandle,
)

S = "specification_aio/session.md#"
F = "specification_aio/frame.md#"
T = "specification_aio/stop.md#"
W = "specification_aio/waiting.md#"
L = "specification_aio/limits.md#"
H = "specification_aio/health.md#"


class AsyncSessionContract:
    subject @= AsyncSession

    class UnacknowledgedFailuresSurface:
        """承認されていない broken のフレームは、ルートのセッションの終了時に必ず警告か例外として表に出る。"""

        kind @= INV
        source @= S + "ASESSION_013"

    class StoppedFramesAreNotFailures:
        """停止の要求で stopped になったフレームについて、ルートのセッションは警告も例外も出さない。"""

        kind @= INV
        source @= S + "ASESSION_013"
        source @= F + "AFRAME_002"

    class EscalatedFailuresRaise:
        """`escalate()` されたフレームがあると、ルートのセッションの終了時に、その例外を持つ `AsyncSessionFailed` を送出する。"""

        kind @= INV
        source @= S + "ASESSION_013"
        source @= S + "ASESSION_014"

    class KeepsOnlyWhatJudgementNeeds:
        """succeeded・stopped・`ignore()` 済みのフレームと、終わったフレームのルーティンと引数は、セッションからもフレームからも参照されない。"""

        kind @= INV
        source @= S + "ASESSION_021"
        source @= F + "AFRAME_016"

    class OwnerCancellationTakesPrecedence:
        """所有タスク自身がキャンセルされた場合、終了時には `CancelledError` を再送出し、`AsyncSessionFailed` に置き換えず、失敗は警告で報告する。"""

        kind @= INV
        source @= S + "ASESSION_016"
        rationale @= "asyncio のキャンセルの伝わり方を壊さない。"

    class ExitWaitIsBounded:
        """終了時の待機は `timeout` 秒で打ち切る。止まらなかったフレームは警告で報告し、停止を要求して切り離す。"""

        kind @= INV
        source @= S + "ASESSION_010"
        source @= S + "ASESSION_012"

    class CancellationWhileWaitingAtExit:
        """終了時の待機の最中に所有タスクがキャンセルされたら、待機を打ち切り、後の処理を済ませてキャンセルを伝える。"""

        kind @= INV
        source @= S + "ASESSION_011"

    class SubSessionReportsToOwner:
        """サブセッションは終了時に警告も独自の例外も出さず、不完全だった場合は報告を親フレームに付ける。停止によるキャンセルは不完全の原因にしない。"""

        kind @= INV
        source @= S + "ASESSION_017"
        source @= S + "ASESSION_018"

    class StopReachesSubSessions:
        """停止の要求は、フレームの中で開かれたサブセッションに伝わる。要求の後に開かれたサブセッションにも伝わる。"""

        kind @= INV
        source @= T + "ASTOP_002"
        source @= T + "ASTOP_004"

    class spawn:
        member @= AsyncSession.spawn

        class SessionIsOpen:
            """開いているセッションでだけ、フレームを作れる。"""

            kind @= PRE
            source @= S + "ASESSION_005"
            on_violation @= REJECTED

        class SpawnAfterStopIsStopped:
            """停止を要求された後は、タスクを作らずに stopped のフレームを返す。そのフレームは失敗ではない。"""

            kind @= POST
            source @= S + "ASESSION_005"
            source @= F + "AFRAME_015"

        class RoutineIsCoroutineFunction:
            """ルーティンはコルーチン関数でなければならない。"""

            kind @= PRE
            source @= S + "ASESSION_006"
            on_violation @= REJECTED

        class CalledFromOwnLoop:
            """セッションが属するループのスレッドから呼ばなければならない。"""

            kind @= PRE
            source @= L + "ALIMIT_007"
            on_violation @= REJECTED

    class stop:
        member @= AsyncSession.stop

        class CancelsEachFrameOnce:
            """実行中のすべてのフレームのタスクをキャンセルする。一つのフレームをキャンセルするのは一度だけである。"""

            kind @= POST
            source @= T + "ASTOP_002"
            source @= T + "ASTOP_003"

        class SafeFromAnyThread:
            """どのスレッドから呼んでもよく、別のスレッドからの要求は、ループが次に動いたときに届く。"""

            kind @= POST
            source @= T + "ASTOP_005"
            source @= L + "ALIMIT_008"

        class WorksInAnyState:
            """開く前に呼んでもよく、そのセッションは開いた時点で停止を要求された状態になる。"""

            kind @= POST
            source @= T + "ASTOP_019"

    class wait_broken:
        member @= AsyncSession.wait_broken

        class ReturnsOnFirstFailure:
            """未承認の broken のフレームが現れた時点で、ほかのフレームの終了を待たずに、その時点の `broken()` を返す。"""

            kind @= POST
            source @= W + "AWAIT_003"
            source @= W + "AWAIT_004"

        class WaiterCancellationDoesNotStopFrames:
            """待っているタスクがキャンセルされても、フレームはキャンセルも停止もされない。"""

            kind @= POST
            source @= W + "AWAIT_006"

        class IdleWaitsForFailureOrStop:
            """`idle=True` では、実行中のフレームがなくても戻らず、失敗、停止の要求、時間切れのどれかで戻る。"""

            kind @= POST
            source @= W + "AWAIT_008"


class AsyncFrameContract:
    subject @= AsyncFrame

    class StopCancellationMeansStopped:
        """停止の要求によるキャンセルで終わったフレームは、broken ではなく stopped になる。"""

        kind @= INV
        source @= F + "AFRAME_002"

    class ForeignCancellationBreaks:
        """gpframe が要求していないキャンセルで終わったフレームは broken になる。"""

        kind @= INV
        source @= F + "AFRAME_003"

    class ReturningAfterCancellationSucceeds:
        """キャンセルを捕まえて値を返したフレームは succeeded になる。"""

        kind @= INV
        source @= F + "AFRAME_004"

    class CallbackErrorsBreakFrame:
        """停止コールバックが例外を送出すると、その例外が `stop_errors` に記録され、フレームは broken になる。"""

        kind @= INV
        source @= T + "ASTOP_017"
        source @= F + "AFRAME_003"

    class InterruptsAreNotSwallowed:
        """ルーティンが `KeyboardInterrupt` か `SystemExit` で終わると、フレームは broken として記録され、その例外はループの外へ伝わる。"""

        kind @= INV
        source @= F + "AFRAME_014"
        rationale @= "中断の要求を握りつぶすと、プログラムを止められなくなる。"

    class result:
        member @= AsyncFrame.result

        class ReportsOutcome:
            """終わり方に応じて、値を返すか、stopped なら `FrameStoppedError` を、例外なら その例外を送出する。時間内に終わらなければ `TimeoutError` を送出する。"""

            kind @= POST
            source @= F + "AFRAME_005"

        class DoesNotLeakCancellation:
            """フレームの `CancelledError` を呼び出し側にそのまま送出せず、`FrameAbortedError` で包む。"""

            kind @= POST
            source @= F + "AFRAME_006"

        class WaiterCancellationDoesNotCancelFrame:
            """`result()` を待っている側がキャンセルされても、フレームはキャンセルされない。"""

            kind @= POST
            source @= F + "AFRAME_007"

    class wait:
        member @= AsyncFrame.wait

        class WaitsWithoutRaising:
            """終わるまで待って `True` を返し、時間切れなら `False` を返す。終わり方によらず例外を送出せず、承認にもならない。"""

            kind @= POST
            source @= F + "AFRAME_017"

    class ignore:
        member @= AsyncFrame.ignore

        class OnlyUnacknowledgedFailures:
            """broken のフレームのうち、まだ承認されていないものだけを承認できる。"""

            kind @= PRE
            source @= F + "AFRAME_012"
            on_violation @= REJECTED

    class escalate:
        member @= AsyncFrame.escalate

        class OnlyUnacknowledgedFailures:
            """broken のフレームのうち、まだ承認されていないものだけを承認できる。"""

            kind @= PRE
            source @= F + "AFRAME_012"
            on_violation @= REJECTED


class AsyncContextContract:
    subject @= AsyncContext

    class on_stop:
        member @= AsyncContext.on_stop

        class CallbackIsSynchronous:
            """停止コールバックは同期の呼び出し可能オブジェクトでなければならない。"""

            kind @= PRE
            source @= T + "ASTOP_011"
            on_violation @= REJECTED

        class CalledBeforeCancellation:
            """停止が要求されると、停止コールバックはループのスレッドで、登録した順に、キャンセルがルーティンに届く前に一度だけ呼ばれる。"""

            kind @= POST
            source @= T + "ASTOP_012"
            source @= T + "ASTOP_013"

        class RegisteredAfterStopIsCalled:
            """停止の後に登録した停止コールバックも呼ばれる。"""

            kind @= POST
            source @= T + "ASTOP_014"


class AsyncStopHandleContract:
    subject @= StopHandle

    class cancel:
        member @= StopHandle.cancel

        class PreventsLaterCall:
            """`cancel()` の後、その停止コールバックは呼ばれない。"""

            kind @= POST
            source @= T + "ASTOP_016"

        class ReleasesRegistration:
            """取り消した登録はフレームに残らず、登録と取り消しを繰り返しても溜まらない。"""

            kind @= POST
            source @= T + "ASTOP_016"


class LoopMonitorContract:
    subject @= LoopMonitor

    class ReportsEachStallOnce:
        """一続きの停滞につき、停滞の検出を一度だけ、ループのスレッドのスタックとともに報告する。"""

        kind @= INV
        source @= H + "AHEALTH_008"
        source @= H + "AHEALTH_009"

    class ReportsRecovery:
        """停滞から回復したら、停滞していた時間とともに回復を一度だけ報告する。"""

        kind @= INV
        source @= H + "AHEALTH_008"
        source @= H + "AHEALTH_011"

    class WarnsWithoutCallback:
        """`on_stall` がなければ、停滞を `HealthWarning` で報告する。"""

        kind @= INV
        source @= H + "AHEALTH_009"

    class CallbacksRunOnWatcherThread:
        """`on_stall` と `on_recover` は、ループのスレッドではなく監視スレッドで呼ばれる。"""

        kind @= INV
        source @= H + "AHEALTH_012"

    class CallbackErrorsAreRecorded:
        """コールバックの例外は `errors` に記録され、`HealthWarning` で報告され、監視は続く。"""

        kind @= INV
        source @= H + "AHEALTH_014"

    class NoCallbacksAfterClose:
        """`async with` を抜けた後に、コールバックが呼ばれることはない。"""

        kind @= INV
        source @= H + "AHEALTH_016"

    class StateIsReadableFromAnyThread:
        """`stalled` と `lag` は、どのスレッドからも読め、停滞中は停滞していることを示す。"""

        kind @= INV
        source @= H + "AHEALTH_015"
