"""停止コールバックと wait_broken() の契約に対するテスト。

タイミングに頼らず、`threading.Event` で順序を確定させて確かめる。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest
from shikumi_contrace import Phase, binds, upholds

import gpframe
from contract.ports.surface import Context, Frame, Session, StopHandle
from contract.session_contract import (
    ContextContract,
    FrameContract,
    SessionContract,
    StopHandleContract,
)
from tests.conftest import blocked, fail, succeed, until_stopped

# test_session_contract.py と同じ理由で、binds より先に形を確かめておく。
_CONTEXT_SHAPE: Callable[..., Context] = gpframe.Context
_SESSION_SHAPE: Callable[..., Session] = gpframe.Session
_FRAME_SHAPE: Callable[..., Frame[object]] = gpframe.Frame
_HANDLE_SHAPE: Callable[..., StopHandle] = gpframe.StopHandle

WAIT = 5.0


@binds[Context](gpframe.Context)
class TestOnStop:
    @upholds(ContextContract.on_stop.CalledOnceOnStop)
    def test_called_once_on_another_thread(self) -> None:
        with Phase.PREPARE:
            ready = threading.Event()
            called = threading.Event()
            calls: list[int] = []
            routine_thread: list[int] = []

            def callback() -> None:
                calls.append(threading.get_ident())
                called.set()

            def routine(ctx: gpframe.Context) -> None:
                routine_thread.append(threading.get_ident())
                _ = ctx.on_stop(callback)
                ready.set()
                _ = called.wait(WAIT)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            _ = s.spawn(routine)
            assert ready.wait(WAIT)
            s.stop()
            s.stop()

        with Phase.VERIFY:
            assert len(calls) == 1
            assert calls[0] not in (threading.get_ident(), routine_thread[0])

    @upholds(ContextContract.on_stop.CalledInRegistrationOrder)
    def test_called_in_registration_order(self) -> None:
        with Phase.PREPARE:
            ready = threading.Event()
            last_called = threading.Event()
            order: list[int] = []

            def routine(ctx: gpframe.Context) -> None:
                _ = ctx.on_stop(lambda: order.append(1))
                _ = ctx.on_stop(lambda: order.append(2))
                _ = ctx.on_stop(lambda: (order.append(3), last_called.set()))
                ready.set()
                _ = last_called.wait(WAIT)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            _ = s.spawn(routine)
            assert ready.wait(WAIT)
            s.stop()

        with Phase.VERIFY:
            assert order == [1, 2, 3]

    @upholds(ContextContract.on_stop.RegisteredAfterStopIsCalled)
    def test_registered_after_stop_is_called(self) -> None:
        with Phase.PREPARE:

            def routine(ctx: gpframe.Context) -> bool:
                assert ctx.wait_stop(WAIT)
                called = threading.Event()
                _ = ctx.on_stop(called.set)
                return called.wait(WAIT)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(routine)
            s.stop()

        with Phase.VERIFY:
            assert frame.result() is True


@binds[Session](gpframe.Session)
class TestStop:
    @upholds(SessionContract.stop.DoesNotWaitForCallbacks)
    def test_stop_returns_while_callback_blocks(self, gate: threading.Event) -> None:
        with Phase.PREPARE:
            ready = threading.Event()
            started = threading.Event()

            def slow_callback() -> None:
                started.set()
                _ = gate.wait()

            def routine(ctx: gpframe.Context) -> None:
                _ = ctx.on_stop(slow_callback)
                ready.set()
                _ = gate.wait()

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            _ = s.spawn(routine)
            assert ready.wait(WAIT)
            began = time.monotonic()
            s.stop()
            elapsed = time.monotonic() - began
            assert started.wait(WAIT)
            gate.set()

        with Phase.VERIFY:
            assert elapsed < 1.0

    @upholds(SessionContract.stop.DoesNotWaitForCallbacks)
    def test_stop_from_inside_a_callback_does_not_deadlock(self) -> None:
        with Phase.PREPARE:
            ready = threading.Event()
            done = threading.Event()

            def routine(ctx: gpframe.Context, s: gpframe.Session) -> None:
                _ = ctx.on_stop(lambda: (s.stop(), done.set()))
                ready.set()
                _ = done.wait(WAIT)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(routine, s)
            assert ready.wait(WAIT)
            s.stop()

        with Phase.VERIFY:
            assert done.is_set()
            assert frame.succeeded

    @upholds(SessionContract.stop.WorksInAnyState)
    def test_stop_before_open(self) -> None:
        with Phase.PREPARE:
            s = gpframe.session(strict=True)

        with Phase.MAIN:
            # 別のスレッドから、with に入る前に止められた場合と同じ。
            stopper = threading.Thread(target=s.stop)
            stopper.start()
            stopper.join()
            with s:
                stopping = s.stopping
                frame = s.spawn(until_stopped)
            s.stop()  # 閉じた後に呼んでもよい

        with Phase.VERIFY:
            assert stopping is True
            assert frame.stopped


@binds[Frame[object]](gpframe.Frame)
class TestCallbacksAndFrameLifetime:
    @upholds(FrameContract.NoCallbacksAfterRoutineReturns)
    def test_no_callback_after_routine_returns(self) -> None:
        with Phase.PREPARE:
            called = threading.Event()

            def routine(ctx: gpframe.Context) -> None:
                _ = ctx.on_stop(called.set)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(routine)
            _ = frame.result(WAIT)
            s.stop()
            time.sleep(0.1)

        with Phase.VERIFY:
            assert not called.is_set()

    @upholds(FrameContract.WaitsForRunningCallback)
    def test_frame_waits_for_running_callback(self, gate: threading.Event) -> None:
        with Phase.PREPARE:
            callback_started = threading.Event()
            returned = threading.Event()

            def callback() -> None:
                callback_started.set()
                _ = gate.wait()

            def routine(ctx: gpframe.Context) -> str:
                _ = ctx.on_stop(callback)
                assert callback_started.wait(WAIT) if ctx.wait_stop(WAIT) else False
                returned.set()
                return "returned"

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(routine)
            s.stop()
            assert returned.wait(WAIT)
            time.sleep(0.05)
            still_running = frame.running
            gate.set()

        with Phase.VERIFY:
            assert still_running
            assert frame.result() == "returned"

    @upholds(FrameContract.CallbackErrorsBreakFrame)
    def test_callback_error_breaks_frame(self) -> None:
        with Phase.PREPARE:
            raised = threading.Event()
            frames: list[gpframe.Frame[object]] = []

            def bad_callback() -> None:
                raised.set()
                raise ValueError("shutdown failed")

            def routine(ctx: gpframe.Context) -> str:
                _ = ctx.on_stop(bad_callback)
                _ = raised.wait(WAIT) if ctx.wait_stop(WAIT) else None
                return "returned"

        with (
            Phase.MAIN,
            pytest.raises(gpframe.SessionFailed) as caught,
            gpframe.session(timeout=WAIT) as s,
        ):
            frames.append(s.spawn(routine))
            s.stop()
            for frame in s.wait_broken(WAIT):
                frame.escalate()

        with Phase.VERIFY:
            frame = frames[0]
            assert frame.error is None
            assert frame.result() == "returned"
            assert [type(e) for e in frame.stop_errors] == [ValueError]
            assert caught.value.exceptions == (frame.stop_errors[0],)


@binds[StopHandle](gpframe.StopHandle)
class TestStopHandle:
    @upholds(StopHandleContract.cancel.PreventsLaterCall)
    def test_cancelled_callback_is_not_called(self) -> None:
        with Phase.PREPARE:
            cancelled_called = threading.Event()
            other_called = threading.Event()
            ready = threading.Event()

            def routine(ctx: gpframe.Context) -> None:
                handle = ctx.on_stop(cancelled_called.set)
                _ = ctx.on_stop(other_called.set)
                handle.cancel()
                ready.set()
                _ = other_called.wait(WAIT) if ctx.wait_stop(WAIT) else None

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            _ = s.spawn(routine)
            # 停止の後の登録はすぐ呼ばれる(STOP_012)ので、取り消しが済んでから止める。
            assert ready.wait(WAIT)
            s.stop()

        with Phase.VERIFY:
            assert other_called.is_set()
            assert not cancelled_called.is_set()

    @upholds(StopHandleContract.cancel.PreventsLaterCall)
    def test_cancel_after_call_does_nothing(self) -> None:
        with Phase.PREPARE:
            calls: list[str] = []
            called = threading.Event()

            def routine(ctx: gpframe.Context) -> int:
                handle = ctx.on_stop(lambda: (calls.append("x"), called.set()))
                _ = called.wait(WAIT) if ctx.wait_stop(WAIT) else None
                handle.cancel()
                handle.cancel()
                return len(calls)

        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            frame = s.spawn(routine)
            s.stop()

        with Phase.VERIFY:
            assert frame.result() == 1


@binds[Session](gpframe.Session)
class TestWaitBroken:
    @upholds(SessionContract.wait_broken.ReturnsOnFirstFailure)
    def test_returns_on_first_failure(self) -> None:
        with Phase.MAIN, gpframe.session(timeout=WAIT) as s:
            long_running = s.spawn(until_stopped)
            failing = s.spawn(fail)
            failed = s.wait_broken(WAIT)
            still_running = long_running.running
            failing.ignore()
            s.stop()

        with Phase.VERIFY:
            assert failed == [failing]
            assert still_running

    @upholds(SessionContract.wait_broken.ReturnsEmptyWithoutFailure)
    def test_returns_empty_when_all_succeed(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            _ = s.spawn(succeed)
            _ = s.spawn(succeed)
            failed = s.wait_broken()
            running = s.running()

        with Phase.VERIFY:
            assert failed == []
            assert not running

    @upholds(SessionContract.wait_broken.ReturnsEmptyWithoutFailure)
    def test_returns_empty_on_timeout(self, gate: threading.Event) -> None:
        with Phase.MAIN, gpframe.session() as s:
            _ = s.spawn(blocked, gate)
            failed = s.wait_broken(0.05)
            running = s.running()
            gate.set()

        with Phase.VERIFY:
            assert failed == []
            assert running

    @upholds(SessionContract.wait_broken.DoesNotAcknowledge)
    def test_failure_is_returned_until_acknowledged(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(fail)
            first = s.wait_broken(WAIT)
            second = s.wait_broken(WAIT)
            frame.ignore()
            after = s.wait_broken(WAIT)

        with Phase.VERIFY:
            assert first == second == [frame]
            assert after == []
