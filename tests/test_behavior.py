"""契約にするほどではない、普通の振る舞いのテスト。"""

from __future__ import annotations

import asyncio
import functools
import threading
from dataclasses import dataclass, replace

import pytest

import gpframe
from tests.conftest import blocked, fail, succeed


class TestRoutines:
    def test_arguments_are_passed_after_context(self) -> None:
        def add(ctx: gpframe.Context, a: int, b: int) -> int:
            return a + b

        with gpframe.session() as s:
            frame = s.spawn(add, 2, 3)

        assert frame.result() == 5

    def test_async_routine_runs_in_its_own_loop(self) -> None:
        async def work(ctx: gpframe.Context, n: int) -> int:
            await asyncio.sleep(0.01)
            return n * 2

        with gpframe.session() as s:
            frame = s.spawn(work, 21)

        assert frame.result() == 42

    def test_context_carries_the_frame_name(self) -> None:
        def who(ctx: gpframe.Context) -> str:
            return ctx.name

        with gpframe.session() as s:
            default = s.spawn(who)
            named = s.spawn(who, name="worker-1")

        assert default.result() == "who"
        assert named.result() == "worker-1"

    def test_name_falls_back_to_type_name(self) -> None:
        with gpframe.session() as s:
            frame = s.spawn(functools.partial(succeed, value=3))

        assert frame.name == "partial"
        assert frame.result() == 3


class TestSessionLifecycle:
    def test_wait_reports_whether_frames_finished(self, gate: threading.Event) -> None:
        with gpframe.session() as s:
            _ = s.spawn(blocked, gate)
            assert s.running()
            assert s.wait(timeout=0.05) is False
            gate.set()
            assert s.wait(timeout=5) is True
            assert not s.running()

    def test_session_can_be_entered_only_once(self) -> None:
        s = gpframe.session()
        with s:
            pass
        with pytest.raises(gpframe.SessionStateError), s:
            pass

    def test_negative_timeout_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            _ = gpframe.session(timeout=-1)

    def test_frame_repr_shows_state(self, gate: threading.Event) -> None:
        with gpframe.session() as s:
            running = s.spawn(blocked, gate)
            assert "running" in repr(running)
            gate.set()
            ok = s.spawn(succeed)
            bad = s.spawn(fail)
            _ = s.wait()
            bad.ignore()

        assert "succeeded" in repr(ok)
        assert "broken" in repr(bad)


