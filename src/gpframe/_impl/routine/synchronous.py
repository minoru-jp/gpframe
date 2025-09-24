from __future__ import annotations

from threading import Lock
from typing import Any


from gpframe._impl.routine.base import (
    _NO_VALUE,
    IntraProcessRoutineExecution,
    SyncRoutineResultWaitFn,
    AsyncRoutineResultWaitFn
)

class SyncRoutine(IntraProcessRoutineExecution):
    __slots__ = ("_lock", "_routine", "_context")
    def __init__(self, lock: Lock):
        self._lock = lock
        self._routine = None
        self._context = None
    
    def load_routine(self, routine, context) -> None:
        with self._lock:
            self._routine = routine
            self._context = context
    
    def wait_routine_result(self, timeout: float | None = None) -> tuple[Any | _NO_VALUE, Exception | None]:
        # TODO: Run in a separate thread and apply timeout
        try:
            assert self._routine
            assert self._context
            result = self._routine(self._context), None
        except Exception as e:
            result = _NO_VALUE, e
        finally:
            with self._lock:
                self._routine = None
                self._context = None
        return result
    
    def get_wait_routine_result_fn(self) -> SyncRoutineResultWaitFn | AsyncRoutineResultWaitFn:
        return self.wait_routine_result
    
    def routine_is_running(self) -> bool:
        with self._lock:
            return self._routine is not None
    
    def request_stop_routine(self, timeout: float | None = None, **kwargs) -> None:
        return
    
    def cleanup(self, timeout: float | None = None) -> None:
        pass
    