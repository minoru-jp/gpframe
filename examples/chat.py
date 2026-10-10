"""行単位のチャットサーバー(gpframe.aio によるドッグフーディング)。

    ChatServer
    └── Listener        接続を受け付け、接続ごとのフレームを起動する
        └── (clients)   接続ごとの失敗は、この階層で閉じる
            └── client:<peer>
                ├── Reader    受け取った行を、ほかの参加者へ配る
                └── Writer    自分宛ての行を、ソケットへ書き出す

全体はループの停滞を見張るヘルスチェック(`aio.monitor()`)の中で動く。

プロトコル(1 行 1 メッセージ、UTF-8):

    最初の行      NICK <name>
    以降の行      ほかの参加者へ "<name>: <text>" として配られる
    /who          参加者の一覧
    /quit         切断

    python examples/chat.py --port 7000     # Ctrl-C で止める
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import time
from dataclasses import dataclass, field
from typing import cast

from gpframe import aio

log = logging.getLogger("chat")


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 7000
    max_line: int = 1024
    """これより長い行はプロトコル違反とする。"""
    stop_timeout: float = 5.0
    stall_threshold: float = 1.0
    debug_block: bool = False
    """`/block <秒>` でループをわざと止められるようにする(ヘルスチェックの確認用)。"""


class ProtocolError(Exception):
    """クライアントがプロトコルに従わなかった。その接続だけの失敗。"""


@dataclass
class Stats:
    """ループのスレッドだけが読み書きする。"""

    accepted: int = 0
    joined: int = 0
    failed: int = 0
    stalls: int = 0
    failures: list[str] = field(default_factory=list[str])


class Hub:
    """参加者の宛先の一覧。ループのスレッドだけが使う。"""

    def __init__(self) -> None:
        self._members: dict[str, asyncio.Queue[str]] = {}

    def join(self, name: str, outbox: asyncio.Queue[str]) -> bool:
        if name in self._members:
            return False
        self._members[name] = outbox
        self.publish(f"* {name} joined", sender=name)
        return True

    def leave(self, name: str) -> None:
        if self._members.pop(name, None) is not None:
            self.publish(f"* {name} left", sender=name)

    def publish(self, line: str, *, sender: str) -> None:
        for name, outbox in self._members.items():
            if name != sender:
                outbox.put_nowait(line)

    def names(self) -> list[str]:
        return sorted(self._members)


# ---------------------------------------------------------------- 接続


async def read_line(reader: asyncio.StreamReader, config: Config) -> str | None:
    """1 行読む。接続が閉じられたら `None`。"""
    try:
        raw = await reader.readuntil(b"\n")
    except asyncio.IncompleteReadError as eof:
        if eof.partial:
            raise ProtocolError("the last line has no newline") from None
        return None
    except asyncio.LimitOverrunError:
        raise ProtocolError(f"a line is longer than {config.max_line} bytes") from None
    if len(raw) > config.max_line:
        raise ProtocolError(f"a line is longer than {config.max_line} bytes")
    try:
        return raw.decode().rstrip("\r\n")
    except UnicodeDecodeError:
        raise ProtocolError("a line is not UTF-8") from None


async def reading(
    _ctx: aio.AsyncContext,  # 停止はキャンセルで届くので、使わない
    config: Config,
    hub: Hub,
    name: str,
    reader: asyncio.StreamReader,
    outbox: asyncio.Queue[str],
) -> None:
    """受け取った行を配る。クライアントが去れば戻る。"""
    while (line := await read_line(reader, config)) is not None:
        if line == "/quit":
            outbox.put_nowait("* bye")
            return
        if line == "/who":
            outbox.put_nowait("* " + " ".join(hub.names()))
        elif config.debug_block and line.startswith("/block "):
            # ヘルスチェックの確認用に、ループをわざとブロックする。
            time.sleep(float(line.split()[1]))  # noqa: ASYNC251 - 意図してループを止める
        else:
            hub.publish(f"{name}: {line}", sender=name)


async def writing(
    _ctx: aio.AsyncContext, outbox: asyncio.Queue[str], writer: asyncio.StreamWriter
) -> None:
    """自分宛ての行を書き出し続ける。止めるのはキャンセル。"""
    while True:
        line = await outbox.get()
        writer.write(line.encode() + b"\n")
        await writer.drain()


async def handshake(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, config: Config
) -> str:
    writer.write(b"* welcome. send: NICK <name>\n")
    await writer.drain()
    line = await read_line(reader, config)
    if line is None:
        raise ProtocolError("closed before NICK")
    command, _, name = line.partition(" ")
    if command != "NICK" or not name.isidentifier():
        raise ProtocolError(f"expected NICK <name>, got {line!r}")
    return name


async def client(
    ctx: aio.AsyncContext,
    config: Config,
    hub: Hub,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """一つの接続。読む側が終われば、この接続は終わる。"""
    outbox: asyncio.Queue[str] = asyncio.Queue()
    joined: str | None = None
    try:
        name = await handshake(reader, writer, config)
        if not hub.join(name, outbox):
            writer.write(f"* the name {name} is taken\n".encode())
            return
        joined = name
        writer.write(f"* hello {name}\n".encode())
        async with ctx.session(timeout=config.stop_timeout) as conn:
            incoming = conn.spawn(
                reading, config, hub, name, reader, outbox, name="Reader"
            )
            _ = conn.spawn(writing, outbox, writer, name="Writer")
            # 読む側が終わったら(正常でも失敗でも)、書く側を止める。
            _ = await incoming.wait()
            conn.stop()
    finally:
        if joined is not None:
            hub.leave(joined)
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()


# ---------------------------------------------------------------- Listener


async def listener(
    ctx: aio.AsyncContext,
    config: Config,
    hub: Hub,
    stats: Stats,
    bound: asyncio.Future[int],
) -> None:
    """接続を受け付ける。接続ごとの失敗は記録して、この階層で閉じる。"""
    async with ctx.session(timeout=config.stop_timeout) as clients:

        def accept(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            stats.accepted += 1
            peer = cast("tuple[str, int]", writer.get_extra_info("peername"))
            frame = clients.spawn(
                client, config, hub, reader, writer, name=f"client:{peer[1]}"
            )
            if frame.stopped:
                writer.close()  # 停止の後に来た接続は、走らないので自分で閉じる

        server = await asyncio.start_server(
            accept, config.host, config.port, limit=config.max_line
        )
        async with server:
            bound.set_result(cast("int", server.sockets[0].getsockname()[1]))
            log.info("listening on %s:%d", config.host, bound.result())
            while True:
                # 接続がなくても待ち続ける。停止はキャンセルとしてここに届く。
                for frame in await clients.wait_broken(idle=True):
                    reason = describe(frame)
                    stats.failed += 1
                    stats.failures.append(f"{frame.name}: {reason}")
                    log.info("%s failed: %s", frame.name, reason)
                    frame.ignore()


def describe(frame: aio.AsyncFrame[object]) -> str:
    """接続のフレームの失敗の原因を、木をたどって一行にする。"""
    if frame.error is not None:
        return repr(frame.error)
    report = frame.incomplete
    if report is None:
        return "unknown"
    causes = [describe(f) for f in report.broken]
    causes += [repr(e) for e in report.errors]
    return "; ".join(causes) or "incomplete"


# ---------------------------------------------------------------- ChatServer


async def supervise(s: aio.AsyncSession) -> None:
    """直下のワーカーが一つでも失敗したら、それを上へ伝え、兄弟を止める。"""
    for frame in await s.wait_broken():
        frame.escalate()
    s.stop()


class ChatServer:
    """ワーカーの木の根。`stop()` はどのスレッドからでも、`run()` の前でも呼べる。"""

    def __init__(self, config: Config) -> None:
        self.config: Config = config
        self.hub: Hub = Hub()
        self.stats: Stats = Stats()
        self._app: aio.AsyncSession = aio.session(timeout=config.stop_timeout)
        self._bound: asyncio.Future[int] | None = None

    async def port(self) -> int:
        """待ち受けているポート。待ち受けを始めるまで待つ。"""
        while self._bound is None:
            await asyncio.sleep(0.01)
        return await asyncio.shield(self._bound)

    async def run(self) -> None:
        """止まるまで動く。ワーカーの失敗は `aio.AsyncSessionFailed` として送出する。"""
        self._bound = asyncio.get_running_loop().create_future()
        async with (
            aio.monitor(self.config.stall_threshold, on_stall=self._on_stall),
            self._app as app,
        ):
            _ = app.spawn(
                listener,
                self.config,
                self.hub,
                self.stats,
                self._bound,
                name="Listener",
            )
            await supervise(app)

    def stop(self) -> None:
        self._app.stop()

    def _on_stall(self, stall: aio.LoopStall) -> None:
        # 監視スレッドで呼ばれる。int の加算は GIL の下で一つの操作として扱える。
        self.stats.stalls += 1
        where = stall.stack[-1].strip().splitlines()[0] if stall.stack else "unknown"
        log.warning("event loop stalled for %.2fs at %s", stall.lag, where)


async def serve(config: Config) -> None:
    server = ChatServer(config)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, server.stop)
    await server.run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="gpframe.aio の行単位チャットサーバー")
    _ = parser.add_argument("--port", type=int, default=7000)
    _ = parser.add_argument("--debug-block", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config = Config(
        port=cast("int", args.port), debug_block=cast("bool", args.debug_block)
    )
    try:
        asyncio.run(serve(config))
    except aio.AsyncSessionFailed as failed:
        for frame in failed.frames:
            log.error("%s failed: %s", frame.name, describe(frame))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
