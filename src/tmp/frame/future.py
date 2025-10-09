from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
import threading

from gpframe.contracts.protocols import RootFrameFuture, SubFrameFuture
from gpframe.contracts.exceptions import FrameAggregateError
from gpframe._impl.frame.circuit import circuit

from gpframe._impl.frame.frame_base import _FrameBaseState as FrameBaseState

class FrameError(Exception):
    def __init__(self, frame_name: str, cause: BaseException):
        self.frame_name = frame_name
        self.cause = cause
        message = f"frame [{frame_name}]"
        if cause:
            message += f": {type(cause).__name__}: {cause}"
        super().__init__(message)

class RootFrameError(FrameError):
    pass

class SubFrameError(FrameError):
    pass


@dataclass(slots = True, frozen = True, kw_only = True)
class FrameRunState:
    thread: threading.Thread
    loop: asyncio.AbstractEventLoop
    circuit_task: asyncio.Task

@dataclass(slots = True, kw_only = True)
class FrameExecutorImpl(ABC):
    frame_name: str

    lock: threading.Lock = field(default_factory = threading.Lock, init = False)
    run_state: FrameRunState | None = field(default = None, init = False)
    circuit_error: BaseException | None = field(default = None, init = False)
    future_is_ready: threading.Event = field(default_factory = threading.Event, init = False)
    circuit_is_ended: threading.Event = field(default_factory = threading.Event, init = False)
    
    def run_circuit_in_thread(self, frame_base: FrameBaseState, ectx, rctx, routine_execution, routine) -> None:
        def worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            circuit_task = loop.create_task(
                circuit(frame_base, ectx, rctx, routine_execution, routine)
            )
            circuit_exc = None
            run_state = FrameRunState(
                thread = threading.current_thread(),
                loop = loop,
                circuit_task = circuit_task,
            )
            self._start(run_state)
            try:
                loop.run_until_complete(circuit_task)
            except BaseException as e:
                circuit_exc = e
            finally:
                def atomic_with_terminating():
                    assert loop is not None
                    loop.close()
                frame_base.phase_role.interface.to_terminated(atomic_with_terminating)
                self._end(circuit_exc)

        thread = threading.Thread(target = worker, daemon = True)
        thread.start()
        self.future_is_ready.wait()
    

    def cancel(self):
        with self.lock:
            if self.run_state is not None:
                run_state = self.run_state
                if self.future_is_ready.is_set():
                    if not run_state.circuit_task.done() and run_state.thread.is_alive():
                        run_state.loop.call_soon_threadsafe(run_state.circuit_task.cancel)

    @abstractmethod
    def wait_done(self, *, timeout: float | None = None, raises: bool = False) -> None:
        ...
    
    @abstractmethod
    def processing(self) -> bool:
        ...
    
    @abstractmethod
    def _start(self, run_state: FrameRunState):
        # Thread-unsafe: caller must ensure synchronization
        if self.future_is_ready.is_set():
            raise RuntimeError
        self.run_state = run_state
        self.future_is_ready.set()

    @abstractmethod
    def _end(self, circuit_exc: BaseException | None):
        # Thread-unsafe: caller must ensure synchronization
        if self.circuit_is_ended.is_set():
            raise RuntimeError
        self.circuit_error = circuit_exc
        self.circuit_is_ended.set()



@dataclass(slots = True)
class RootFrameExecutorImpl(FrameExecutorImpl):
    started_sub_frame_count: int = field(default = 0, init = False)
    failed_frames: dict = field(default_factory = dict, init = False)
    interface: RootFrameFuture = field(init = False)

    def __post_init__(self):
        self.interface = self._create_interface()
    
    def wait_done(self, *, timeout: float | None = None) -> None:
        if not self.circuit_is_ended.wait(timeout):
            raise TimeoutError
        with self.lock:
            if self.circuit_error is not None or self.failed_frames:
                raise FrameAggregateError(self.frame_name, self.circuit_error, self.failed_frames)

    def processing(self) -> bool:
        with self.lock:
            return self.circuit_is_ended.is_set() and self.started_sub_frame_count == 0

    def raise_if(self) -> None:
        with self.lock:
            if self.failed_frames:
                sub_frame, exc = next(iter(self.failed_frames.items()))
                self.failed_frames.pop(sub_frame)
                raise SubFrameError(sub_frame, exc)

    
    def _start(self, run_state: FrameRunState):
        with self.lock:
            super()._start(run_state)

    def _end(self, circuit_exc: BaseException | None):
        with self.lock:
            super()._end(circuit_exc)

    def _on_start_sub_frame(self):
        with self.lock:
            if self.circuit_is_ended.is_set():
                raise RuntimeError
            self.started_sub_frame_count += 1
    
    def _on_end_sub_frame(self, frame_name: str, exc: BaseException | None):
        with self.lock:
            self.started_sub_frame_count -= 1
            if self.started_sub_frame_count < 0:
                raise RuntimeError
            
    def _create_interface(self) -> RootFrameFuture:
        outer = self
        class RootFrameFuture:
            __slots__ = ()
            @property
            def frame_name(self) -> str:
                return outer.frame_name
            
            def cancel(self):
                outer.cancel()

            def wait_done(self, *, timeout: float | None = None, raises: bool = False) -> None:
                return outer.wait_done(timeout = timeout)
            
            def processing(self) -> bool:
                return outer.processing()
            
            def raise_if(self):
                return outer.raise_if()
        
        return RootFrameFuture()


@dataclass(slots = True, kw_only = True)
class SubFrameExecutorImpl(FrameExecutorImpl):
    root: RootFrameExecutorImpl
    interface: SubFrameFuture = field(init = False)

    def __post_init__(self):
        self.interface = self._create_interface()
    
    def _start(self, run_state: FrameRunState):
        with self.lock:
            super()._start(run_state)
            self.root._on_start_sub_frame()

    def _end(self, circuit_exc: BaseException | None):
        with self.lock:
            super()._end(circuit_exc)
            self.root._on_end_sub_frame(self.frame_name, self.circuit_error)
    
    def wait_done(self, *, timeout: float | None = None) -> None:
        if not self.circuit_is_ended.wait(timeout):
            raise TimeoutError
        with self.lock:
            if self.circuit_error is not None:
                raise SubFrameError(self.frame_name, self.circuit_error)

    def processing(self):
        with self.lock:
            return self.circuit_is_ended.is_set()

    def _create_interface(self) -> SubFrameFuture:
        outer = self
        class SubFrameFuture:
            __slots__ = ()
            @property
            def frame_name(self) -> str:
                return outer.frame_name
            
            def cancel(self):
                outer.cancel()

            def wait_done(self, *, timeout: float | None = None) -> None:
                return outer.wait_done(timeout = timeout)
            
            def processing(self) -> bool:
                return outer.processing()
        
        return SubFrameFuture()
