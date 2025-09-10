from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, EnumMeta
import threading
from typing import Any, Callable, TypeVar, Generic

from enum import Enum

R = TypeVar("R")

class NoValueMeta(EnumMeta):
    def __repr__(cls):
        return f"<{cls.__name__}>"
    
    def __bool__(cls):
        return False
    
    def __len__(cls):
        return 0
    
    def __iter__(cls):
        return iter(())


class NO_VALUE(Enum, metaclass = NoValueMeta):
    """
    Sentinel value for missing routine results.

    Note:
        This is defined as an Enum class, but is intended to be used directly
        as a sentinel value.
    
    This constant represents the absence of a routine return value. It is the
    initial value before a routine produces a result, and it remains unchanged
    in the following cases:

    - The routine has not yet executed
    - The routine was canceled
    - The routine was interrupted
    - The routine raised an exception

    By comparing a routine's return value with ``NO_VALUE``, callers can detect
    whether the routine produced a valid result.
    """

    _ = "Dummy member to prevent this class from being extended."


class RoutineResult(ABC, Generic[R]):
    __slots__ = ()
    @property
    @abstractmethod
    def value(self) -> R | type[NO_VALUE]:
        ...

    @property
    @abstractmethod
    def error(self) -> Exception | None:
        ...

class RoutineResultSource(Generic[R]):
    __slots__ = ("_validator", "_lock", "_routine_result", "_routine_error", "_interface")
    def __init__(self, lock: threading.Lock, validator: Callable[[], None]):
        self._validator = validator
        self._lock = lock
        self._routine_result: R | type[NO_VALUE] =  NO_VALUE
        self._routine_error = None
        self._interface = self._create_interface()
    
    def _create_interface(self) -> RoutineResult:
        outer = self
        class _Reader(RoutineResult):
            __slots__ = ()
            @property
            def value(self) -> R | type[NO_VALUE]:
                outer._validator()
                with outer._lock:
                    return outer._routine_result
            @property
            def error(self) -> Exception | None:
                outer._validator()
                with outer._lock:
                    return outer._routine_error
        return _Reader()
    
    @property
    def interface(self) -> RoutineResult[R]:
        return self._interface
    
    def set(self, result: R, exc: Exception | None) -> None:
        with self._lock:
            self._routine_result = result
            self._routine_error = exc
    
    def get_routine_result_unsafe(self):
        return self._routine_result
    
    def get_routine_error_unsafe(self):
        return self._routine_error
    
    def clear_routine_result_unsafe(self):
        self._routine_result = NO_VALUE
    
    def clear_routine_error_unsafe(self):
        self._routine_error = None



