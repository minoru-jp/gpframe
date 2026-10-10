"""`Channel` の契約に対するテスト。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import cast

import pytest
from shikumi_contrace import Phase, binds, upholds, violates

import gpframe
from contract.channel_contract import ChannelContract
from contract.ports.surface import Channel

WAIT = 5.0


def received_by(
    ctx: gpframe.Context, channel: gpframe.Channel[int], ready: threading.Event
) -> list[int]:
    ready.set()
    return list(channel.receive(ctx))


def waiting(
    ctx: gpframe.Context,
    channel: gpframe.Channel[int],
    ready: threading.Event,
    timeout: float | None = None,
) -> tuple[int | None, bool, bool]:
    ready.set()
    item = channel.get(ctx, timeout)
    return item, ctx.stopping, channel.closed


def in_frame(fn: Callable[[gpframe.Context], object]) -> object:
    """`Context` が要る操作を、一つのフレームの中で行う。"""
    with gpframe.session() as s:
        frame = s.spawn(fn)
        _ = s.wait()
        for broken in s.broken():
            broken.ignore()  # 例外は result() で受け取る
    return frame.result()


@binds[Channel[int]](gpframe.Channel)
class TestPut:
    @upholds(ChannelContract.put.ItemMatchesType)
    @upholds(ChannelContract.put.WithoutContextDoesNotWait)
    def test_put_returns_at_once(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)

        with Phase.MAIN:
            began = time.monotonic()
            for n in range(10_000):
                channel.put(n)
            elapsed = time.monotonic() - began

        with Phase.VERIFY:
            assert elapsed < 1.0
            assert channel.type is int

    @violates(ChannelContract.put.ItemMatchesType)
    def test_put_rejects_wrong_type_and_none(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)

        with Phase.MAIN:
            with pytest.raises(gpframe.DeclaredTypeError):
                channel.put(cast("int", "one"))
            with pytest.raises(gpframe.DeclaredTypeError):
                channel.put(cast("int", None))
            channel.close()

        with Phase.VERIFY:
            assert in_frame(lambda ctx: channel.get(ctx, 0)) is None

    @violates(ChannelContract.put.WithoutContextChannelIsOpen)
    def test_put_after_close_is_rejected(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            channel.put(1)
            channel.close()

        with Phase.MAIN, pytest.raises(gpframe.ChannelClosedError):
            channel.put(2)

        with Phase.VERIFY:
            assert in_frame(lambda ctx: list(channel.receive(ctx))) == [1]


@binds[Channel[int]](gpframe.Channel)
class TestDelivery:
    @upholds(ChannelContract.DeliversInOrderOnce)
    def test_values_come_out_in_order(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            for n in range(5):
                channel.put(n)
            channel.close()

        with Phase.MAIN:
            items = in_frame(lambda ctx: list(channel.receive(ctx)))

        with Phase.VERIFY:
            assert items == [0, 1, 2, 3, 4]

    @upholds(ChannelContract.DeliversInOrderOnce)
    def test_receivers_share_the_values(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            count = 2_000
            ready = [threading.Event() for _ in range(4)]

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frames = [s.spawn(received_by, channel, r) for r in ready]
            for r in ready:
                assert r.wait(WAIT)
            for n in range(count):
                channel.put(n)
            channel.close()

        with Phase.VERIFY:
            parts = [f.result() for f in frames]
            assert sorted(n for part in parts for n in part) == list(range(count))
            for part in parts:
                assert part == sorted(part)


@binds[Channel[int]](gpframe.Channel)
class TestGet:
    @upholds(ChannelContract.get.StopEndsTheWait)
    @pytest.mark.parametrize("path", ["stop", "parent", "body-error"])
    def test_any_stop_request_ends_the_wait(self, path: str) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            ready = threading.Event()

            def owner(ctx: gpframe.Context) -> tuple[int | None, bool, bool]:
                with ctx.session() as sub:
                    inner = sub.spawn(waiting, channel, ready)
                return inner.result()

        with Phase.MAIN:
            began = time.monotonic()
            if path == "stop":
                with gpframe.session(timeout=WAIT) as s:
                    frame = s.spawn(waiting, channel, ready)
                    assert ready.wait(WAIT)
                    s.stop()
            elif path == "parent":
                with gpframe.session(timeout=WAIT) as s:
                    frame = s.spawn(owner)
                    assert ready.wait(WAIT)
                    s.stop()
            else:
                holder: list[gpframe.Frame[tuple[int | None, bool, bool]]] = []
                with (
                    pytest.raises(RuntimeError),
                    gpframe.session(timeout=WAIT) as s,
                ):
                    holder.append(s.spawn(waiting, channel, ready))
                    assert ready.wait(WAIT)
                    raise RuntimeError("body")
                frame = holder[0]
            elapsed = time.monotonic() - began

        with Phase.VERIFY:
            assert elapsed < WAIT
            assert frame.result() == (None, True, False)

    @upholds(ChannelContract.get.StopTakesPrecedence)
    def test_values_are_left_after_a_stop(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            channel.put(1)
            ready = threading.Event()
            gate = threading.Event()

            def take_after_stop(ctx: gpframe.Context) -> int | None:
                ready.set()
                _ = gate.wait(WAIT)
                return channel.get(ctx)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(take_after_stop)
            assert ready.wait(WAIT)
            s.stop()
            gate.set()

        with Phase.VERIFY:
            assert frame.result() is None
            channel.close()
            assert in_frame(lambda ctx: list(channel.receive(ctx))) == [1]

    @upholds(ChannelContract.get.CloseLetsRemainingThrough)
    @upholds(ChannelContract.close.WakesAllReceivers)
    def test_close_wakes_every_receiver(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            ready = [threading.Event() for _ in range(3)]

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frames = [s.spawn(waiting, channel, r) for r in ready]
            for r in ready:
                assert r.wait(WAIT)
            channel.put(7)
            channel.close()

        with Phase.VERIFY:
            results = sorted(
                (f.result() for f in frames), key=lambda r: (r[0] is None, r)
            )
            assert results[0] == (7, False, True)
            assert results[1:] == [(None, False, True), (None, False, True)]

    @upholds(ChannelContract.get.TimeoutReturnsNone)
    @upholds(ChannelContract.get.TimeoutIsValid)
    def test_timeout(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            ready = threading.Event()

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(waiting, channel, ready, 0.05)

        with Phase.VERIFY:
            assert frame.result() == (None, False, False)

    @violates(ChannelContract.get.TimeoutIsValid)
    def test_negative_timeout_is_rejected(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)

        with Phase.MAIN, pytest.raises(ValueError, match="timeout"):
            _ = in_frame(lambda ctx: channel.get(ctx, -1))


def producing(
    ctx: gpframe.Context,
    channel: gpframe.Channel[int],
    items: range,
    ready: threading.Event,
) -> list[bool]:
    ready.set()
    return [channel.put(n, ctx) for n in items]


@binds[Channel[int]](gpframe.Channel)
class TestCapacity:
    @upholds(ChannelContract.NeverExceedsCapacity)
    @upholds(ChannelContract.put.WithContextWaitsForSpace)
    def test_a_fast_producer_waits_for_space(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int, maxsize=3)
            ready = threading.Event()
            sizes: list[int] = []

            def slow_consumer(ctx: gpframe.Context) -> list[int]:
                taken: list[int] = []
                while (item := channel.get(ctx)) is not None:
                    sizes.append(_size(channel))
                    taken.append(item)
                    time.sleep(0.001)
                return taken

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            producer = s.spawn(producing, channel, range(200), ready)
            consumer = s.spawn(slow_consumer)
            assert producer.wait(WAIT)
            channel.close()

        with Phase.VERIFY:
            assert channel.maxsize == 3
            assert all(producer.result())
            assert consumer.result() == list(range(200))
            assert max(sizes) <= 3

    @violates(ChannelContract.put.WithoutContextChannelHasSpace)
    @upholds(ChannelContract.NeverExceedsCapacity)
    def test_put_without_context_is_rejected_when_full(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int, maxsize=1)
            channel.put(1)

        with Phase.MAIN, pytest.raises(gpframe.ChannelFullError):
            channel.put(2)

        with Phase.VERIFY:
            channel.close()
            assert in_frame(lambda ctx: list(channel.receive(ctx))) == [1]

    @upholds(ChannelContract.put.WithContextStopEndsTheWait)
    @pytest.mark.parametrize("ending", ["stop", "close", "timeout"])
    def test_a_waiting_producer_gives_up(self, ending: str) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int, maxsize=1)
            channel.put(0)
            ready = threading.Event()
            timeout = 0.1 if ending == "timeout" else None

            def blocked_producer(ctx: gpframe.Context) -> tuple[bool, bool, bool]:
                ready.set()
                added = channel.put(1, ctx, timeout)
                return added, ctx.stopping, channel.closed

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(blocked_producer)
            assert ready.wait(WAIT)
            time.sleep(0.05)
            if ending == "stop":
                s.stop()
            elif ending == "close":
                channel.close()
            began = time.monotonic()
            assert frame.wait(WAIT)
            elapsed = time.monotonic() - began

        with Phase.VERIFY:
            expected = {
                "stop": (False, True, False),
                "close": (False, False, True),
                "timeout": (False, False, False),
            }
            assert frame.result() == expected[ending]
            assert elapsed < WAIT
            assert _size(channel) == 1  # 何も加えていない

    @upholds(ChannelContract.put.WithContextStopEndsTheWait)
    def test_put_after_stop_or_close_adds_nothing(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)
            ready = threading.Event()
            gate = threading.Event()

            def late(ctx: gpframe.Context) -> bool:
                ready.set()
                _ = gate.wait(WAIT)
                return channel.put(1, ctx)  # 空きはあるが、停止の後

        with Phase.MAIN:
            with gpframe.session(timeout=WAIT) as s:
                frame = s.spawn(late)
                assert ready.wait(WAIT)
                s.stop()
                gate.set()
            channel.close()
            after_close = in_frame(lambda ctx: channel.put(2, ctx))

        with Phase.VERIFY:
            assert frame.result() is False
            assert after_close is False
            assert _size(channel) == 0

    @violates(ChannelContract.put.TimeoutIsValid)
    def test_negative_timeout_is_rejected(self) -> None:
        with Phase.PREPARE:
            channel = gpframe.Channel(int)

        with Phase.MAIN, pytest.raises(ValueError, match="timeout"):
            _ = in_frame(lambda ctx: channel.put(1, ctx, -1))

    @upholds(ChannelContract.NeverExceedsCapacity)
    def test_negative_maxsize_is_rejected(self) -> None:
        with Phase.MAIN, pytest.raises(ValueError, match="maxsize"):
            _ = gpframe.Channel(int, maxsize=-1)


def _size(channel: gpframe.Channel[int]) -> int:
    """チャネルに残っている値の数。テストのために repr から読む。"""
    return int(repr(channel).split(", ")[2].split("/")[0])
