from abc import ABC, abstractmethod
from logging import Logger
from threading import Lock
from typing import Any, Callable, Coroutine, Generic, TypeVar

from ...api.contexts import RoutineContext

from .result import NO_VALUE

R = TypeVar("R")

SyncWaitFn = Callable[
    [str, Logger, float | None],
    tuple[Any | type[NO_VALUE], Exception | None]
]

AsyncWaitFn = Callable[
    [str, Logger, float | None],
    Coroutine[Any, Any, tuple[Any | type[NO_VALUE], Exception | None]]
]


class RoutineExecution(ABC, Generic[R]):
    __slots__ = ()
    @abstractmethod
    def __init__(self, frame_name: str, logger: Logger, options: dict):
        ...

    @abstractmethod
    def get_shared_lock(self) -> Lock:
        ...
    
    @abstractmethod
    def get_shared_map_factory(self) -> type[dict]:
        ...
    
    @abstractmethod
    def load_routine(self, frame_name: str, logger: Logger, routine, context: RoutineContext) -> None:
        ...
    
    # @abstractmethod
    # def wait_routine_result(self, frame_name: str, logger: Logger, timeout: float | None = None) -> tuple[Any | NO_VALUE, Exception | None]:
    #     ...
    
    @abstractmethod
    def get_wait_routine_result_fn(self) -> SyncWaitFn | AsyncWaitFn:
        ...
    
    @abstractmethod
    def routine_is_running(self) -> bool:
        ...
    
    @abstractmethod
    def request_stop_routine(self, frame_name: str, logger: Logger, **kwargs) -> None:
        ...
    
    @abstractmethod
    def cleanup(self, frame_name: str, logger: Logger, timeout: float | None = None) -> None:
        ...
    