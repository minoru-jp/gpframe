"""gpframe の README の正本。

コード例は `test_target_field` に分け、文字列そのものを定数として持つ。
tests/test_devdocs.py がこの定数を実行して、例が実装と食い違っていないことを確かめる。
"""

from shikumi_devdoc.norms.common import canonical_source
from shikumi_devdoc.norms.document import test_target_field, title

QUICK_START = """\
import gpframe


def parse(ctx: gpframe.Context, text: str) -> int:
    return int(text)


with gpframe.session(timeout=5) as s:
    frames = [s.spawn(parse, text) for text in ["1", "2", "x"]]
    s.wait()
    for frame in s.broken():
        if isinstance(frame.error, ValueError):
            frame.ignore()  # 想定内の失敗として承認する
        else:
            frame.escalate()  # 想定外。with を抜けるときに SessionFailed になる

print(sum(f.result() for f in frames if f.succeeded))  # 3
"""

STOP_EXAMPLE = """\
import time

import gpframe


def ticker(ctx: gpframe.Context, interval: float) -> int:
    count = 0
    while not ctx.stopping:
        count += 1
        ctx.wait_stop(interval)  # 停止が要求されるとすぐに起きる sleep
    return count


with gpframe.session(timeout=5) as s:
    frame = s.spawn(ticker, 0.1)
    time.sleep(0.5)
    s.stop()

print(frame.result() > 0)  # True
"""

SHARED_EXAMPLE = """\
import gpframe


def work(ctx: gpframe.Context, done: gpframe.Shared[int]) -> None:
    for _ in range(1_000):
        done.apply(lambda n: n + 1)  # 読み取りから書き込みまでを一つの操作で行う


done = gpframe.Shared(int, 0)  # 型と初期値を同時に決める
with gpframe.session() as s:
    for _ in range(4):
        s.spawn(work, done)

print(done.get())  # 4000
"""

COMPONENTS_EXAMPLE = """\
import http.server

import gpframe


def web(ctx: gpframe.Context) -> None:
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), http.server.BaseHTTPRequestHandler
    )
    ctx.on_stop(server.shutdown)  # ブロックしている serve_forever() を止める
    with server:
        server.serve_forever()


def worker(ctx: gpframe.Context) -> None:
    ctx.wait_stop(0.2)
    raise RuntimeError("worker crashed")


try:
    with gpframe.session(timeout=5) as s:
        s.spawn(web)
        s.spawn(worker)
        for frame in s.wait_broken():  # 最初の失敗を待つ
            frame.escalate("component failed")
        s.stop()  # 残りの部品も止める
except* RuntimeError as group:
    print(group.exceptions[0])  # worker crashed
"""

AIO_EXAMPLE = """\
import asyncio

from gpframe import aio


async def web(ctx: aio.AsyncContext) -> None:
    await asyncio.Event().wait()  # 動き続ける部品。停止はキャンセルとして届く


async def worker(ctx: aio.AsyncContext) -> None:
    await asyncio.sleep(0.1)
    raise RuntimeError("worker crashed")


async def main() -> None:
    async with aio.monitor():  # 1 秒を超えるループの停滞を報告する
        async with aio.session(timeout=5) as s:
            s.spawn(web)
            s.spawn(worker)
            for frame in await s.wait_broken():  # 最初の失敗を待つ
                frame.escalate("component failed")
            s.stop()  # 残りの部品をキャンセルで止める


try:
    asyncio.run(main())
except* RuntimeError as group:
    print(group.exceptions[0])  # worker crashed
"""

TREE_EXAMPLE = """\
import gpframe


def supervise(s: gpframe.Session) -> None:
    \"\"\"直下のワーカーが一つでも失敗したら、それを上へ伝え、兄弟を止める。\"\"\"
    for frame in s.wait_broken():
        frame.escalate()
    s.stop()


def idle(ctx: gpframe.Context) -> None:
    while not ctx.stopping:  # 実際の仕事の代わり
        ctx.wait_stop(0.05)


def consumer(ctx: gpframe.Context) -> None:
    ctx.wait_stop(0.2)
    raise ConnectionError("broker unreachable")


def web_server(ctx: gpframe.Context) -> None:
    with ctx.session(timeout=5) as s:
        s.spawn(idle, name="RequestHandler")
        s.spawn(idle, name="ConnectionManager")
        supervise(s)


def message_worker(ctx: gpframe.Context) -> None:
    with ctx.session(timeout=5) as s:
        s.spawn(consumer, name="Consumer")
        s.spawn(idle, name="Processor")
        supervise(s)


try:
    with gpframe.session(timeout=5) as app:
        app.spawn(web_server, name="WebServer")
        app.spawn(message_worker, name="MessageWorker")
        app.spawn(idle, name="Monitor")
        supervise(app)
except gpframe.SessionFailed as failed:
    for frame in failed.frames:
        report = frame.incomplete
        causes = [f"{c.name}: {c.error}" for c in report.broken] if report else []
        print(frame.name, "failed because", ", ".join(causes))
"""

