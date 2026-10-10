"""セッション、フレーム、コンテキストの契約に対するテスト。

`pytest.raises` は例外を握るので、その中で起動したフレームは外で用意した
リストに入れて受け取る。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import pytest
from shikumi_contrace import Phase, binds, upholds, violates

import gpframe
from contract.ports.surface import Context, Frame, Session
from contract.session_contract import ContextContract, FrameContract, SessionContract
from tests.conftest import blocked, fail, succeed, until_stopped

Frames = list[gpframe.Frame[object]]

# 実装が公開 API の形を満たすことの静的な確認。
# `@binds[...]` の引数の型 `T | Callable[..., T]` では、basedpyright 1.40.2 が
# クラスオブジェクトと Protocol を比べた途中結果を誤って再利用し、相互に参照し合う
# Context と Session の適合を失敗と判定することがある。binds より先にここで
# インスタンスの形として確かめておくと、その誤判定が起きない。
_CONTEXT_SHAPE: Callable[..., Context] = gpframe.Context
_SESSION_SHAPE: Callable[..., Session] = gpframe.Session
_FRAME_SHAPE: Callable[..., Frame[object]] = gpframe.Frame


@binds[Session](gpframe.Session)
class TestSessionExit:
    @upholds(SessionContract.UnacknowledgedFailuresSurface)
    def test_unmarked_failure_warns(self) -> None:
        with (
            Phase.MAIN,
            pytest.warns(gpframe.FrameWarning, match="not acknowledged"),
            gpframe.session() as s,
        ):
            frame = s.spawn(fail)

        with Phase.VERIFY:
            assert isinstance(frame.error, ValueError)

    @upholds(SessionContract.IgnoredFailuresAreSilent)
    def test_ignored_failure_is_silent(self) -> None:
        # filterwarnings = error なので、警告が出ればこのテストは失敗する。
        with Phase.MAIN, gpframe.session() as s:
            _ = s.spawn(fail)
            _ = s.wait()
            for frame in s.broken():
                frame.ignore()

        with Phase.VERIFY:
            assert s.broken() == []

    @upholds(SessionContract.EscalatedFailuresRaise)
    @upholds(SessionContract.UnacknowledgedFailuresSurface)
    def test_escalated_failure_raises(self) -> None:
        with Phase.PREPARE:
            frames: Frames = []

        with (
            Phase.MAIN,
            pytest.raises(gpframe.SessionFailed) as caught,
            gpframe.session() as s,
        ):
            frames.append(s.spawn(fail, "bad input"))
            _ = s.wait()
            s.broken()[0].escalate("parser crashed")

        with Phase.VERIFY:
            group = caught.value
            assert group.frames == tuple(frames)
            assert len(group.exceptions) == 1
            assert isinstance(group.exceptions[0], ValueError)
            assert "parser crashed" in group.message

    @upholds(SessionContract.StrictRaisesUnmarkedFailures)
    @upholds(SessionContract.UnacknowledgedFailuresSurface)
    def test_strict_raises_unmarked_failure(self) -> None:
        with Phase.PREPARE:
            frames: Frames = []

        with (
            Phase.MAIN,
            pytest.raises(gpframe.SessionFailed) as caught,
            gpframe.session(strict=True) as s,
        ):
            frames.append(s.spawn(fail))

        with Phase.VERIFY:
            assert caught.value.frames == tuple(frames)

    @upholds(SessionContract.ExitWaitIsBounded)
    def test_exit_does_not_wait_beyond_timeout(self, gate: threading.Event) -> None:
        with Phase.PREPARE:
            seen_stop = threading.Event()

            def ignores_stop(ctx: gpframe.Context) -> None:
                _ = gate.wait()
                if ctx.stopping:
                    seen_stop.set()

            started = time.monotonic()

        with (
            Phase.MAIN,
            pytest.warns(gpframe.FrameWarning, match="did not stop"),
            gpframe.session(timeout=0.1) as s,
        ):
            frame = s.spawn(ignores_stop)

        with Phase.VERIFY:
            assert time.monotonic() - started < 2.0
            assert frame.running
            assert s.stopping
            gate.set()
            _ = frame.result(timeout=2.0)
            assert seen_stop.is_set()

    @upholds(SessionContract.BodyErrorRequestsStop)
    def test_error_in_body_requests_stop(self) -> None:
        with Phase.PREPARE:
            frames: Frames = []

        with (
            Phase.MAIN,
            pytest.raises(RuntimeError, match="body failed"),
            gpframe.session(timeout=5) as s,
        ):
            frames.append(s.spawn(until_stopped))
            raise RuntimeError("body failed")

        with Phase.VERIFY:
            assert frames[0].succeeded
            assert frames[0].result() == "stopped"


@binds[Session](gpframe.Session)
class TestSubSessions:
    @upholds(SessionContract.StopReachesSubSessions)
    def test_stop_reaches_open_sub_session(self) -> None:
        with Phase.PREPARE:
            sub_started = threading.Event()

            def parent(ctx: gpframe.Context) -> str:
                with ctx.session(timeout=5) as sub:
                    child = sub.spawn(until_stopped)
                    sub_started.set()
                    _ = sub.wait()
                return child.result()

        with Phase.MAIN, gpframe.session(timeout=5) as s:
            frame = s.spawn(parent)
            assert sub_started.wait(5)
            s.stop()

        with Phase.VERIFY:
            assert frame.result() == "stopped"

    @upholds(SessionContract.StopReachesSubSessions)
    def test_stop_reaches_sub_session_opened_later(self) -> None:
        with Phase.PREPARE:

            def parent(ctx: gpframe.Context) -> bool:
                _ = ctx.wait_stop(5)
                with ctx.session() as sub:
                    return sub.stopping

        with Phase.MAIN, gpframe.session(timeout=5) as s:
            frame = s.spawn(parent)
            s.stop()

        with Phase.VERIFY:
            assert frame.result() is True

    @upholds(SessionContract.SubSessionReportsToOwner)
    def test_sub_session_reports_to_owner_frame(self) -> None:
        with Phase.PREPARE:
            failed_children: Frames = []

            def parent(ctx: gpframe.Context) -> int:
                # サブセッションの終了は、ここで警告も例外も出さない。
                with ctx.session() as sub:
                    failed_children.append(sub.spawn(fail))
                return 42

        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(parent)
            _ = s.wait()
            for broken in s.broken():
                broken.ignore()

        with Phase.VERIFY:
            report = frame.incomplete
            assert report is not None
            assert report.broken == tuple(failed_children)
            assert report.stuck == ()
            assert report.errors == ()


@binds[Session](gpframe.Session)
class TestSpawn:
    @upholds(SessionContract.spawn.SessionIsOpen)
    def test_open_session_accepts_work(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(succeed, 7)

        with Phase.VERIFY:
            assert frame.result() == 7

    @upholds(SessionContract.spawn.SpawnAfterStopIsStopped)
    def test_spawn_after_stop_returns_a_stopped_frame(self) -> None:
        called: list[str] = []

        def record(ctx: gpframe.Context) -> None:
            called.append(ctx.name)

        # filterwarnings = error なので、判定で警告が出ればこのテストは失敗する。
        with Phase.MAIN, gpframe.session(strict=True) as s:
            s.stop()
            frame = s.spawn(record)

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
            assert s.broken() == []
            with pytest.raises(gpframe.FrameStoppedError):
                _ = frame.result(0)
            with pytest.raises(gpframe.FrameStateError):
                frame.ignore()

    @upholds(SessionContract.spawn.SpawnAfterStopIsStopped)
    def test_spawn_in_a_stopped_sub_session_is_not_a_failure(self) -> None:
        # 停止を受けて正常に終わった仕事の後で、次の仕事を起動しようとする形。
        gate = threading.Event()

        def owner(ctx: gpframe.Context) -> bool:
            _ = gate.wait(5)
            with ctx.session() as sub:
                late = sub.spawn(succeed)
            return late.stopped

        with Phase.MAIN, gpframe.session(strict=True) as s:
            frame = s.spawn(owner)
            s.stop()
            gate.set()

        with Phase.VERIFY:
            assert frame.succeeded
            assert frame.result() is True

    @violates(SessionContract.spawn.SessionIsOpen)
    def test_spawn_outside_with_is_rejected(self) -> None:
        with Phase.PREPARE:
            s = gpframe.session()

        with Phase.MAIN:
            with pytest.raises(gpframe.SessionStateError):
                _ = s.spawn(succeed)
            with s:
                pass
            with pytest.raises(gpframe.SessionStateError):
                _ = s.spawn(succeed)

        with Phase.VERIFY:
            assert not s.running()


@binds[Session](gpframe.Session)
class TestBroken:
    @upholds(SessionContract.broken.ReturnsOnlyUnacknowledged)
    def test_returns_only_unacknowledged_failures(self, gate: threading.Event) -> None:
        with Phase.MAIN, gpframe.session() as s:
            _ = s.spawn(succeed)
            first = s.spawn(fail, "first")
            second = s.spawn(fail, "second")
            running = s.spawn(blocked, gate)
            while first.running or second.running:
                time.sleep(0.01)
            before = s.broken()
            first.ignore()
            after = s.broken()
            second.ignore()
            gate.set()

        with Phase.VERIFY:
            assert before == [first, second]
            assert after == [second]
            assert running.result() == "released"


@binds[Frame[object]](gpframe.Frame)
class TestFrame:
    @upholds(FrameContract.IncompleteSessionBreaksFrame)
    def test_incomplete_sub_session_breaks_frame(self) -> None:
        with Phase.PREPARE:
            frames: Frames = []
            broken: Frames = []

            def parent(ctx: gpframe.Context) -> int:
                with ctx.session() as sub:
                    _ = sub.spawn(fail)
                return 42

        with (
            Phase.MAIN,
            pytest.raises(gpframe.SessionFailed) as caught,
            gpframe.session() as s,
        ):
            frames.append(s.spawn(parent))
            _ = s.wait()
            broken.extend(s.broken())
            for each in broken:
                each.escalate()

        with Phase.VERIFY:
            frame = frames[0]
            assert broken == [frame]
            assert not frame.succeeded
            assert frame.error is None
            assert frame.result() == 42
            error = caught.value.exceptions[0]
            assert isinstance(error, gpframe.IncompleteSessionError)
            assert error.report == frame.incomplete

    @upholds(FrameContract.result.WaitsForCompletion)
    def test_result_waits_and_returns_value(self) -> None:
        with Phase.PREPARE:

            def slow(ctx: gpframe.Context) -> str:
                time.sleep(0.05)
                return "done"

        with Phase.MAIN, gpframe.session() as s:
            value = s.spawn(slow).result()

        with Phase.VERIFY:
            assert value == "done"

    @upholds(FrameContract.result.WaitsForCompletion)
    def test_result_reraises_routine_error(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(fail, "from routine")
            with pytest.raises(ValueError, match="from routine"):
                _ = frame.result()
            frame.ignore()

        with Phase.VERIFY:
            assert isinstance(frame.error, ValueError)

    @upholds(FrameContract.result.WaitsForCompletion)
    def test_result_times_out(self, gate: threading.Event) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(blocked, gate)
            with pytest.raises(TimeoutError):
                _ = frame.result(timeout=0.05)
            gate.set()

        with Phase.VERIFY:
            assert frame.result() == "released"

    @upholds(FrameContract.result.DoesNotAcknowledge)
    def test_result_does_not_acknowledge(self) -> None:
        with Phase.PREPARE:

            def scenario() -> tuple[gpframe.Frame[int], Frames]:
                with gpframe.session() as s:
                    frame = s.spawn(fail)
                    with pytest.raises(ValueError):
                        _ = frame.result()
                    return frame, list(s.broken())

        with (
            Phase.MAIN,
            pytest.warns(gpframe.FrameWarning, match="not acknowledged"),
        ):
            frame, remaining = scenario()

        with Phase.VERIFY:
            assert remaining == [frame]

    @upholds(FrameContract.ignore.OnlyUnacknowledgedFailures)
    @upholds(FrameContract.escalate.OnlyUnacknowledgedFailures)
    def test_failed_frame_can_be_acknowledged(self) -> None:
        with Phase.PREPARE:
            s = gpframe.session()

        with Phase.MAIN, pytest.raises(gpframe.SessionFailed), s:
            ignored = s.spawn(fail)
            escalated = s.spawn(fail)
            _ = s.wait()
            ignored.ignore()
            escalated.escalate()

        with Phase.VERIFY:
            assert s.broken() == []

    @violates(FrameContract.ignore.OnlyUnacknowledgedFailures)
    @violates(FrameContract.escalate.OnlyUnacknowledgedFailures)
    def test_succeeded_frame_is_rejected(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(succeed)
            _ = s.wait()
            with pytest.raises(gpframe.FrameStateError, match="did not fail"):
                frame.ignore()
            with pytest.raises(gpframe.FrameStateError, match="did not fail"):
                frame.escalate()

        with Phase.VERIFY:
            assert frame.succeeded

    @violates(FrameContract.ignore.OnlyUnacknowledgedFailures)
    @violates(FrameContract.escalate.OnlyUnacknowledgedFailures)
    def test_running_frame_is_rejected(self, gate: threading.Event) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(blocked, gate)
            with pytest.raises(gpframe.FrameStateError, match="still running"):
                frame.ignore()
            with pytest.raises(gpframe.FrameStateError, match="still running"):
                frame.escalate()
            gate.set()

        with Phase.VERIFY:
            assert frame.succeeded

    @violates(FrameContract.ignore.OnlyUnacknowledgedFailures)
    @violates(FrameContract.escalate.OnlyUnacknowledgedFailures)
    def test_acknowledged_frame_is_rejected(self) -> None:
        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(fail)
            _ = s.wait()
            frame.ignore()
            with pytest.raises(gpframe.FrameStateError, match="already"):
                frame.ignore()
            with pytest.raises(gpframe.FrameStateError, match="already"):
                frame.escalate()

        with Phase.VERIFY:
            assert s.broken() == []


@binds[Context](gpframe.Context)
class TestContext:
    @upholds(ContextContract.wait_stop.WakesOnStop)
    def test_wait_stop_wakes_on_stop(self) -> None:
        with Phase.PREPARE:
            waiting = threading.Event()

            def sleeper(ctx: gpframe.Context) -> tuple[bool, float]:
                waiting.set()
                started = time.monotonic()
                woke = ctx.wait_stop(10)
                return woke, time.monotonic() - started

        with Phase.MAIN, gpframe.session(timeout=5) as s:
            frame = s.spawn(sleeper)
            assert waiting.wait(5)
            s.stop()

        with Phase.VERIFY:
            woke, elapsed = frame.result()
            assert woke is True
            assert elapsed < 5

    @upholds(ContextContract.wait_stop.WakesOnStop)
    def test_wait_stop_times_out(self) -> None:
        with Phase.PREPARE:

            def sleeper(ctx: gpframe.Context) -> bool:
                return ctx.wait_stop(0.01)

        with Phase.MAIN, gpframe.session() as s:
            frame = s.spawn(sleeper)

        with Phase.VERIFY:
            assert frame.result() is False
