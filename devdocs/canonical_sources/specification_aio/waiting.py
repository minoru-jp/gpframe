"""非同期版の待ち方に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    MUST_NOT,
    level,
    related,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title

from devdocs.canonical_sources.specification_aio.frame import (
    SPECIFICATION_PART as FRAME_SPEC,
)
from devdocs.canonical_sources.specification_aio.session import (
    SPECIFICATION_PART as SESSION_SPEC,
)


@summary(
    "非同期版で、すべてのフレームの終了と最初の失敗を、ループを止めずに待つ方法に関する規則。"
)
@canonical_source(
    "Async waiting",
    filename="waiting.md",
    order=40,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """非同期版で、すべてのフレームの終了と最初の失敗を、ループを止めずに待つ方法に関する規則。"""

    class AWAIT_001:
        """`AsyncSession.running()` はコルーチンではなく、まだ終了していないフレームがあれば `True` を返す。"""

        title @= "Running frames"
        level @= MUST

    class AWAIT_002:
        """`await AsyncSession.wait(timeout)` は、ループを止めずに、すべてのフレームが終了するまで最大 `timeout` 秒待ち、時間内にすべて終了すれば `True`、そうでなければ `False` を返す。待っている間に起動されたフレームの終了も待つ。"""

        title @= "Waiting for all frames"
        level @= MUST

    class AWAIT_003:
        """
        `await AsyncSession.wait_broken(timeout, *, idle=False)` は、ループを止めずに、次のどれかが成り立つまで最大 `timeout` 秒待たなければならない。呼び出した時点ですでに成り立っていれば、すぐに戻る。

        - まだ承認されていない broken のフレームがある
        - 実行中のフレームがない(`idle=False` のとき。`idle=True` の場合は AWAIT_008)
        - `timeout` 秒が経った
        """

        title @= "Waiting for the first failure"
        level @= MUST
        related @= (FRAME_SPEC.AFRAME_003,)

    class AWAIT_004:
        """`wait_broken()` は、戻る時点の `broken()` と同じ並びを返す。空なら失敗以外の理由で戻ったことを表し、どちらの理由かは `running()` で区別できる。stopped のフレームは失敗として扱わない。"""

        title @= "Result of wait_broken"
        level @= MUST
        related @= (SESSION_SPEC.ASESSION_009,)

    class AWAIT_005:
        """`wait_broken()` が返したフレームを、承認されたものとして扱ってはならない。"""

        title @= "Waiting does not acknowledge"
        level @= MUST_NOT
        related @= (FRAME_SPEC.AFRAME_011,)

    class AWAIT_006:
        """`wait()` や `wait_broken()` で待っているタスクがキャンセルされた場合、待機はその `asyncio.CancelledError` で終わる。フレームはキャンセルも停止もされてはならない。"""

        title @= "Cancelling a waiter does not stop frames"
        level @= MUST_NOT
        related @= (FRAME_SPEC.AFRAME_007,)

    class AWAIT_007:
        """
        長く動き続ける部品を連結し、どれか一つが失敗したら全体を止める処理は、次の形で書ける。同期版と違い、停止はキャンセルとして各部品の待機点に届く。

        ```python
        async with gpframe.aio.session(timeout=10) as s:
            for component in components:
                s.spawn(component)
            if failed := await s.wait_broken():
                for frame in failed:
                    frame.escalate()
                s.stop()
        ```
        """

        title @= "Supervising long-running components"
        level @= INFORMATIVE

    class AWAIT_008:
        """`await wait_broken(idle=True)` は、実行中のフレームがないことでは戻らず、まだ承認されていない broken のフレームがあるか、セッションに停止が要求されているか、`timeout` 秒が経つまで待たなければならない。同期版の WAIT_007 と同じ。"""

        title @= "Waiting while idle"
        level @= MUST

    class AWAIT_009:
        """
        接続ごとにフレームを起動するサーバーは、`idle=True` で失敗を待ち続け、受け付けの階層で失敗を閉じる。停止はキャンセルとしてこの待機に届く。

        ```python
        while True:
            for frame in await clients.wait_broken(idle=True):
                log(frame)
                frame.ignore()
        ```
        """

        title @= "Supervising a changing set of frames"
        level @= INFORMATIVE
