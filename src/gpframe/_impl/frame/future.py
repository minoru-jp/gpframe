from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable

from gpframe.contracts.protocols import FrameFuture
from gpframe.contracts.exceptions import FrameFutureAggregateError
from gpframe._impl.frame.circuit import circuit

from gpframe._impl.frame.frame_base import _FrameBaseState as FrameBaseState

class FrameFutureImpl:
    def __init__(
            self,
            frame_name: str,
            frame_lock: threading.Lock,
            wait_targets_getter: Callable[[], tuple[Any, ...]] | None = None):
        self.frame_name = frame_name
        self.lock = frame_lock
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.future_is_ready = threading.Event()
        self.circuit_error: BaseException | None = None
        self.circuit_is_ended = threading.Event()
        self.wait_targets_getter = wait_targets_getter if wait_targets_getter else lambda: (self,)
    
    def cancel(self):
        with self.lock:
            if self.future_is_ready.is_set():
                assert self.task is not None
                assert self.thread is not None
                if not self.task.done() and self.thread.is_alive():
                    assert self.loop is not None
                    self.loop.call_soon_threadsafe(self.task.cancel)
    
    @staticmethod
    def _wait_target_futures(
        *frame_futures: FrameFutureImpl,
        timeout: float | None = None,
        raises: bool = True,
    ) -> dict[str, BaseException | None]:
        errors = {}
        deadline = None if timeout is None else time.monotonic() + timeout
        for f in frame_futures:
            remaining = None if deadline is None else max(0, deadline - time.monotonic())
            error = f._wait_frame_done(timeout = remaining, raises = False)
            if error:
                errors[f.frame_name] = error
        if errors and raises:
            raise FrameFutureAggregateError(errors)
        return errors

    def _wait_frame_done(self, *, timeout: float | None = None, raises: bool = False) -> BaseException | None:
        assert self.thread is not None
        self.thread.join(timeout)
        if self.thread.is_alive():
            te = TimeoutError(
                f"{self.frame_name} did not finish within {timeout} seconds"
            )
            if raises:
                raise te
            return te
        if self.circuit_is_ended.is_set():
            if self.circuit_error and raises:
                raise self.circuit_error
        else:
            re = RuntimeError(
                f"{self.frame_name}: The thread has already terminated, "
                "but the circuit completion has not been detected.")
            if raises:
                raise re
            return re
    
    def wait_done(self, *, timeout: float | None = None, raises: bool = False) -> dict[str, BaseException | None]:
        self.circuit_is_ended.wait()
        wait_targets = self.wait_targets_getter()
        return self._wait_target_futures(*wait_targets, timeout = timeout, raises = raises)
    
    def processing(self):
        return not self.circuit_is_ended.is_set()


def run_circuit_in_thread(
        base: FrameBaseState, ectx, rctx, routine_execution, routine, wait_targets_getter = None
    ) -> FrameFutureImpl:
    frame_future_impl = FrameFutureImpl(base.frame_name, base.intra_frame_lock, wait_targets_getter)
    def worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        circuit_task = loop.create_task(
            circuit(base, ectx, rctx, routine_execution, routine)
        )
        frame_future_impl.loop = loop
        frame_future_impl.task = circuit_task
        frame_future_impl.thread = threading.current_thread()
        frame_future_impl.future_is_ready.set()
        try:
            loop.run_until_complete(circuit_task)
        except BaseException as e:
            frame_future_impl.circuit_error = e
        finally:
            def atomic_with_terminating():
                assert loop is not None
                loop.close()
            base.phase_role.interface.to_terminated(atomic_with_terminating)
            frame_future_impl.circuit_is_ended.set()

    thread = threading.Thread(target = worker)
    thread.start()
    frame_future_impl.future_is_ready.wait()
        
    return frame_future_impl

def wrap_to_interface(impl: FrameFutureImpl) -> FrameFuture:
    class FrameFutureInterface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return impl.frame_name
        
        def cancel(self):
            impl.cancel()

        def wait_done(self, *, timeout: float | None = None, raises: bool = False) -> dict[str, BaseException | None]:
            return impl.wait_done(timeout = timeout, raises = raises)
        
        def processing(self) -> bool:
            return impl.processing()
    
    return FrameFutureInterface()
