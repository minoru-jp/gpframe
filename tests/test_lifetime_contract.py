"""終わったフレームの手放し、`Frame.wait()`、`wait_broken(idle=True)` の契約に対するテスト。

チャットサーバー(examples/chat.py)のドッグフーディングで見つかった不足を埋めた部分。
同期版と非同期版の両方を確かめる。
"""

from __future__ import annotations

import asyncio
import gc
import threading
import time
import weakref
from collections.abc import Callable, Coroutine, Sequence
from typing import Any, TypeVar

from shikumi_contrace import Phase, binds, upholds

import gpframe
from contract.aio_contract import (
    AsyncFrameContract,
    AsyncSessionContract,
    AsyncStopHandleContract,
)
from contract.ports.aio_surface import AsyncFrame, AsyncSession
from contract.ports.aio_surface import StopHandle as AsyncStopHandle
from contract.ports.surface import Frame, Session, StopHandle
from contract.session_contract import (
    FrameContract,
    SessionContract,
    StopHandleContract,
)
from gpframe import aio
from tests.conftest import blocked, fail, succeed, until_stopped

T = TypeVar("T")
WAIT = 5.0

# binds の型検査の回避策(STATUS_006)。
_SESSION_SHAPE: Callable[..., Session] = gpframe.Session
_FRAME_SHAPE: Callable[..., Frame[object]] = gpframe.Frame
_ASESSION_SHAPE: Callable[..., AsyncSession] = aio.AsyncSession
_AFRAME_SHAPE: Callable[..., AsyncFrame[object]] = aio.AsyncFrame
_HANDLE_SHAPE: Callable[..., StopHandle] = gpframe.StopHandle
_AHANDLE_SHAPE: Callable[..., AsyncStopHandle] = aio.StopHandle


class Callback:
    """weakref で解放を確かめられる停止コールバック。"""

    def __call__(self) -> None:
        return None


def cancel_once(
    on_stop: Callable[[Callable[[], object]], gpframe.StopHandle | aio.StopHandle],
) -> weakref.ref[Callback]:
    """登録してすぐ取り消し、コールバックへの weakref を返す。"""
    callback = Callback()
    on_stop(callback).cancel()
    return weakref.ref(callback)


class Payload:
    """引数として渡し、解放されたかを weakref で確かめるもの。"""


def keep(ctx: gpframe.Context, payload: Payload) -> int:
    return 1


def reject(ctx: gpframe.Context, payload: Payload) -> int:
    raise ValueError("rejected")


def released(refs: Sequence[weakref.ref[Any]]) -> bool:
    _ = gc.collect()
    return all(ref() is None for ref in refs)


def run(scenario: Callable[[], Coroutine[object, object, T]]) -> T:
    return asyncio.run(scenario())


def alive(names: set[str]) -> set[str]:
    """名前が `names` にあるフレームのうち、まだメモリに残っているものの名前。"""
    _ = gc.collect()
    found: set[str] = set()
    for obj in gc.get_objects():
        if isinstance(obj, gpframe.Frame | aio.AsyncFrame):
            frame: gpframe.Frame[object] | aio.AsyncFrame[object] = obj
            if frame.name in names:
                found.add(frame.name)
    return found


@binds[Session](gpframe.Session)
class TestSyncRelease:
    @upholds(SessionContract.KeepsOnlyWhatJudgementNeeds)
    def test_finished_frames_and_arguments_are_released(self) -> None:
        names = {"r-keep", "r-reject", "r-stopper", "r-stopped"}
        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            payloads = [Payload(), Payload(), Payload()]
            refs = [weakref.ref(p) for p in payloads]
            kept = s.spawn(keep, payloads[0], name="r-keep")
            rejected = s.spawn(reject, payloads[1], name="r-reject")
            assert s.wait(WAIT)
            rejected.ignore()
            stopper = s.spawn(until_stopped, name="r-stopper")
            s.stop()
            assert stopper.wait(WAIT)
            stopped = s.spawn(keep, payloads[2], name="r-stopped")
            del payloads, kept, rejected, stopper, stopped
            # セッションを開いたまま、ハンドルを手放せば解放される。
            frames_left = alive(names)
            payloads_freed = released(refs)

        with Phase.VERIFY:
            assert frames_left == set()
            assert payloads_freed

    @upholds(SessionContract.KeepsOnlyWhatJudgementNeeds)
    def test_frames_needed_by_the_judgement_are_kept(self) -> None:
        with Phase.MAIN, gpframe.session(timeout=WAIT, strict=True) as s:
            frame = s.spawn(reject, Payload(), name="r-unacked")
            assert s.wait(WAIT)
            frame_id = id(frame)
            del frame
            kept = alive({"r-unacked"})  # 承認されていない失敗は保持する
            (frame,) = s.broken()
            assert id(frame) == frame_id
            frame.ignore()
            del frame
            after_ignore = alive({"r-unacked"})

        with Phase.VERIFY:
            assert kept == {"r-unacked"}
            assert after_ignore == set()


