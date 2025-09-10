
from logging import Logger
from threading import Lock
from typing import Any, Literal

from ...api.contexts import RoutineContext

from ..errors import HandledError
from .result import NO_VALUE

from .base import RoutineExecution
from .errors import ExecutionError


class SyncRoutine(RoutineExecution):
    __slots__ = ("_lock", "_routine", "_context")
    def __init__(self, frame_name: str, logger: Logger):
        self._lock = Lock()
        self._routine = None
        self._context = None
    
    def get_shared_lock(self) -> Lock:
        try:
            return self._lock
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e

    def get_shared_map_factory(self) -> type[dict]:
        return dict
    
    def load_routine(self, frame_name: str, logger: Logger, routine, context: RoutineContext) -> None:
        try:
            with self._lock:
                self._routine = routine
                self._context = context
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def wait_routine_result(self, frame_name: str, logger: Logger, timeout: float | None = None) -> tuple[Any | NO_VALUE, Exception | None]:
        try:
            try:
                assert self._routine
                assert self._context
                result = self._routine(self._context), None
            except Exception as e:
                result = NO_VALUE, e
            finally:
                with self._lock:
                    self._routine = None
                    self._context = None
            return result
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def routine_is_running(self) -> bool:
        try:
            with self._lock:
                return self._routine is not None
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    
    def request_stop_routine(self, frame_name: str, logger: Logger, timeout: float | None = None, **kwargs) -> None:
        return
    
    def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
        try:
            self._routine = None
            self._context = None
        except Exception as e:
            if isinstance(e, (HandledError, AssertionError)):
                raise
            else:
                raise ExecutionError(e) from e
    