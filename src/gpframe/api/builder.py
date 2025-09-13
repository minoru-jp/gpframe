
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

R = TypeVar("R")
R2 = TypeVar("R2")

if TYPE_CHECKING:
    import logging

    from ..impl.frame import Frame
    from ..impl.builder import Routine
    from ..impl.handler.event import EventHandler
    from ..impl.handler.redo import RedoHandler
    from ..impl.handler.exception import ExceptionHandler
    # from ..impl.handler.terminated import TerminatedHandler


def FrameBuilder(routine: Routine[R], name: str = "frame", **options) -> FrameBuilderType[R]:
    from ..impl.builder import create_builder_role
    role = create_builder_role(routine, name = name, **options)
    return role.interface


class FrameBuilderType(ABC, Generic[R]):
    __slots__ = ()
    @abstractmethod
    def set_logger(self, logger: logging.Logger):
        ...
    
    @abstractmethod
    def set_environments(self, environments: dict):
        ...
    
    @abstractmethod
    def set_requests(self, requests: dict):
        ...
    
    @abstractmethod
    def set_routine_timeout(self, timeout: float | None) -> None:
        ...
    
    @abstractmethod
    def set_cleanup_timeout(self, timeout: float | None) -> None:
        ...

    @abstractmethod
    def get_frame(self, **options) -> Frame:
        ...

    # @abstractmethod
    # def set_on_terminated(self, handler: TerminatedHandler):
    #     ...
    
    @abstractmethod
    def set_on_exception(self, handler: ExceptionHandler):
        ...

    @abstractmethod
    def set_on_redo(self, handler: RedoHandler[R]) -> None:
        ...

    @abstractmethod
    def set_on_open(self, handler: EventHandler[R]) -> None:
        ...
    
    @abstractmethod
    def set_on_start(self, handler: EventHandler[R]) -> None:
        ...
    
    @abstractmethod
    def set_on_end(self, handler: EventHandler[R]) -> None:
        ...
    
    @abstractmethod
    def set_on_cancel(self, handler: EventHandler[R]) -> None:
        ...
    
    @abstractmethod
    def set_on_close(self, handler: EventHandler[R]) -> None:
        ...
    
    @abstractmethod
    def create_inner_frame_builder(self, routine: Routine[R2], name: str = "inner-frame") -> FrameBuilderType[R]:
        ...
    