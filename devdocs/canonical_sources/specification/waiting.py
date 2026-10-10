"""フレームの終了と失敗の待ち方に関する仕様。"""

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
from devdocs.canonical_sources.specification.session import (
    SPECIFICATION_PART as SESSION_SPEC,
)


@summary("すべてのフレームの終了を待つ方法と、最初の失敗を待つ方法に関する規則。")
@canonical_source(
    "Waiting",
    filename="waiting.md",
    order=30,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """すべてのフレームの終了を待つ方法と、最初の失敗を待つ方法に関する規則。"""

    class WAIT_001:
        """`Session.running()` は、まだ終了していないフレームがあれば `True` を返さなければならない。"""

        title @= "Running frames"
        level @= MUST

    class WAIT_002:
        """`Session.wait(timeout)` は、すべてのフレームが終了するまで最大 `timeout` 秒待ち、時間内にすべて終了すれば `True`、そうでなければ `False` を返さなければならない。待っている間に起動されたフレームの終了も待つ。`timeout` が `None` なら、すべて終了するまで待つ。"""

        title @= "Waiting for all frames"
        level @= MUST

    class WAIT_003:
        """
        `Session.wait_broken(timeout, *, idle=False)` は、次のどれかが成り立つまで最大 `timeout` 秒待たなければならない。

        - まだ承認されていない broken frame がある
        - 実行中のフレームがない(`idle=False` のとき。`idle=True` の場合は WAIT_007)
        - `timeout` 秒が経った

        呼び出した時点ですでに成り立っていれば、すぐに戻る。`timeout` が `None` なら、時間切れにはならない。
        """

        title @= "Waiting for the first failure"
        level @= MUST
        related @= (FRAME_SPEC.FRAME_001,)

    class WAIT_004:
        """`wait_broken()` は、戻る時点の `broken()` と同じ並びを返さなければならない。空でなければ失敗によって、空なら終了か時間切れによって戻ったことを表す。この二つは `running()`(WAIT_001)で区別できる。"""

        title @= "Result of wait_broken"
        level @= MUST
        related @= (SESSION_SPEC.SESSION_008,)

    class WAIT_005:
        """`wait_broken()` が返したフレームを、承認されたものとして扱ってはならない。続けて呼んだ `wait_broken()` は、承認されるまで同じフレームを返し続ける。"""

        title @= "Waiting does not acknowledge"
        level @= MUST_NOT
        related @= (FRAME_SPEC.FRAME_005,)

    class WAIT_006:
        """
        長く動き続ける部品を連結し、どれか一つが失敗したら全体を止める処理は、次の形で書ける。

        ```python
        with gpframe.session(timeout=10) as s:
            for component in components:
                s.spawn(component)
            if failed := s.wait_broken():
                for frame in failed:
                    frame.escalate()
                s.stop()
        ```

        失敗した部品だけを起動し直す場合は、`wait_broken()` を繰り返し呼び、承認したうえで同じルーティンを `spawn()` し直す。
        """

        title @= "Supervising long-running components"
        level @= INFORMATIVE

    class WAIT_007:
        """
        `wait_broken(idle=True)` は、実行中のフレームがないことでは戻らず、次のどれかが成り立つまで待たなければならない。

        - まだ承認されていない broken frame がある
        - セッションに停止が要求されている
        - `timeout` 秒が経った

        停止の要求で戻ることで、待ち続けるループを停止で抜けられる。戻り値は WAIT_004 と同じく、戻る時点の `broken()` である。
        """

        title @= "Waiting while idle"
        level @= MUST

    class WAIT_008:
        """
        接続や要求ごとにフレームを起動するサーバーのように、セッションにフレームが増えたり減ったりする場合は、`idle=True` で失敗を待ち続け、一つの階層で失敗を閉じる。`selectors` のループと同じ形である。

        ```python
        while not ctx.stopping:
            for frame in clients.wait_broken(idle=True):
                log(frame)
                frame.ignore()
        ```
        """

        title @= "Supervising a changing set of frames"
        level @= INFORMATIVE
