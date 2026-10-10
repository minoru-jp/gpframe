"""チャットサーバー(examples/chat.py)のテスト。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TypeVar

from examples import chat

T = TypeVar("T")
WAIT = 5.0


def run(scenario: Callable[[], Coroutine[object, object, T]]) -> T:
    return asyncio.run(asyncio.wait_for(scenario(), 20))


@dataclass
class Client:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter

    async def send(self, line: str) -> None:
        self.writer.write(line.encode() + b"\n")
        await self.writer.drain()

    async def line(self) -> str:
        raw = await asyncio.wait_for(self.reader.readline(), WAIT)
        return raw.decode().rstrip("\n")

    async def closed(self) -> bool:
        """接続が閉じられるまで読み捨てる。閉じられれば `True`。"""
        _ = await asyncio.wait_for(self.reader.read(), WAIT)
        return self.reader.at_eof()

    async def close(self) -> None:
        self.writer.close()
        with contextlib.suppress(OSError):
            await self.writer.wait_closed()


@dataclass
class Harness:
    server: chat.ChatServer
    port: int
    clients: list[Client] = field(default_factory=list[Client])

    async def connect(self) -> Client:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        client = Client(reader, writer)
        self.clients.append(client)
        assert (await client.line()).startswith("* welcome")
        return client

    async def join(self, name: str) -> Client:
        client = await self.connect()
        await client.send(f"NICK {name}")
        assert await client.line() == f"* hello {name}"
        return client


@asynccontextmanager
async def running(config: chat.Config) -> AsyncIterator[Harness]:
    server = chat.ChatServer(config)
    task = asyncio.create_task(server.run())
    harness = Harness(server, await asyncio.wait_for(server.port(), WAIT))
    try:
        yield harness
    finally:
        server.stop()
        await asyncio.wait_for(task, WAIT)
        for client in harness.clients:
            await client.close()


CONFIG = chat.Config(port=0, stop_timeout=2.0)


def test_messages_reach_the_others() -> None:
    async def scenario() -> list[str]:
        async with running(CONFIG) as h:
            alice = await h.join("alice")
            bob = await h.join("bob")
            seen = [await alice.line()]  # bob joined
            await alice.send("hi")
            seen.append(await bob.line())
            await bob.send("/who")
            seen.append(await bob.line())
            await bob.send("/quit")
            seen.append(await bob.line())
            seen.append(await alice.line())  # bob left
            assert await bob.closed()
            await alice.close()
            return seen

    assert run(scenario) == [
        "* bob joined",
        "alice: hi",
        "* alice bob",
        "* bye",
        "* bob left",
    ]


def test_a_protocol_error_fails_only_that_connection() -> None:
    async def scenario() -> chat.Stats:
        async with running(CONFIG) as h:
            alice = await h.join("alice")
            rude = await h.connect()
            await rude.send("HELLO")  # NICK ではない
            assert await rude.closed()
            long = await h.join("carol")
            await long.send("x" * 2_000)
            assert await long.closed()
            assert await alice.line() == "* carol joined"
            assert await alice.line() == "* carol left"
            # 失敗した接続があっても、ほかの接続は動き続ける。
            bob = await h.join("bob")
            await bob.send("still here")
            assert await alice.line() == "* bob joined"
            assert await alice.line() == "bob: still here"
            await asyncio.sleep(0.2)
            return h.server.stats

    stats = run(scenario)
    assert stats.failed == 2
    assert "ProtocolError" in stats.failures[0]
    assert "longer than" in stats.failures[1]


def test_a_taken_name_and_a_dropped_connection_are_not_failures() -> None:
    async def scenario() -> chat.Stats:
        async with running(CONFIG) as h:
            alice = await h.join("alice")
            twin = await h.connect()
            await twin.send("NICK alice")
            assert await twin.line() == "* the name alice is taken"
            assert await twin.closed()
            bob = await h.join("bob")
            await bob.close()  # /quit なしで切る
            assert await alice.line() == "* bob joined"
            assert await alice.line() == "* bob left"
            await asyncio.sleep(0.2)
            return h.server.stats

    stats = run(scenario)
    assert stats.failed == 0
    assert stats.accepted == 3


def test_stop_closes_every_connection() -> None:
    async def scenario() -> bool:
        async with running(CONFIG) as h:
            clients = [await h.join(f"user{n}") for n in range(5)]
            loop = asyncio.get_running_loop()
            began = loop.time()
            h.server.stop()
            closed = [await c.closed() for c in clients]
            return all(closed) and loop.time() - began < WAIT

    assert run(scenario) is True


def test_stop_before_run() -> None:
    async def scenario() -> None:
        server = chat.ChatServer(CONFIG)
        server.stop()
        await asyncio.wait_for(server.run(), WAIT)

    run(scenario)


def test_the_monitor_reports_a_blocked_loop() -> None:
    config = chat.Config(
        port=0, stop_timeout=2.0, stall_threshold=0.2, debug_block=True
    )

    async def scenario() -> chat.Stats:
        async with running(config) as h:
            alice = await h.join("alice")
            await alice.send("/block 0.6")
            await alice.send("/who")
            assert await alice.line() == "* alice"
            return h.server.stats

    assert run(scenario).stalls == 1
