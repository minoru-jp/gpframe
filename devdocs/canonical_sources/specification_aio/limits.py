"""非同期版の制約と、原理的な限界に関する仕様。"""

from shikumi_devdoc.fields.specification import (
    INFORMATIVE,
    MUST,
    MUST_NOT,
    SHOULD,
    condition,
    level,
)
from shikumi_devdoc.norms.common import canonical_source, summary
from shikumi_devdoc.norms.document import title


@summary(
    "非同期版が守れないものを先に定める。利用者が守るべき制約と、gpframe.aio が原理的に保証できない限界。"
)
@canonical_source(
    "Constraints and limits",
    filename="limits.md",
    order=0,
    merge_policy="local",
    heading="identity",
)
class SPECIFICATION_PART:
    """
    非同期版が守れないものを先に定める。ここに書く制約と限界は、設計の不足ではなく、一つのイベントループの上で協調的に動くという実行モデルから来る原理的なものである。他の文書の規則は、すべてこの文書の制約が守られていることを前提とする。

    限界を黙って抱えるのではなく、表明したうえで、その内側で約束できることを約束する。
    """

    class ALIMIT_001:
        """フレームのルーティンと停止コールバックは、イベントループをブロックしてはならない。ブロッキングする処理は `asyncio.to_thread()` などでループの外へ出す。"""

        title @= "Do not block the loop"
        level @= MUST_NOT

    class ALIMIT_002:
        """
        ループがブロックされている間は、ループ上で動くどの仕組みも動けない。そのため次の保証はすべて失われ、gpframe はブロックされたこと自体も検出しない。

        - `timeout` による待機の打ち切り
        - 停止(キャンセル)の配送と停止コールバックの呼び出し
        - stuck frame の報告と、終了時の判定

        ループが応答しているかどうかの監視は、gpframe.aio の約束の外側にある別の道具(ヘルスチェック)の役割とする。ヘルスチェックの規則は Health monitoring の文書(`health.md`)で定める。
        """

        title @= "A blocked loop voids the guarantees"
        level @= INFORMATIVE
        condition @= "ALIMIT_001 が守られなかった場合。"

    class ALIMIT_003:
        """キャンセルを捕まえて処理を続けるフレームを、外から止める方法はない。gpframe はそうしたフレームを stuck frame として報告し、セッションから切り離す。切り離したフレームが後で止まるかどうか、後始末が行われるかどうかは保証しない。"""

        title @= "Frames that ignore cancellation"
        level @= INFORMATIVE

    class ALIMIT_004:
        """切り離したフレームのタスクは、スコープを抜けた後も走り続けうる。これは「スコープを抜けたら配下のタスクは残らない」という構造化並行性の原則を、意図して破るものである。待ち続けて呼び出し側まで止めるより、止まらなかった事実を報告して先へ進むことを優先する。"""

        title @= "Detaching breaks structured concurrency on purpose"
        level @= INFORMATIVE

    class ALIMIT_005:
        """切り離したフレームのタスクがループの終了時にまだ終わっていなければ、asyncio の通常の規則に従って破棄されうる。そのときの後始末を gpframe は保証しない。"""

        title @= "Pending tasks at loop shutdown"
        level @= INFORMATIVE

    class ALIMIT_006:
        """フレームが `asyncio.to_thread()` などで起動したスレッドは、gpframe が追跡しない。キャンセルはスレッドの中の処理を止めないので、止める必要があれば停止コールバックで止め方を登録する。"""

        title @= "Threads started by a frame"
        level @= INFORMATIVE

    class ALIMIT_007:
        """非同期のセッションは、`async with` で開いたときに動いていたイベントループに属する。`stop()` を除くすべての操作は、そのループのスレッドから行わなければならない。別のスレッドや別のループからの操作は、検出できた場合 `SessionStateError` で拒否する。"""

        title @= "A session belongs to one loop"
        level @= MUST

    class ALIMIT_008:
        """別のスレッドから呼んだ `stop()` は、停止の要求をすぐに記録するが、キャンセルと停止コールバックはループが次に動いたときに届く。ループがブロックされていれば再開したときに、ループが閉じていれば届かない。"""

        title @= "Stopping from another thread"
        level @= INFORMATIVE
        condition @= "ループのスレッド以外から `stop()` を呼んだ場合。"

    class ALIMIT_009:
        """非同期のフレームの中で、同期版のセッションを開いて待ってはならない。同期版の待機はスレッドをブロックし、ALIMIT_001 に反する。"""

        title @= "No synchronous sessions inside async frames"
        level @= MUST_NOT

    class ALIMIT_010:
        """逆に、同期版のフレームで動く `async def` のルーティンの中では、非同期のセッションを使ってよい。そのルーティンは、フレームのスレッド内の専用のイベントループで動くためである。"""

        title @= "Async sessions inside synchronous frames"
        level @= INFORMATIVE

    class ALIMIT_011:
        """`Shared` は非同期のフレームからも使える。ただし内部でスレッド用のロックを使うため、同期版のフレームと同じ `Shared` を奪い合うと、ループは短い時間ブロックされる。`apply()` に渡す関数は、同期版以上に短くすべきである。"""

        title @= "Using Shared from async frames"
        level @= SHOULD

    class ALIMIT_012:
        """ALIMIT_001 に反する呼び出しの一部は、静的検査で見つけられる。例えば Ruff の ASYNC 系の規則(非同期関数の中の `time.sleep()` を指摘する ASYNC251 など)を有効にすべきである。ただし検出できるのは典型的な呼び出しだけであり、ループをブロックしないことの保証にはならない。"""

        title @= "Static checks for blocking calls"
        level @= SHOULD
        condition @= "非同期のルーティンと停止コールバックを書くとき。"
