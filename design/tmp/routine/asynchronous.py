from __future__ import annotations

import asyncio
import inspect

from logging import Logger
import threading
from typing import Any


from gpframe.contracts.exceptions import RoutineTaskTimeoutError

from gpframe._impl.routine.base import (
    _NO_VALUE,
    IntraProcessRoutineExecution,
    SyncRoutineResultWaitFn,
    AsyncRoutineResultWaitFn
)

class AsyncRoutine(IntraProcessRoutineExecution):
    __slots__ = ("_lock", "_task", "_called_stop")
    def __init__(self, lock: threading.Lock):
        self._lock = lock
        self._task = None
        self._called_stop = False
    
    def load_routine(self, routine, context) -> None:
        with self._lock:
            self._called_stop = False
            if not inspect.iscoroutinefunction(routine):
                raise TypeError
            self._task = asyncio.create_task(routine(context))
    
    async def wait_routine_result(self, timeout: float | None = None) -> tuple[Any | _NO_VALUE, Exception | None]:
        if self._task is None:
            raise RuntimeError("routine is not loading")
        try:
            return await asyncio.wait_for(self._task, timeout), None
        except asyncio.TimeoutError as e:
            raise RoutineTaskTimeoutError(self._task, timeout if timeout is not None else -1.0) from e
        except Exception as e:
            return _NO_VALUE, e
        finally:
            with self._lock:
                self._task = None
    
    def get_wait_routine_result_fn(self) -> SyncRoutineResultWaitFn | AsyncRoutineResultWaitFn:
        return self.wait_routine_result
    
    def routine_is_running(self) -> bool:
        with self._lock:
            return bool(self._task and (self._task.done()))
    
    def request_stop_routine(self) -> None:
        assert self._lock
        with self._lock:
            if not self._called_stop:
                self._called_stop = True
                if self._task and not self._task.cancelled():
                    self._task.cancel()
            else:
                return
    
    def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
        pass
        