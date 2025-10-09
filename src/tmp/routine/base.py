from abc import ABC, abstractmethod

from typing import Any, Callable, Coroutine

from gpframe._impl.routine.result import _NO_VALUE

SyncRoutineResultWaitFn = Callable[
    [float | None],
    tuple[Any | type[_NO_VALUE], Exception | None]
]

AsyncRoutineResultWaitFn = Callable[
    [float | None],
    Coroutine[Any, Any, tuple[Any | type[_NO_VALUE], Exception | None]]
]


class RoutineExecution(ABC):
    __slots__ = ()
    
    @abstractmethod
    def load_routine(self, routine, context) -> None:
        ...
    
    @abstractmethod
    def get_wait_routine_result_fn(self) -> SyncRoutineResultWaitFn | AsyncRoutineResultWaitFn:
        ...

class IntraProcessRoutineExecution(RoutineExecution):
    @abstractmethod
    def request_stop_routine(self):
        ...

class IPCRoutineExecution(RoutineExecution):
    @abstractmethod
    def request_stop_routine(self, kill: bool):
        ...