class TestFailures:
    def test_session_failed_supports_except_star(self) -> None:
        def type_error(ctx: gpframe.Context) -> None:
            raise TypeError("wrong")

        caught: list[BaseException] = []
        try:
            with gpframe.session() as s:
                _ = s.spawn(fail)
                _ = s.spawn(type_error)
                _ = s.wait()
                for frame in s.broken():
                    frame.escalate()
        except* ValueError as group:
            caught.extend(group.exceptions)
        except* TypeError as group:
            caught.extend(group.exceptions)

        assert sorted(type(e).__name__ for e in caught) == ["TypeError", "ValueError"]

    def test_split_keeps_the_matching_frames(self) -> None:
        def type_error(ctx: gpframe.Context) -> None:
            raise TypeError("wrong")

        frames: list[gpframe.Frame[object]] = []
        with pytest.raises(gpframe.SessionFailed) as caught, gpframe.session() as s:
            frames.append(s.spawn(fail))
            frames.append(s.spawn(type_error))
            _ = s.wait()
            for frame in s.broken():
                frame.escalate()

        value_frame, type_frame = frames
        matched, rest = caught.value.split(ValueError)
        assert isinstance(matched, gpframe.SessionFailed)
        assert isinstance(rest, gpframe.SessionFailed)
        assert matched.frames == (value_frame,)
        assert rest.frames == (type_frame,)

    def test_session_failed_keeps_spawn_order_in_strict_mode(self) -> None:
        frames: list[gpframe.Frame[object]] = []
        with (
            pytest.raises(gpframe.SessionFailed) as caught,
            gpframe.session(strict=True) as s,
        ):
            frames.append(s.spawn(fail, "unmarked"))
            frames.append(s.spawn(fail, "escalated"))
            _ = s.wait()
            frames[1].escalate()

        assert caught.value.frames == tuple(frames)

    def test_base_exception_is_wrapped(self) -> None:
        def interrupted(ctx: gpframe.Context) -> None:
            raise KeyboardInterrupt

        with pytest.raises(gpframe.SessionFailed) as caught, gpframe.session() as s:
            frame = s.spawn(interrupted)
            _ = s.wait()
            frame.escalate()

        error = caught.value.exceptions[0]
        assert isinstance(error, gpframe.FrameAbortedError)
        assert isinstance(error.__cause__, KeyboardInterrupt)

    def test_base_exception_from_stop_callback_is_wrapped(self) -> None:
        raised = threading.Event()

        def interrupt() -> None:
            raised.set()
            raise KeyboardInterrupt

        def routine(ctx: gpframe.Context) -> None:
            _ = ctx.on_stop(interrupt)
            _ = raised.wait(5) if ctx.wait_stop(5) else None

        frames: list[gpframe.Frame[None]] = []
        with pytest.raises(gpframe.SessionFailed) as caught, gpframe.session() as s:
            frames.append(s.spawn(routine))
            s.stop()
            for each in s.wait_broken(5):
                each.escalate()

        error = caught.value.exceptions[0]
        assert isinstance(error, gpframe.FrameAbortedError)
        assert error.__cause__ is frames[0].stop_errors[0]

    def test_failed_session_has_body_error_as_context(self) -> None:
        with pytest.raises(gpframe.SessionFailed) as caught, gpframe.session() as s:
            frame = s.spawn(fail)
            _ = s.wait()
            frame.escalate()
            raise RuntimeError("body")

        assert isinstance(caught.value.__context__, RuntimeError)

    def test_reports_of_several_sub_sessions_are_merged(self) -> None:
        def parent(ctx: gpframe.Context) -> None:
            for _ in range(2):
                with ctx.session() as sub:
                    _ = sub.spawn(fail)

        with gpframe.session() as s:
            frame = s.spawn(parent)
            _ = s.wait()
            frame.ignore()

        report = frame.incomplete
        assert report is not None
        assert len(report.broken) == 2

    def test_error_in_sub_session_body_is_reported_and_reraised(self) -> None:
        def parent(ctx: gpframe.Context) -> None:
            with ctx.session():
                raise RuntimeError("inside sub")

        with gpframe.session() as s:
            frame = s.spawn(parent)
            _ = s.wait()
            frame.ignore()

        assert isinstance(frame.error, RuntimeError)
        report = frame.incomplete
        assert report is not None
        assert isinstance(report.errors[0], RuntimeError)


@dataclass(frozen=True)
class Progress:
    done: int
    failed: int


class TestShared:
    def test_swap_returns_previous_value(self) -> None:
        cell = gpframe.Shared(str, "a")
        assert cell.swap("b") == "a"
        assert cell.get() == "b"

    def test_apply_keeps_value_when_fn_raises(self) -> None:
        cell = gpframe.Shared(int, 1)

        def explode(n: int) -> int:
            raise RuntimeError("no")

        with pytest.raises(RuntimeError):
            _ = cell.apply(explode)
        assert cell.get() == 1

    def test_frozen_dataclass_keeps_values_consistent(self) -> None:
        progress = gpframe.Shared(Progress, Progress(0, 0))
        result = progress.apply(lambda p: replace(p, done=p.done + 1))
        assert result == Progress(1, 0)
        assert progress.type is Progress

    def test_subclass_instance_is_accepted(self) -> None:
        cell = gpframe.Shared(int, 0)
        cell.set(True)
        assert cell.get() is True

    def test_type_expressions_and_none_type_are_rejected(self) -> None:
        with pytest.raises(gpframe.DeclaredTypeError):
            _ = gpframe.Shared(list[int], [1])
        with pytest.raises(gpframe.DeclaredTypeError):
            _ = gpframe.Shared(type(None), None)

    def test_repr(self) -> None:
        assert repr(gpframe.Shared(int, 3)) == "Shared(int, 3)"