CHANNEL_EXAMPLE = """\
import gpframe


def produce(ctx: gpframe.Context, jobs: gpframe.Channel[int]) -> None:
    for n in range(1, 11):
        jobs.put(n)
    jobs.close()  # もう送らない、と伝える


def consume(ctx: gpframe.Context, jobs: gpframe.Channel[int]) -> int:
    # 停止が要求されるか、閉じられて空になったらループを抜ける
    return sum(n * n for n in jobs.receive(ctx))


jobs = gpframe.Channel(int)
with gpframe.session(timeout=5) as s:
    s.spawn(produce, jobs)
    consumers = [s.spawn(consume, jobs) for _ in range(3)]  # 値は三つで分け合う
    for frame in s.wait_broken():
        frame.escalate()

print(sum(f.result() for f in consumers))  # 385
"""

quick_start = test_target_field("quick start")
tree_example = test_target_field("tree example")
stop_example = test_target_field("stop example")
shared_example = test_target_field("shared example")
channel_example = test_target_field("channel example")
components_example = test_target_field("components example")
aio_example = test_target_field("aio example")


@canonical_source(
    "{{project.name}}",
    filename="README.md",
    merge_policy="all",
    heading="title",
)
class SECTION_001:
    r"""
    `{{project.name}}` は、並行処理を**ワーカーの木**として構造的に組み立てるための、小さなフレームワークです。

    システムをいくつかのワーカーに分け、各ワーカーがさらに自分の下のワーカーを持つ。その構造をコードにそのまま書けます。各階層では直下のワーカーだけを理解すればよく、その下で何が動いているかを知らなくても、システム全体の止め方と失敗の扱いについて推論できます。
    """

    class SECTION_012:
        r"""
        例えば、次のようなシステムを考えます。

        ```text
        Application
        ├── WebServer
        │   ├── RequestHandler
        │   └── ConnectionManager
        ├── MessageWorker
        │   ├── Consumer
        │   └── Processor
        └── Monitor
        ```

        gpframe では、この木がそのままコードになります。

        ```python
        {{tree_example}}
        ```

        実行すると、`MessageWorker failed because Consumer: broker unreachable` と表示され、全体が止まります。

        読むときに注目してほしいのは、どの関数も**直下のワーカーしか知らない**ことです。根の `app` は `WebServer`・`MessageWorker`・`Monitor` の三つだけを、`message_worker` は `Consumer` と `Processor` だけを起動しています。Consumer が落ちたことは、根からは「MessageWorker が失敗した」という一つの失敗として見えます。

        どの階層も、`supervise()` という同じ形で書けています。gpframe では、こうしたワーカー一つ一つを**フレーム**と呼び、フレームを束ねるスコープを**セッション**と呼びます。
        """

        title @= "ワーカーの木を書く"
        tree_example @= TREE_EXAMPLE

    class SECTION_013:
        r"""
        木の各階層で推論できるのは、停止と失敗が次のように一段ずつ伝わるからです。

        - **停止は下へ伝わります。** `s.stop()` は直下のフレームに停止を要求し、それらのフレームが開いているセッションにも伝わります。根の `app.stop()` 一つで木全体が止まり、各ワーカーは自分の直下の止め方だけを知っていれば足ります。
        - **失敗は上へ、一段ずつまとまって伝わります。** ワーカーの中のセッションで、承認されないまま残った失敗は、そのワーカー自身の失敗になります。親から見えるのはそのワーカーの失敗一つで、中身を知る必要はありません。知りたければ `frame.incomplete` から辿れます。
        - **想定内の失敗は、その場で閉じられます。** ワーカーの中で `ignore()` した失敗は、親には伝わりません。どこまでを自分で引き受けるかを、各ワーカーが決められます。
        - **最終的な判断は根だけが行います。** フレームの中のセッションでは、`escalate()` しても例外は起きず、印を付けて親へ伝えるだけです。例外として送出するか警告にするかは、根のセッションが決めます。

        同期版のワーカーの下に、非同期版(`gpframe.aio`)の木を作ることはできます。逆に、非同期版のワーカーの下に同期版のセッションを開いてはいけません。同期版の待機がイベントループをブロックするためです。
        """

        title @= "停止は下へ、失敗は上へ"

    class SECTION_002:
        r"""
        - **停止は協調的です。** gpframe は停止を要求するだけで、実際に止まるかどうかは処理の書き方に委ねます。処理の中で `ctx.stopping` や `ctx.wait_stop()` を確認するか、ブロックする処理なら `ctx.on_stop()` で止め方を登録してください。
        - **止まらなかったスレッドは走り続けます。** Python のスレッドは外から安全に止められないためです。gpframe はそのスレッドを警告で報告するところまでを受け持ちます。スレッドはデーモンスレッドとして起動するので、プロセスの終了は妨げません。
        - **実行はスレッドか、asyncio のタスクです。** 同期版の `gpframe` はフレームをスレッドで、非同期版の `gpframe.aio` はイベントループのタスクとして動かします。プロセスでの並列実行は扱いません。スレッドは待ち(I/O や停止)を並べるためのもので、Python の計算を複数のスレッドに分けても速くはなりません。
        - Python `{{project.requires-python}}` が必要です。
        """

        title @= "最初に知っておくこと"

    class SECTION_003:
        r"""
        ```bash
        pip install "gpframe>={{project.version}}"
        ```

        PyPI 上の `0.0.x` 系は作り直す前の旧実装で、この README とは互換性がありません。
        """

        title @= "インストール"

    class SECTION_014:
        r"""
        ここからは、木の構造を保つために gpframe が用意している道具を、一つずつ説明します。失敗の承認や停止の仕組みは、それ自体が目的ではなく、ワーカーの境界をはっきりさせるためのものです。
        """

        title @= "構造を保つための道具"

        class SECTION_004:
            r"""
            `gpframe.session()` で開いたセッションの中で、`spawn()` した関数がそれぞれ一つのスレッド(フレーム)として動きます。関数は第 1 引数に `Context` を受け取り、残りの引数は `spawn()` に渡したものがそのまま届きます。

            ```python
            {{quick_start}}
            ```

            `spawn()` が返す `Frame` は `concurrent.futures.Future` に近いハンドルで、`result()` で戻り値を受け取れます。ルーティンは `async def` でも構いません。フレームの中で `ctx.session()` を開けば、そのフレームの下にさらに階層を作れます。
            """

            title @= "一つの階層の書き方"
            quick_start @= QUICK_START

        class SECTION_005:
            r"""
            例外で終わったフレームは **broken frame** になります。`s.broken()` はまだ承認されていない broken frame だけを返すので、ポーリングで繰り返し呼んでも同じフレームを二度処理しません。

            根のセッションの `with` を抜けるとき、残った broken frame は次のように扱われます。

            | 状態 | `with` を抜けたときの結果 |
            | --- | --- |
            | すべて `ignore()` 済み、または失敗なし | 何も起きない |
            | `escalate()` されたものがある | `SessionFailed`(`ExceptionGroup`)を送出する |
            | どちらのマークもないものがある | `FrameWarning` で警告する |
            | `strict=True` でマークのないものがある | `SessionFailed` に含めて送出する |

            `SessionFailed` は `ExceptionGroup` なので、`except*` で例外の型ごとに受け取れます。`f.result()` を呼んで例外を見ただけでは承認になりません。失敗を受け入れるかどうかは、必ず `ignore()` か `escalate()` で明示します。

            サブセッションで `escalate()` した失敗は、その場では例外になりません。サブセッションの報告として親フレームに付き、親フレームの**ルーティンが戻ったとき**に、そのフレームの失敗として一つ上の階層に現れます。監視のループのように長く動き続けるフレームの中では、失敗が戻るまで表に出ないので、すぐに上へ伝えたい場合はその場で例外を送出します。

            ```python
            for frame in sub.wait_broken():
                raise ConnectionError(frame.name) from frame.error  # このフレームを今すぐ失敗にする
            ```
            """

            title @= "失敗を承認する"

        class SECTION_006:
            r"""
            `s.stop()` は、セッションのすべてのフレームに停止を要求します。ルーティンは `ctx.stopping` をループの条件にし、`time.sleep()` の代わりに `ctx.wait_stop()` を使うと、要求にすぐ応えられます。

            ```python
            {{stop_example}}
            ```

            `with` を抜けるとき、セッションは最大 `timeout` 秒(既定の `None` なら終わるまで)フレームの終了を待ちます。時間内に止まらなかったフレームは **stuck frame** として `FrameWarning` で報告し、停止を要求したうえで先へ進みます。`with` ブロックの中で例外が起きた場合は、待つ前に停止を要求します。

            停止の後に `spawn()` したフレームは、ルーティンを呼ばずに **stopped** のフレームとして返ります(`frame.stopped` が `True`)。止まる途中で始めようとした仕事は失敗ではないので、例外にも承認の対象にもなりません。停止を確かめてから起動するまでの間に停止が来ても、何も書き足す必要はありません。ただしルーティンは呼ばれないので、受け付けたソケットのように後始末が要るものを引数に渡した場合は、`frame.stopped` を確かめて自分で閉じます。

            シグナルの処理や別のスレッドからルートのセッションを止めたいときは、セッションを `with` の前に作って参照を渡しておき、その `stop()` を呼びます。`stop()` は `with` に入る前でも呼べ、その場合はセッションを開いた時点で止まっています。
            """

            title @= "止める"
            stop_example @= STOP_EXAMPLE

        class SECTION_010:
            r"""
            HTTP サーバーのように中でブロックし続ける部品は、`ctx.stopping` を確認できません。こうした部品には、二つの道具を組み合わせます。

            - `ctx.on_stop(callback)` は、停止が要求されたときに呼ぶ関数を登録します。`serve_forever()` なら `server.shutdown` を登録して止め方を教えておきます。コールバックは別のスレッドで一度だけ呼ばれ、`stop()` はその完了を待ちません。
            - `s.wait_broken()` は、最初の失敗が出るまで待ち、その時点の `broken()` を返します。失敗がないまますべて終わるか、時間切れになった場合は空の並びを返します。

            ```python
            {{components_example}}
            ```

            停止コールバックが例外を出した場合も、そのフレームは broken frame になり、`Frame.stop_errors` から例外を読めます。

            並行に走らせたフレームの結果を集めるときは、`[f.result() for f in frames]` の前に `wait_broken()` で失敗を確かめます。`result()` を起動した順に待つと、先に失敗したフレームがあっても、前にある遅いフレームが終わるまで気づけないためです。

            「読む側が終わったら書く側を止める」のように、終わり方を問わず一つのフレームの終わりだけを待つときは `frame.wait()` を使います。例外を送出せず、終われば `True` を返します。

            接続や要求ごとにフレームを起動するサーバーでは、`wait_broken(idle=True)` で失敗を待ち続けます。実行中のフレームが一つもなくても戻らず、失敗か停止の要求で戻ります。終わったフレームはセッションが手放すので(`ignore()` したものも含む)、長く動かしても溜まりません。

            ```python
            while not ctx.stopping:
                for frame in clients.wait_broken(idle=True):
                    log.info("%s failed: %r", frame.name, frame.error)
                    frame.ignore()  # 接続ごとの失敗は、この階層で閉じる
            ```
            """

            title @= "ブロックする部品を止める"
            components_example @= COMPONENTS_EXAMPLE

        class SECTION_008:
            r"""
            フレーム間で値を共有するときは `Shared` を使います。型と初期値を生成時に決め、値は常にその型に保たれます。`apply()` は読み取りから書き込みまでを一つの操作として行うので、並行した更新を失いません。

            ```python
            {{shared_example}}
            ```

            複数の値をまとめて一貫させたいときは、不変のデータクラスを一つの `Shared` に入れて `apply()` で丸ごと差し替えます。結果の受け取りにはフレームの戻り値を使ってください。
            """

            title @= "値を共有する"
            shared_example @= SHARED_EXAMPLE

        class SECTION_015:
            r"""
            フレームからフレームへ値を順に渡すときは `Channel` を使います。受け取る側の `receive(ctx)` は、値が届くのを待ちながら、**停止が要求されると自然にループを抜けます**。止め方を別に書かなくても、止められるワーカーになります。

            ```python
            {{channel_example}}
            ```

            - `put(item)` は待たずに戻り、フレームの外のスレッドからも呼べます。
            - `close()` は「もう送らない」という知らせです。残った値は届けられ、空になったところで受け取りのループが終わります。
            - 停止が要求された後は、値が残っていても受け取りません。停止の後に新しい仕事を始めないためです。
            - 一つずつ取り出すときは `get(ctx, timeout)` を使います。値がなければ `None` を返し、理由は `ctx.stopping` と `jobs.closed` で区別できます。

            送る側が受け取る側より速いと、値はチャネルに溜まり続けます。`Channel(Job, maxsize=100)` のように上限を付け、送る側では `put(item, ctx)` を使います。満杯なら空きが出るまで待ち、停止の要求か `close()` で待ちを解いて `False` を返します。`ctx` を渡さない `put(item)` は、満杯なら待たずに `ChannelFullError` を送出します。満杯のときに値を黙って捨てる扱いはありません。

            ```python
            for batch in read_batches():
                if not lines.put(batch, ctx):  # 満杯なら空くまで待つ
                    return  # 停止したか、下流が閉じた
            ```

            ログ集計の例では、上限なしだと 44MB のログのほぼ全体がチャネルに溜まり(112MB)、上限 20 では 24MB で、速さは変わりませんでした。

            細かい値を大量に流すときは、リストにまとめて渡します(`Channel(list)` を `gpframe.Channel[list[str]]` と注釈する)。一件ずつ渡すと、スレッドの間の受け渡しの費用が処理そのものより大きくなります。ログ集計の例(`examples/logstats.py`)では、500 行ずつまとめるだけで 4 倍ほど速くなりました。

            `Channel` は同期版だけの部品です。非同期版では停止がキャンセルなので、`asyncio.Queue` の待ちがそのまま止まります。
            """

            title @= "値を受け渡す"
            channel_example @= CHANNEL_EXAMPLE

    class SECTION_011:
        r"""
        `gpframe.aio` は、フレームをイベントループのタスクとして動かす非同期版です。同期版とは型を共有しない独立した API で、`async with` で開き、待機はすべて `await` で行います。ワーカーの木は、非同期版でも同じ形(`ctx.session()` で下の階層を開く)で書けます。

        - **停止はキャンセルです。** `s.stop()` はフレームのタスクをキャンセルし、停止の要求で終わったフレームは失敗ではなく stopped になります。gpframe が要求していないキャンセルで終わったフレームは broken です。
        - **`spawn()` に渡せるのはコルーチン関数だけです。** 同期関数をループの上で呼ぶと、ループをブロックしうるためです。
        - **`ctx` を使わないルーティンもよくあります。** 停止がキャンセルとして届くためです。型検査器の未使用引数の警告は、`_ctx` と名付けると避けられます。
        - **ヘルスチェック `aio.monitor()` でループの停滞を見張れます。** ループの外のスレッドが応答の遅れを測り、停滞を検出すると、ブロックしている箇所のスタックとともに報告します。

        ```python
        {{aio_example}}
        ```

        非同期版には、一つのループの上で動くことから来る原理的な限界があります。フレームがループをブロックすると、`timeout` や報告の保証は失われます。キャンセルを無視するタスクは、止まらなかったものとして報告したうえで切り離し、後始末は保証しません。詳しくは非同期版の Specification の「Constraints and limits」を参照してください。
        """

        title @= "非同期版(gpframe.aio)"
        aio_example @= AIO_EXAMPLE

    class SECTION_016:
        r"""
        開発に必要な道具は extras の `dev` にまとめています。検査はすべて `tools/check.py` で走らせ、CI とリリースも同じものを使います。

        ```console
        pip install -e ".[dev]"
        python tools/check.py            # すべての検査
        python tools/check.py lint tests # 選んだ検査だけ
        ```

        振る舞いの規則は `devdocs/canonical_sources/` の正本(日本語)に書き、`python scripts/render_devdocs.py` で canonical document を生成します。英語の公開文書は canonical document の翻訳です。
        """

        title @= "開発"

    class SECTION_009:
        r"""
        - [STATUS.md](STATUS.md): 開発段階、対応範囲、品質の状態、今後の方向
        - [specification/INDEX.md](specification/INDEX.md): 振る舞いの規則(Specification)
        - [specification_aio/INDEX.md](specification_aio/INDEX.md): 非同期版の振る舞いの規則と、その制約・限界
        - [CHANGELOG.md](CHANGELOG.md): 版ごとの変更
        """

        title @= "関連文書"
