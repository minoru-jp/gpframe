"""gpframe.aio(非同期版)のセッション・フレーム・停止の契約に対するテスト。

各テストは `asyncio.run()` で自分のループを動かす。キャンセルを無視するフレームは、
ループの後始末で止まらないよう、テストの最後に必ず解放する。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import TypeVar

import pytest
from shikumi_contrace import Phase, binds, upholds, violates

import gpframe
from contract.aio_contract import (
    AsyncContextContract,
    AsyncFrameContract,
    AsyncSessionContract,
    AsyncStopHandleContract,
)
from contract.ports.aio_surface import (
    AsyncContext,
    AsyncFrame,
    AsyncSession,
    StopHandle,
)
from gpframe import aio

# test_session_contract.py と同じ理由で、binds より先に形を確かめておく。
_CONTEXT_SHAPE: Callable[..., AsyncContext] = aio.AsyncContext
_SESSION_SHAPE: Callable[..., AsyncSession] = aio.AsyncSession
_FRAME_SHAPE: Callable[..., AsyncFrame[object]] = aio.AsyncFrame
_HANDLE_SHAPE: Callable[..., StopHandle] = aio.StopHandle

WAIT = 5.0
T = TypeVar("T")


def run(scenario: Callable[[], Coroutine[object, object, T]]) -> T:
    return asyncio.run(scenario())


async def ends_cancelled(task: asyncio.Task[None]) -> bool:
    """タスクの終わりを待ち、キャンセルで終わったなら `True` を返す。"""
    try:
        await task
    except asyncio.CancelledError:
        return True
    return False


async def forever(ctx: aio.AsyncContext) -> None:
    _ = await asyncio.Event().wait()


async def fail(ctx: aio.AsyncContext, message: str = "boom") -> None:
    await asyncio.sleep(0)
    raise ValueError(message)


async def stubborn(ctx: aio.AsyncContext, release: asyncio.Event) -> str:
    """キャンセルを無視し続け、release が立つまで止まらないルーティン。"""
    while not release.is_set():
        try:
            _ = await release.wait()
        except asyncio.CancelledError:
            continue
    return "released"


@binds[AsyncSession](aio.AsyncSession)
class TestExitJudgement:
    @upholds(AsyncSessionContract.UnacknowledgedFailuresSurface)
    def test_unmarked_failure_warns(self) -> None:
        async def scenario() -> None:
            with pytest.warns(gpframe.FrameWarning, match="not acknowledged"):
                async with aio.session() as s:
                    _ = s.spawn(fail)

        with Phase.MAIN:
            _ = run(scenario)

    @upholds(AsyncSessionContract.StoppedFramesAreNotFailures)
    def test_stopped_frames_are_silent(self) -> None:
        frames: list[aio.AsyncFrame[None]] = []

        async def scenario() -> None:
            # filterwarnings = error なので、警告が出ればこのテストは失敗する。
            async with aio.session(timeout=WAIT) as s:
                frames.extend([s.spawn(forever), s.spawn(forever)])
                await asyncio.sleep(0)
                s.stop()
            assert s.broken() == []

        with Phase.MAIN:
            _ = run(scenario)

        with Phase.VERIFY:
            assert [f.stopped for f in frames] == [True, True]

    @upholds(AsyncSessionContract.EscalatedFailuresRaise)
    @upholds(AsyncSessionContract.UnacknowledgedFailuresSurface)
    def test_escalated_failure_raises(self) -> None:
        async def scenario() -> None:
            async with aio.session() as s:
                frame = s.spawn(fail, "bad input")
                for broken in await s.wait_broken(WAIT):
                    broken.escalate("parser crashed")
                assert frame.error is not None

        with Phase.MAIN, pytest.raises(aio.AsyncSessionFailed) as caught:
            _ = run(scenario)

        with Phase.VERIFY:
            assert [type(e) for e in caught.value.exceptions] == [ValueError]
            assert "parser crashed" in caught.value.message
            assert len(caught.value.frames) == 1

    @upholds(AsyncSessionContract.OwnerCancellationTakesPrecedence)
    def test_owner_cancellation_is_not_replaced(self) -> None:
        async def owner() -> None:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(fail)
                _ = await s.wait()
                frame.escalate()
                _ = await asyncio.Event().wait()  # ここで外からキャンセルされる

        async def scenario() -> bool:
            task = asyncio.create_task(owner())
            await asyncio.sleep(0.05)
            _ = task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return True
            return False

        with (
            Phase.MAIN,
            pytest.warns(gpframe.FrameWarning, match="cancelled; not raising"),
        ):
            cancelled = run(scenario)

        with Phase.VERIFY:
            assert cancelled is True

    @upholds(AsyncSessionContract.ExitWaitIsBounded)
    def test_exit_does_not_wait_beyond_timeout(self) -> None:
        async def scenario() -> tuple[float, bool, bool, str]:
            release = asyncio.Event()
            loop = asyncio.get_running_loop()
            began = loop.time()
            with pytest.warns(gpframe.FrameWarning, match="did not stop"):
                async with aio.session(timeout=0.1) as s:
                    frame = s.spawn(stubborn, release)
            elapsed = loop.time() - began
            running, stopping = frame.running, s.stopping
            release.set()
            return elapsed, running, stopping, await frame.result(WAIT)

        with Phase.MAIN:
            elapsed, running, stopping, value = run(scenario)

        with Phase.VERIFY:
            assert elapsed < 2.0
            assert running and stopping
            assert value == "released"

    @upholds(AsyncSessionContract.CancellationWhileWaitingAtExit)
    def test_cancellation_while_waiting_at_exit(self) -> None:
        async def scenario() -> tuple[bool, str]:
            release = asyncio.Event()
            frames: list[aio.AsyncFrame[str]] = []

            async def owner() -> None:
                # timeout=None なので、終了時に待ち続ける。
                async with aio.session() as s:
                    frames.append(s.spawn(stubborn, release))

            task = asyncio.create_task(owner())
            await asyncio.sleep(0.05)
            _ = task.cancel()
            with pytest.warns(gpframe.FrameWarning, match="did not stop"):
                cancelled = await ends_cancelled(task)
            release.set()
            return cancelled, await frames[0].result(WAIT)

        with Phase.MAIN:
            cancelled, value = run(scenario)

        with Phase.VERIFY:
            assert cancelled is True
            assert value == "released"


@binds[AsyncSession](aio.AsyncSession)
class TestSubSessions:
    @upholds(AsyncSessionContract.SubSessionReportsToOwner)
    def test_incomplete_sub_session_is_reported_to_owner(self) -> None:
        async def scenario() -> aio.AsyncFrame[int]:
            async def parent(ctx: aio.AsyncContext) -> int:
                async with ctx.session() as sub:
                    _ = sub.spawn(fail)
                return 42

            async with aio.session() as s:
                frame = s.spawn(parent)
                for broken in await s.wait_broken(WAIT):
                    broken.ignore()
            return frame

        with Phase.MAIN:
            frame = run(scenario)

        with Phase.VERIFY:
            assert isinstance(frame, aio.AsyncFrame)
            report = frame.incomplete
            assert report is not None
            assert len(report.broken) == 1

    @upholds(AsyncSessionContract.SubSessionReportsToOwner)
    @upholds(AsyncSessionContract.StopReachesSubSessions)
    def test_stop_cancellation_is_not_incomplete(self) -> None:
        children: list[aio.AsyncFrame[None]] = []
        parents: list[aio.AsyncFrame[None]] = []

        async def scenario() -> None:
            started = asyncio.Event()

            async def parent(ctx: aio.AsyncContext) -> None:
                async with ctx.session(timeout=WAIT) as sub:
                    children.append(sub.spawn(forever))
                    started.set()
                    _ = await sub.wait()

            async with aio.session(timeout=WAIT) as s:
                parents.append(s.spawn(parent))
                _ = await started.wait()
                s.stop()

        with Phase.MAIN:
            _ = run(scenario)

        with Phase.VERIFY:
            assert children[0].stopped
            assert parents[0].stopped
            assert parents[0].incomplete is None

    @upholds(AsyncSessionContract.StopReachesSubSessions)
    def test_sub_session_opened_after_stop_is_stopping(self) -> None:
        async def scenario() -> object:
            async def parent(ctx: aio.AsyncContext) -> bool:
                try:
                    _ = await asyncio.Event().wait()
                except asyncio.CancelledError:
                    async with ctx.session() as sub:
                        return sub.stopping
                return False

            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(parent)
                await asyncio.sleep(0)
                s.stop()
            return await frame.result()

        with Phase.MAIN:
            value = run(scenario)

        with Phase.VERIFY:
            assert value is True


@binds[AsyncSession](aio.AsyncSession)
class TestSpawn:
    @upholds(AsyncSessionContract.spawn.SessionIsOpen)
    @upholds(AsyncSessionContract.spawn.RoutineIsCoroutineFunction)
    @upholds(AsyncSessionContract.spawn.CalledFromOwnLoop)
    def test_open_session_accepts_coroutine_function(self) -> None:
        async def double(ctx: aio.AsyncContext, n: int) -> int:
            return n * 2

        async def scenario() -> object:
            async with aio.session() as s:
                frame = s.spawn(double, 21)
            return await frame.result()

        with Phase.MAIN:
            value = run(scenario)

        with Phase.VERIFY:
            assert value == 42

    @violates(AsyncSessionContract.spawn.SessionIsOpen)
    def test_spawn_outside_the_session_is_rejected(self) -> None:
        async def scenario() -> None:
            s = aio.session()
            with pytest.raises(gpframe.SessionStateError):
                _ = s.spawn(forever)
            async with s:
                pass
            with pytest.raises(gpframe.SessionStateError):
                _ = s.spawn(forever)

        with Phase.MAIN:
            _ = run(scenario)

    @upholds(AsyncSessionContract.spawn.SpawnAfterStopIsStopped)
    def test_spawn_after_stop_returns_a_stopped_frame(self) -> None:
        called: list[str] = []

        async def record(ctx: aio.AsyncContext) -> None:
            called.append(ctx.name)

        async def scenario() -> aio.AsyncFrame[None]:
            async with aio.session(strict=True) as s:
                s.stop()
                frame = s.spawn(record)
                assert s.broken() == []
                assert not s.running()
                with pytest.raises(aio.FrameStoppedError):
                    await frame.result(0)
                with pytest.raises(gpframe.FrameStateError):
                    frame.ignore()
            return frame

        with Phase.MAIN:
            frame = run(scenario)

        with Phase.VERIFY:
            assert called == []
            assert (frame.stopped, frame.running, frame.succeeded) == (
                True,
                False,
                False,
            )
            assert (frame.error, frame.incomplete, frame.stop_errors) == (
                None,
                None,
                (),
            )

    @upholds(AsyncSessionContract.spawn.SpawnAfterStopIsStopped)
    def test_spawn_in_a_stopped_sub_session_is_not_a_failure(self) -> None:
        async def owner(ctx: aio.AsyncContext) -> bool:
            try:
                _ = await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass  # 停止を受けて、後始末として次の仕事を起動しようとする
            async with ctx.session() as sub:
                late = sub.spawn(forever)
            return late.stopped

        async def scenario() -> aio.AsyncFrame[bool]:
            async with aio.session(timeout=WAIT, strict=True) as s:
                frame = s.spawn(owner)
                await asyncio.sleep(0)
                s.stop()
            return frame

        with Phase.MAIN:
            frame = run(scenario)

        with Phase.VERIFY:
            assert frame.succeeded

    @violates(AsyncSessionContract.spawn.RoutineIsCoroutineFunction)
    def test_synchronous_routine_is_rejected(self) -> None:
        def blocking(ctx: aio.AsyncContext) -> None:
            return None

        async def scenario() -> bool:
            async with aio.session() as s:
                with pytest.raises(TypeError):
                    _ = s.spawn(blocking)  # pyright: ignore[reportArgumentType]
                return s.running()

        with Phase.MAIN:
            running = run(scenario)

        with Phase.VERIFY:
            assert running is False

    @violates(AsyncSessionContract.spawn.CalledFromOwnLoop)
    def test_spawn_from_another_thread_is_rejected(self) -> None:
        errors: list[BaseException] = []

        async def scenario() -> None:
            async with aio.session() as s:

                def from_thread() -> None:
                    try:
                        _ = s.spawn(forever)
                    except BaseException as error:  # noqa: BLE001 - 種類をテストで確かめる
                        errors.append(error)

                thread = threading.Thread(target=from_thread)
                thread.start()
                await asyncio.to_thread(thread.join)

        with Phase.MAIN:
            _ = run(scenario)

        with Phase.VERIFY:
            assert [type(e) for e in errors] == [gpframe.SessionStateError]


@binds[AsyncSession](aio.AsyncSession)
class TestStop:
    @upholds(AsyncSessionContract.stop.CancelsEachFrameOnce)
    def test_each_frame_is_cancelled_once(self) -> None:
        async def careful(ctx: aio.AsyncContext) -> int:
            received = 0
            try:
                _ = await asyncio.Event().wait()
            except asyncio.CancelledError:
                received += 1
                try:
                    await asyncio.sleep(0.1)  # 後始末。二度目のキャンセルは来ない
                except asyncio.CancelledError:
                    received += 1
            return received

        async def scenario() -> tuple[object, bool]:
            async with aio.session(timeout=WAIT) as s:
                first = s.spawn(careful)
                other = s.spawn(forever)
                await asyncio.sleep(0)
                s.stop()
                await asyncio.sleep(0.02)
                s.stop()
            return await first.result(), other.stopped

        with Phase.MAIN:
            received, other_stopped = run(scenario)

        with Phase.VERIFY:
            assert received == 1
            assert other_stopped is True

    @upholds(AsyncSessionContract.stop.SafeFromAnyThread)
    def test_stop_from_another_thread(self) -> None:
        async def scenario() -> tuple[bool, bool]:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(forever)
                await asyncio.sleep(0)
                thread = threading.Thread(target=s.stop)
                thread.start()
                await asyncio.to_thread(thread.join)
                finished = await s.wait(WAIT)
            return finished, frame.stopped

        with Phase.MAIN:
            finished, stopped = run(scenario)

        with Phase.VERIFY:
            assert finished and stopped

    @upholds(AsyncSessionContract.stop.WorksInAnyState)
    def test_stop_before_open(self) -> None:
        async def scenario() -> tuple[bool, bool]:
            s = aio.session(strict=True)
            s.stop()
            async with s:
                stopping = s.stopping
                frame = s.spawn(forever)
            s.stop()  # 閉じた後に呼んでもよい
            return stopping, frame.stopped

        with Phase.MAIN:
            stopping, stopped = run(scenario)

        with Phase.VERIFY:
            assert stopping and stopped


@binds[AsyncSession](aio.AsyncSession)
class TestWaitBroken:
    @upholds(AsyncSessionContract.wait_broken.ReturnsOnFirstFailure)
    def test_returns_on_first_failure(self) -> None:
        async def scenario() -> tuple[list[str], bool]:
            async with aio.session(timeout=WAIT) as s:
                long_running = s.spawn(forever)
                _ = s.spawn(fail)
                failed = await s.wait_broken(WAIT)
                still_running = long_running.running
                for frame in failed:
                    frame.ignore()
                s.stop()
            return [f.name for f in failed], still_running

        with Phase.MAIN:
            names, still_running = run(scenario)

        with Phase.VERIFY:
            assert names == ["fail"]
            assert still_running is True

    @upholds(AsyncSessionContract.wait_broken.WaiterCancellationDoesNotStopFrames)
    def test_cancelling_the_waiter_keeps_frames(self) -> None:
        async def scenario() -> tuple[bool, bool, bool]:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(forever)
                waiter = asyncio.create_task(s.wait_broken())
                await asyncio.sleep(0.02)
                _ = waiter.cancel()
                try:
                    _ = await waiter
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0.02)
                observed = (frame.running, s.stopping)
                s.stop()
            return observed[0], observed[1], frame.stopped

        with Phase.MAIN:
            running, stopping, stopped = run(scenario)

        with Phase.VERIFY:
            assert running is True
            assert stopping is False
            assert stopped is True


@binds[AsyncFrame[object]](aio.AsyncFrame)
class TestFrameStates:
    @upholds(AsyncFrameContract.StopCancellationMeansStopped)
    def test_stop_makes_frame_stopped(self) -> None:
        async def scenario() -> aio.AsyncFrame[None]:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(forever)
                await asyncio.sleep(0)
                s.stop()
            return frame

        with Phase.MAIN:
            frame = run(scenario)

        with Phase.VERIFY:
            assert isinstance(frame, aio.AsyncFrame)
            assert frame.stopped and not frame.succeeded
            assert frame.error is None

    @upholds(AsyncFrameContract.ForeignCancellationBreaks)
    def test_foreign_cancellation_breaks(self) -> None:
        async def scenario() -> aio.AsyncFrame[None]:
            tasks: list[asyncio.Task[object]] = []

            async def routine(ctx: aio.AsyncContext) -> None:
                task = asyncio.current_task()
                assert task is not None
                tasks.append(task)
                _ = await asyncio.Event().wait()

            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(routine)
                await asyncio.sleep(0)
                _ = tasks[0].cancel()
                _ = await s.wait(WAIT)
                frame.ignore()
            return frame

        with Phase.MAIN:
            frame = run(scenario)

        with Phase.VERIFY:
            assert isinstance(frame, aio.AsyncFrame)
            assert not frame.stopped
            assert isinstance(frame.error, asyncio.CancelledError)

    @upholds(AsyncFrameContract.ReturningAfterCancellationSucceeds)
    def test_returning_after_cancellation_succeeds(self) -> None:
        async def tidy(ctx: aio.AsyncContext) -> str:
            try:
                _ = await asyncio.Event().wait()
            except asyncio.CancelledError:
                return "cleaned up"
            return "unreachable"

        async def scenario() -> tuple[bool, object]:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(tidy)
                await asyncio.sleep(0)
                s.stop()
            return frame.succeeded, await frame.result()

        with Phase.MAIN:
            succeeded, value = run(scenario)

        with Phase.VERIFY:
            assert succeeded is True
            assert value == "cleaned up"

    @upholds(AsyncFrameContract.CallbackErrorsBreakFrame)
    def test_callback_error_breaks_frame(self) -> None:
        def bad_callback() -> None:
            raise ValueError("shutdown failed")

        async def routine(ctx: aio.AsyncContext) -> None:
            _ = ctx.on_stop(bad_callback)
            _ = await asyncio.Event().wait()

        async def scenario() -> None:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(routine)
                await asyncio.sleep(0)
                s.stop()
                for broken in await s.wait_broken(WAIT):
                    broken.escalate()
                assert [type(e) for e in frame.stop_errors] == [ValueError]

        with Phase.MAIN, pytest.raises(aio.AsyncSessionFailed) as caught:
            _ = run(scenario)

        with Phase.VERIFY:
            assert [type(e) for e in caught.value.exceptions] == [ValueError]


@binds[AsyncFrame[object]](aio.AsyncFrame)
class TestInterrupts:
    @upholds(AsyncFrameContract.InterruptsAreNotSwallowed)
    def test_keyboard_interrupt_reaches_the_caller(self) -> None:
        frames: list[aio.AsyncFrame[None]] = []

        async def interrupted(ctx: aio.AsyncContext) -> None:
            await asyncio.sleep(0)
            raise KeyboardInterrupt

        async def scenario() -> None:
            async with aio.session(timeout=WAIT) as s:
                frames.append(s.spawn(interrupted))
                _ = await asyncio.Event().wait()

        # ループの終了に伴うキャンセルとして終了処理が走り、未承認の失敗が警告される。
        with (
            Phase.MAIN,
            pytest.raises(KeyboardInterrupt),
            pytest.warns(gpframe.FrameWarning, match="not acknowledged"),
        ):
            run(scenario)

        with Phase.VERIFY:
            assert not frames[0].running
            assert isinstance(frames[0].error, KeyboardInterrupt)
            assert repr(frames[0]).endswith("broken>")


@binds[AsyncFrame[object]](aio.AsyncFrame)
class TestResult:
    @upholds(AsyncFrameContract.result.ReportsOutcome)
    def test_outcomes(self) -> None:
        async def value(ctx: aio.AsyncContext) -> int:
            return 7

        async def scenario() -> list[str]:
            seen: list[str] = []
            async with aio.session(timeout=WAIT) as s:
                ok = s.spawn(value)
                bad = s.spawn(fail, "from routine")
                held = s.spawn(forever)
                with pytest.raises(TimeoutError):
                    _ = await held.result(0.02)
                seen.append(str(await ok.result()))
                with pytest.raises(ValueError, match="from routine"):
                    _ = await bad.result()
                seen.append("raised")
                bad.ignore()
                s.stop()
            with pytest.raises(aio.FrameStoppedError):
                _ = await held.result()
            seen.append("stopped")
            return seen

        with Phase.MAIN:
            seen = run(scenario)

        with Phase.VERIFY:
            assert seen == ["7", "raised", "stopped"]

    @upholds(AsyncFrameContract.result.DoesNotLeakCancellation)
    def test_foreign_cancellation_is_wrapped(self) -> None:
        async def scenario() -> BaseException | None:
            tasks: list[asyncio.Task[object]] = []

            async def routine(ctx: aio.AsyncContext) -> None:
                task = asyncio.current_task()
                assert task is not None
                tasks.append(task)
                _ = await asyncio.Event().wait()

            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(routine)
                await asyncio.sleep(0)
                _ = tasks[0].cancel()
                with pytest.raises(gpframe.FrameAbortedError) as caught:
                    _ = await frame.result(WAIT)
                frame.ignore()
            return caught.value.__cause__

        with Phase.MAIN:
            cause = run(scenario)

        with Phase.VERIFY:
            assert isinstance(cause, asyncio.CancelledError)

    @upholds(AsyncFrameContract.result.WaiterCancellationDoesNotCancelFrame)
    def test_cancelling_the_waiter_keeps_the_frame(self) -> None:
        async def scenario() -> tuple[bool, bool]:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(forever)
                waiter = asyncio.create_task(frame.result())
                await asyncio.sleep(0.02)
                _ = waiter.cancel()
                try:
                    _ = await waiter
                except asyncio.CancelledError:
                    pass
                await asyncio.sleep(0.02)
                still_running = frame.running
                s.stop()
            return still_running, frame.stopped

        with Phase.MAIN:
            still_running, stopped = run(scenario)

        with Phase.VERIFY:
            assert still_running and stopped


@binds[AsyncFrame[object]](aio.AsyncFrame)
class TestAcknowledgement:
    @upholds(AsyncFrameContract.ignore.OnlyUnacknowledgedFailures)
    @upholds(AsyncFrameContract.escalate.OnlyUnacknowledgedFailures)
    def test_failed_frames_can_be_acknowledged(self) -> None:
        async def scenario() -> None:
            async with aio.session() as s:
                first = s.spawn(fail)
                second = s.spawn(fail)
                _ = await s.wait(WAIT)
                first.ignore()
                second.escalate()

        with Phase.MAIN, pytest.raises(aio.AsyncSessionFailed):
            _ = run(scenario)

    @violates(AsyncFrameContract.ignore.OnlyUnacknowledgedFailures)
    @violates(AsyncFrameContract.escalate.OnlyUnacknowledgedFailures)
    def test_non_failures_are_rejected(self) -> None:
        async def done(ctx: aio.AsyncContext) -> None:
            return None

        async def scenario() -> list[str]:
            messages: list[str] = []
            async with aio.session(timeout=WAIT) as s:
                running = s.spawn(forever)
                ok = s.spawn(done)
                bad = s.spawn(fail)
                _ = await ok.result()
                _ = await s.wait_broken(WAIT)
                bad.ignore()
                for frame in (running, ok, bad):
                    with pytest.raises(gpframe.FrameStateError) as caught:
                        frame.escalate()
                    messages.append(str(caught.value))
                s.stop()
                _ = await s.wait(WAIT)
                with pytest.raises(gpframe.FrameStateError, match="was stopped"):
                    running.ignore()
            return messages

        with Phase.MAIN:
            messages = run(scenario)

        with Phase.VERIFY:
            assert isinstance(messages, list)
            assert "still running" in messages[0]
            assert "did not fail" in messages[1]
            assert "already" in messages[2]


@binds[AsyncContext](aio.AsyncContext)
class TestOnStop:
    @upholds(AsyncContextContract.on_stop.CalledBeforeCancellation)
    @upholds(AsyncContextContract.on_stop.CallbackIsSynchronous)
    def test_called_before_cancellation_on_the_loop(self) -> None:
        events: list[str] = []
        threads: list[int] = []

        async def routine(ctx: aio.AsyncContext) -> None:
            _ = ctx.on_stop(
                lambda: (events.append("first"), threads.append(threading.get_ident()))
            )
            _ = ctx.on_stop(lambda: events.append("second"))
            try:
                _ = await asyncio.Event().wait()
            except asyncio.CancelledError:
                events.append("cancelled")
                raise

        async def scenario() -> int:
            async with aio.session(timeout=WAIT) as s:
                _ = s.spawn(routine)
                await asyncio.sleep(0)
                s.stop()
                s.stop()
            return threading.get_ident()

        with Phase.MAIN:
            loop_thread = run(scenario)

        with Phase.VERIFY:
            assert events == ["first", "second", "cancelled"]
            assert threads == [loop_thread]

    @violates(AsyncContextContract.on_stop.CallbackIsSynchronous)
    def test_coroutine_callback_is_rejected(self) -> None:
        async def async_callback() -> None:
            return None

        async def routine(ctx: aio.AsyncContext) -> bool:
            try:
                _ = ctx.on_stop(async_callback)
            except TypeError:
                return True
            return False

        async def scenario() -> object:
            async with aio.session() as s:
                frame = s.spawn(routine)
            return await frame.result()

        with Phase.MAIN:
            rejected = run(scenario)

        with Phase.VERIFY:
            assert rejected is True

    @upholds(AsyncContextContract.on_stop.RegisteredAfterStopIsCalled)
    def test_registered_after_stop_is_called(self) -> None:
        async def routine(ctx: aio.AsyncContext) -> bool:
            called: list[bool] = []
            try:
                _ = await asyncio.Event().wait()
            except asyncio.CancelledError:
                _ = ctx.on_stop(lambda: called.append(True))
                await asyncio.sleep(0.02)
            return called == [True]

        async def scenario() -> object:
            async with aio.session(timeout=WAIT) as s:
                frame = s.spawn(routine)
                await asyncio.sleep(0)
                s.stop()
            return await frame.result()

        with Phase.MAIN:
            called = run(scenario)

        with Phase.VERIFY:
            assert called is True


@binds[StopHandle](aio.StopHandle)
class TestStopHandle:
    @upholds(AsyncStopHandleContract.cancel.PreventsLaterCall)
    def test_cancelled_callback_is_not_called(self) -> None:
        events: list[str] = []

        async def routine(ctx: aio.AsyncContext) -> None:
            handle = ctx.on_stop(lambda: events.append("cancelled one"))
            _ = ctx.on_stop(lambda: events.append("kept"))
            handle.cancel()
            _ = await asyncio.Event().wait()

        async def scenario() -> None:
            async with aio.session(timeout=WAIT) as s:
                _ = s.spawn(routine)
                await asyncio.sleep(0)
                s.stop()

        with Phase.MAIN:
            _ = run(scenario)

        with Phase.VERIFY:
            assert events == ["kept"]