@binds[Frame[object]](gpframe.Frame)
class TestSyncFrameWait:
    @upholds(FrameContract.wait.WaitsWithoutRaising)
    def test_wait_does_not_raise_or_acknowledge(self, gate: threading.Event) -> None:
        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            failing = s.spawn(fail)
            ended = failing.wait(WAIT)
            still_broken = s.broken() == [failing]
            stuck = s.spawn(blocked, gate)
            timed_out = stuck.wait(0.05)
            gate.set()
            failing.ignore()

        with Phase.VERIFY:
            assert ended is True
            assert still_broken
            assert timed_out is False

    @upholds(FrameContract.wait.WaitsWithoutRaising)
    def test_wait_on_a_stopped_frame(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            s.stop()
            frame = s.spawn(succeed)
            ended = frame.wait(0)

        with Phase.VERIFY:
            assert ended is True


@binds[Session](gpframe.Session)
class TestSyncIdleWait:
    @upholds(SessionContract.wait_broken.IdleWaitsForFailureOrStop)
    def test_idle_waits_through_an_empty_session(self) -> None:
        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            began = time.monotonic()
            empty = s.wait_broken(0.2, idle=True)
            waited = time.monotonic() - began
            timer = threading.Timer(0.1, lambda: s.spawn(fail))
            timer.start()
            failed = s.wait_broken(WAIT, idle=True)
            timer.join()
            for frame in failed:
                frame.ignore()

        with Phase.VERIFY:
            assert empty == []
            assert waited >= 0.2
            assert [f.name for f in failed] == ["fail"]

    @upholds(SessionContract.wait_broken.IdleWaitsForFailureOrStop)
    def test_idle_returns_on_a_stop_request(self) -> None:
        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            timer = threading.Timer(0.1, s.stop)
            timer.start()
            began = time.monotonic()
            failed = s.wait_broken(WAIT, idle=True)
            waited = time.monotonic() - began
            timer.join()

        with Phase.VERIFY:
            assert failed == []
            assert waited < WAIT


async def akeep(ctx: aio.AsyncContext, payload: Payload) -> int:
    return 1


async def areject(ctx: aio.AsyncContext, payload: Payload) -> int:
    raise ValueError("rejected")


async def aforever(ctx: aio.AsyncContext) -> None:
    _ = await asyncio.Event().wait()


@binds[AsyncSession](aio.AsyncSession)
class TestAsyncRelease:
    @upholds(AsyncSessionContract.KeepsOnlyWhatJudgementNeeds)
    def test_finished_frames_and_arguments_are_released(self) -> None:
        names = {"a-keep", "a-reject", "a-cancelled", "a-stopped", "a-unacked"}

        async def scenario() -> tuple[set[str], bool, set[str]]:
            async with aio.session(timeout=WAIT) as s:
                payloads = [Payload(), Payload(), Payload()]
                refs = [weakref.ref(p) for p in payloads]
                kept = s.spawn(akeep, payloads[0], name="a-keep")
                rejected = s.spawn(areject, payloads[1], name="a-reject")
                unacked = s.spawn(areject, Payload(), name="a-unacked")
                assert await s.wait(WAIT)
                rejected.ignore()
                cancelled = s.spawn(aforever, name="a-cancelled")
                await asyncio.sleep(0)
                s.stop()
                assert await cancelled.wait(WAIT)
                stopped = s.spawn(akeep, payloads[2], name="a-stopped")
                del payloads, kept, rejected, cancelled, stopped, unacked
                left = alive(names)
                freed = released(refs)
                (frame,) = s.broken()
                frame.ignore()
                del frame
                return left, freed, alive(names)

        with Phase.MAIN:
            left, freed, after_ignore = run(scenario)

        with Phase.VERIFY:
            assert left == {"a-unacked"}  # 承認されていない失敗だけが残る
            assert freed
            assert after_ignore == set()


@binds[AsyncFrame[object]](aio.AsyncFrame)
class TestAsyncFrameWait:
    @upholds(AsyncFrameContract.wait.WaitsWithoutRaising)
    def test_wait_does_not_raise_or_acknowledge(self) -> None:
        async def boom(ctx: aio.AsyncContext) -> None:
            raise ValueError("boom")

        async def scenario() -> tuple[bool, bool, bool, bool]:
            async with aio.session(timeout=WAIT) as s:
                failing = s.spawn(boom)
                ended = await failing.wait(WAIT)
                still_broken = s.broken() == [failing]
                long = s.spawn(aforever)
                timed_out = await long.wait(0.05)
                failing.ignore()
                s.stop()
                late = s.spawn(aforever)
                stopped_ended = await late.wait(0)
            return ended, still_broken, timed_out, stopped_ended

        with Phase.MAIN:
            ended, still_broken, timed_out, stopped_ended = run(scenario)

        with Phase.VERIFY:
            assert (ended, still_broken, timed_out) == (True, True, False)
            assert stopped_ended is True


@binds[AsyncSession](aio.AsyncSession)
class TestAsyncIdleWait:
    @upholds(AsyncSessionContract.wait_broken.IdleWaitsForFailureOrStop)
    def test_idle_waits_for_a_later_failure_and_for_stop(self) -> None:
        async def boom(ctx: aio.AsyncContext) -> None:
            raise ValueError("boom")

        async def scenario() -> tuple[list[str], list[str], float]:
            loop = asyncio.get_running_loop()
            async with aio.session(timeout=WAIT) as s:
                empty = await s.wait_broken(0.1, idle=True)
                _ = loop.call_later(0.1, lambda: s.spawn(boom))
                failed = await s.wait_broken(WAIT, idle=True)
                names = [f.name for f in failed]
                for frame in failed:
                    frame.ignore()
                stopper = threading.Timer(0.1, s.stop)  # 別のスレッドからの停止
                stopper.start()
                began = loop.time()
                after_stop = await s.wait_broken(WAIT, idle=True)
                waited = loop.time() - began
                await asyncio.to_thread(stopper.join)
            return [f.name for f in empty] + names, [f.name for f in after_stop], waited

        with Phase.MAIN:
            names, after_stop, waited = run(scenario)

        with Phase.VERIFY:
            assert names == ["boom"]
            assert after_stop == []
            assert waited < WAIT


@binds[StopHandle](gpframe.StopHandle)
class TestSyncCancelRelease:
    @upholds(StopHandleContract.cancel.ReleasesRegistration)
    def test_cancelled_registrations_do_not_pile_up(self) -> None:
        def routine(ctx: gpframe.Context) -> bool:
            refs = [cancel_once(ctx.on_stop) for _ in range(1_000)]
            return released(refs)

        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(routine)

        with Phase.VERIFY:
            assert frame.result() is True


@binds[AsyncStopHandle](aio.StopHandle)
class TestAsyncCancelRelease:
    @upholds(AsyncStopHandleContract.cancel.ReleasesRegistration)
    def test_cancelled_registrations_do_not_pile_up(self) -> None:
        async def routine(ctx: aio.AsyncContext) -> bool:
            refs = [cancel_once(ctx.on_stop) for _ in range(1_000)]
            return released(refs)

        async def scenario() -> bool:
            async with aio.session() as s:
                frame = s.spawn(routine)
            return await frame.result()

        with Phase.MAIN:
            freed = run(scenario)

        with Phase.VERIFY:
            assert freed is True
