from __future__ import annotations

from enum import Enum
import threading
from typing import Any, Callable

from gpframe.contracts.api import routine, _T, _D, _NO_DEFAULT

from gpframe.exceptions import RoutineResultTypeError, RoutineResultMissingError

class _NO_VALUE(Enum):
    _ = "dummy"

class RoutineResultSource():
    __slots__ = ("_phase_validator", "_lock", "_routine_result", "_routine_error", "_interface")
    def __init__(self, lock: threading.Lock, phase_validator: Callable[[], None]):
        self._phase_validator = phase_validator
        self._lock = lock
        self._routine_result = _NO_VALUE
        self._routine_error = None
        self._interface = self._create_interface()
    
    def _create_interface(self) -> routine.Result:
        outer = self
        class _Reader(routine.Result):
            __slots__ = ()
            def get(self, typ: type[_T]) -> _T:
                outer._phase_validator()
                routine_result = _NO_VALUE
                with outer._lock:
                    routine_result = outer._routine_result
                if routine_result is _NO_VALUE:
                    raise RoutineResultMissingError
                if not isinstance(routine_result, typ):
                    raise RoutineResultTypeError
                return routine_result

            def getd(self, typ: type[_T], default: _D = _NO_DEFAULT) -> _T | _D:
                outer._phase_validator()
                routine_result = _NO_VALUE
                with outer._lock:
                    routine_result = outer._routine_result
                if routine_result is not _NO_VALUE:
                    if not isinstance(routine_result, typ):
                        raise RoutineResultTypeError
                    return routine_result
                elif default is not _NO_DEFAULT:
                    return default
                else:
                    raise RoutineResultMissingError

            def geta(self, default: Any = _NO_DEFAULT) -> Any:
                outer._phase_validator()
                routine_result = _NO_VALUE
                with outer._lock:
                    routine_result = outer._routine_result
                if routine_result is not _NO_VALUE:
                    return routine_result
                elif default is not _NO_DEFAULT:
                    return default
                else:
                    raise RoutineResultMissingError

            @property
            def error(self) -> Exception | None:
                outer._phase_validator()
                with outer._lock:
                    return outer._routine_error

        return _Reader()
    
    @property
    def interface(self) -> routine.Result:
        return self._interface
    
    def set(self, result: Any, exc: Exception | None) -> None:
        with self._lock:
            self._routine_result = result
            self._routine_error = exc

