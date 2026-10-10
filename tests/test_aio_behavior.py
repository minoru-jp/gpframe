"""gpframe.aio の、契約にするほどではない普通の振る舞いのテスト。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TypeVar

import pytest

import gpframe
from gpframe import aio

T = TypeVar("T")
WAIT = 5.0


def run(scenario: Callable[[], Coroutine[object, object, T]]) -> T:
    return asyncio.run(scenario())


async def fail(ctx: aio.AsyncContext, message: str = "boom") -> None:
    raise ValueError(message)


async def type_error(ctx: aio.AsyncContext) -> None:
    raise TypeError("wrong")


async def forever(ctx: aio.AsyncContext) -> None:
    _ = await asyncio.Event().wait()


class TestSession:
    def test_names(self) -> None:
        async def who(ctx: aio.AsyncContext) -> str:
            return ctx.name

        async def scenario() -> tuple[str, str]:
            async with aio.session() as s:
                default = s.spawn(who)
                named = s.spawn(who, name="worker-1")
            return await default.result(), await named.result()

        assert run(scenario) == ("who", "worker-1")

    def test_entered_once_and_not_with_plain_with(self) -> None:
        async def scenario() -> None:
            s = aio.session()
            async with s:
                pass
            with pytest.raises(gpframe.SessionStateError):
                async with s:
                    pass

        run(scenario)
        with pytest.raises(TypeError), aio.session():  # pyright: ignore[reportGeneralTypeIssues]
            pass

    def test_negative_timeout_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            _ = aio.session(timeout=-1)

    def test_wait_reports_timeout(self) -> None:
        async def scenario() -> tuple[bool, list[aio.AsyncFrame[object]]]:
            async with aio.session(timeout=WAIT) as s:
                _ = s.spawn(forever)
                timed_out = await s.wait(0.02)
                s.stop()
            return timed_out, await s.wait_broken()

        timed_out, broken = run(scenario)
        assert timed_out is False
        assert broken == []

    def test_strict_raises_unmarked_failure(self) -> None:
        async def scenario() -> None:
            async with aio.session(strict=True) as s:
                _ = s.spawn(fail)

        with pytest.raises(aio.AsyncSessionFailed):
            run(scenario)

    def test_body_error_becomes_context(self) -> None:
        async def scenario() -> None:
            async with aio.session() as s:
                frame = s.spawn(fail)
                _ = await s.wait()
                frame.escalate()
                raise RuntimeError("body")

        with pytest.raises(aio.AsyncSessionFailed) as caught:
            run(scenario)
        assert isinstance(caught.value.__context__, RuntimeError)

    def test_split_keeps_the_matching_frames(self) -> None:
        async def scenario() -> None:
            async with aio.session() as s:
                _ = s.spawn(fail)
                _ = s.spawn(type_error)
                _ = await s.wait()
                for frame in s.broken():
                    frame.escalate()

        with pytest.raises(aio.AsyncSessionFailed) as caught:
            run(scenario)
        matched, rest = caught.value.split(ValueError)
        assert isinstance(matched, aio.AsyncSessionFailed)
        assert isinstance(rest, aio.AsyncSessionFailed)
        assert [f.name for f in matched.frames] == ["fail"]
        assert [f.name for f in rest.frames] == ["type_error"]

    def test_repr_shows_state(self) -> None:
        async def done(ctx: aio.AsyncContext) -> None:
            return None

        async def scenario() -> list[str]:
            async with aio.session(timeout=WAIT) as s:
                running = s.spawn(forever)
                ok = s.spawn(done)
                bad = s.spawn(fail)
                await asyncio.sleep(0)
                states = [repr(running)]
                _ = await s.wait_broken(WAIT)
                bad.ignore()
                s.stop()
            return [*states, repr(ok), repr(bad), repr(running)]

        states = run(scenario)
        assert ["running" in states[0], "succeeded" in states[1]] == [True, True]
        assert "broken" in states[2]
        assert "stopped" in states[3]


class TestStopCallbacks:
    def test_callback_returning_a_coroutine_is_a_failure(self) -> None:
        async def later() -> None:
            return None

        async def routine(ctx: aio.AsyncContext) -> None:
            # コルーチン関数ではないが、呼ぶとコルーチンを返すもの。登録時には見抜けない。
            _ = ctx.on_stop(lambda: later())
            _ = await asyncio.Event().wait()

        async def scenario() -> tuple[BaseException, ...]:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(routine)
                await asyncio.sleep(0)
                s.stop()
                for broken in await s.wait_broken(WAIT):
                    broken.ignore()
            return frame.stop_errors

        errors = run(scenario)
        assert [type(e) for e in errors] == [TypeError]

    def test_base_exception_from_callback_is_wrapped(self) -> None:
        def interrupt() -> None:
            raise KeyboardInterrupt

        async def routine(ctx: aio.AsyncContext) -> None:
            _ = ctx.on_stop(interrupt)
            _ = await asyncio.Event().wait()

        async def scenario() -> None:
            async with aio.session(timeout=WAIT) as s:
                _ = s.spawn(routine)
                await asyncio.sleep(0)
                s.stop()
                for broken in await s.wait_broken(WAIT):
                    broken.escalate()

        with pytest.raises(aio.AsyncSessionFailed) as caught:
            run(scenario)
        error = caught.value.exceptions[0]
        assert isinstance(error, gpframe.FrameAbortedError)
        assert isinstance(error.__cause__, KeyboardInterrupt)


class TestComposition:
    def test_async_session_inside_a_synchronous_frame(self) -> None:
        async def double(ctx: aio.AsyncContext, n: int) -> int:
            await asyncio.sleep(0)
            return n * 2

        async def routine(ctx: gpframe.Context) -> int:
            # 同期版のフレームの async def ルーティンは、自分のループで動く(ALIMIT_010)。
            async with aio.session() as s:
                frames = [s.spawn(double, n) for n in range(4)]
            return sum([await f.result() for f in frames])

        with gpframe.session() as s:
            frame = s.spawn(routine)

        assert frame.result() == 12


class TestMonitor:
    def test_defaults(self) -> None:
        monitor = aio.monitor()
        assert monitor.threshold == 1.0
        assert monitor.interval == 0.25
        custom = aio.monitor(2.0)
        assert (custom.threshold, custom.interval) == (2.0, 0.5)

    def test_parameters_are_validated(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            _ = aio.monitor(0)
        with pytest.raises(ValueError, match="interval"):
            _ = aio.monitor(0.1, interval=0.2)
        with pytest.raises(ValueError, match="interval"):
            _ = aio.monitor(0.1, interval=0)

    def test_entered_once(self) -> None:
        async def scenario() -> None:
            monitor = aio.monitor(1.0)
            async with monitor:
                pass
            with pytest.raises(gpframe.SessionStateError):
                async with monitor:
                    pass

        run(scenario)

    def test_quiet_loop_is_not_stalled(self) -> None:
        async def scenario() -> tuple[bool, float]:
            async with aio.monitor(0.5, interval=0.05) as monitor:
                await asyncio.sleep(0.2)
                return monitor.stalled, monitor.lag

        stalled, lag = run(scenario)
        assert stalled is False
        assert lag < 0.5
