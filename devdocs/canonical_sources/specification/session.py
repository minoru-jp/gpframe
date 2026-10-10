"""セッションの開閉と終了時の判定に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    MUST_NOT,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification.frame import (
    SPECIFICATION_PART as FRAME_SPEC,
)


@summary("セッションの開閉、フレームの起動、終了時の判定、サブセッションに関する規則。")
@canonical_source(
    "Session",
    filename="session.md",
    order=0,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """セッションの開閉、フレームの起動、終了時の判定、サブセッションに関する規則。"""

    class SESSION_001:
        """ルートのセッションは `gpframe.session(timeout, strict)` で作り、フレームの中のサブセッションは `Context.session(timeout)` で作る。どちらも `with` で開いて使う。"""

        title @= "Creating sessions"
        level @= INFORMATIVE

    class SESSION_002:
        """セッションを `with` で開けるのは一度だけである。二度目に開こうとした場合は `SessionStateError` を送出しなければならない。"""

        title @= "A session is entered once"
        level @= MUST

    class SESSION_003:
        """`timeout` は `None` か 0 以上の数でなければならない。負の数はセッションの作成時に `ValueError` で拒否しなければならない。"""

        title @= "Timeout values"
        level @= MUST

    class SESSION_004:
        """
        `spawn()` は、開いているセッションでだけ使える。

        - 開く前または閉じた後のセッションでは、フレームを作らずに `SessionStateError` を送出しなければならない。終了時の判定から漏れるフレームを作らないためである。
        - 停止を要求された後のセッションでは、ルーティンを呼ばずに stopped のフレームを返さなければならない(FRAME_012)。
        """

        title @= "Spawning needs an open session"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_012,)

    class SESSION_005:
        """`spawn(fn, *args, name=None)` は新しいデーモンスレッドでフレームを起動し、そのスレッドで `fn(context, *args)` を呼ばなければならない。ルーティンへの引数は位置引数だけを渡す。"""

        title @= "Running a routine"
        level @= MUST

    class SESSION_006:
        """ルーティンの呼び出し結果がコルーチンだった場合は、フレームのスレッド内で新しいイベントループを作って最後まで実行し、その結果をルーティンの戻り値としなければならない。"""

        title @= "Coroutine routines"
        level @= MUST

    class SESSION_007:
        """`name` を省略した場合、フレームの名前はルーティンの `__name__`、それがなければルーティンの型名とする。名前はログと報告のためのもので、重複してもよい。"""

        title @= "Frame names"
        level @= MUST

    class SESSION_008:
        """`broken()` は、まだ承認されていない broken frame だけを、起動した順に返さなければならない。実行中のフレーム、succeeded のフレーム、承認済みのフレームを含めてはならない。"""

        title @= "Listing unacknowledged failures"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_001, FRAME_SPEC.FRAME_008)

    class SESSION_009:
        """
        `with` を抜けるとき、セッションは次の順で処理しなければならない。

        1. `with` ブロック内で例外が起きていれば、停止を要求する。
        2. 最大 `timeout` 秒、すべてのフレームの終了を待つ。
        3. 閉じた状態に移り、まだ終わっていないフレームを stuck frame とする。
        4. stuck frame があれば停止を要求する。
        5. ルートのセッションなら終了時の判定を、サブセッションなら親フレームへの報告を行う。
        """

        title @= "Exit procedure"
        level @= MUST

    class SESSION_010:
        """ルートのセッションは、stuck frame があれば、その名前を挙げた `FrameWarning` を出さなければならない。stuck frame のスレッドは止めず、そのまま走らせ続ける。"""

        title @= "Reporting stuck frames"
        level @= MUST

    class SESSION_011:
        """
        ルートのセッションは、終了時の broken frame を承認に応じて次のように扱わなければならない。

        | 承認 | 結果 |
        | --- | --- |
        | `ignore()` 済み | 何もしない |
        | `escalate()` 済み | `SessionFailed` に含めて送出する |
        | 承認なし(`strict=False`) | 名前を挙げた `FrameWarning` を出す |
        | 承認なし(`strict=True`) | `SessionFailed` に含めて送出する |

        承認されていない broken frame を、警告も例外もなしに捨ててはならない。
        """

        title @= "Judgement at the root"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_008,)

    class SESSION_012:
        """
        `SessionFailed` は `ExceptionGroup` であり、送出の対象になったフレームごとに一つの例外を、起動した順に持たなければならない。`frames` 属性は、同じ順に対応するフレームを持つ。各フレームの例外は次の優先順で決める。

        1. ルーティンが `Exception` で終わった場合は、その例外。
        2. ルーティンが `Exception` 以外の `BaseException` で終わった場合は、それを `__cause__` に持つ `FrameAbortedError`。
        3. 停止コールバックが例外を送出した場合は、最初の例外(`Exception` 以外なら 2. と同様に包む)。
        4. それ以外(サブセッションが不完全だった場合)は、報告を持つ `IncompleteSessionError`。

        `escalate(reason)` の `reason` は、メッセージにフレーム名とともに含める。
        """

        title @= "Contents of SessionFailed"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_001, FRAME_SPEC.FRAME_011)

    class SESSION_013:
        """`SessionFailed` を `split()` や `subgroup()` で分けた場合、分けた結果も `SessionFailed` であり、残った例外に対応するフレームだけを `frames` に持たなければならない。"""

        title @= "Splitting SessionFailed"
        level @= MUST

    class SESSION_014:
        """`with` ブロック内の例外と `SessionFailed` の送出が重なった場合は `SessionFailed` を送出し、ブロック内の例外はその `__context__` として残す。`SessionFailed` を送出しない場合は、ブロック内の例外をそのまま再送出する。"""

        title @= "Body errors and SessionFailed"
        level @= MUST

    class SESSION_015:
        """サブセッションは、`with` を抜けるときに警告を出してはならず、独自の例外を送出してはならない。最終的な判断はルートのセッションだけが行う。"""

        title @= "Sub-sessions do not judge"
        level @= MUST_NOT

    class SESSION_016:
        """
        サブセッションは、次のどれかに当てはまる場合に不完全であり、その報告(`SessionReport`)を親フレームに付けなければならない。

        - `ignore()` されていない broken frame がある(`escalate()` 済みのものも含む)
        - stuck frame がある
        - `with` ブロック内で例外が起きた

        報告の `broken`、`stuck`、`errors` は、それぞれ上の三つに対応する。
        """

        title @= "Incomplete sub-sessions"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_002, FRAME_SPEC.FRAME_007)

    class SESSION_017:
        """サブセッションの `with` ブロック内で起きた例外は、報告に記録したうえでそのまま再送出しなければならない。"""

        title @= "Body errors in sub-sessions"
        level @= MUST

    class SESSION_018:
        """ルートで親フレームを `ignore()` した場合、そのフレームの配下で起きた失敗もまとめて許したことになる。配下の失敗だけを個別に送出する手段は提供しない。"""

        title @= "Ignoring a parent forgives its children"
        level @= INFORMATIVE

    class SESSION_019:
        """
        セッションは、終了時の判定と報告に要らなくなったフレームを保持してはならない。次のフレームは、終了した時点(`ignore()` 済みのものは承認した時点)で手放す。

        - succeeded のフレーム
        - stopped のフレーム
        - `ignore()` 済みの broken frame

        実行中のフレーム、承認されていない broken frame、`escalate()` 済みの broken frame は、判定と報告のために保持する。手放したフレームも、ハンドルを持っている側からは変わらず使える。

        要求ごとにフレームを起動するサーバーのように、長く開いたままのセッションで、終わったフレームが溜まり続けないためである。
        """

        title @= "A session keeps only what the judgement needs"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_001, FRAME_SPEC.FRAME_013)
