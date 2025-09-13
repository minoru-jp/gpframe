from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from ...api.contexts import EventContext, OuterContext

if TYPE_CHECKING:
    from .. import builder
    from ..message import MessageUpdater, MessageReader
    from ..routine.result import RoutineResult
    from ..routine.subprocess import SyncRoutineInSubprocess

R = TypeVar("R")

def create_event_context(
        base_state: builder._BaseState,
        frame_sync: builder._FrameSynchronization[R],
) -> EventContext[R]:
    
    class _Interface(EventContext):
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return base_state.frame_name
        @property
        def logger(self) -> logging.Logger:
            return base_state.logger
        @property
        def routine_in_subprocess(self) -> bool:
            return isinstance(frame_sync.routine_execution, SyncRoutineInSubprocess)
        @property
        def environment(self) -> MessageReader:
            return frame_sync.environment_map.reader
        @property
        def request(self) -> MessageReader:
            return frame_sync.request_map.reader
        @property
        def event_message(self) -> MessageUpdater:
            return frame_sync.event_msg_map.updater
        @property
        def routine_message(self) -> MessageReader:
            return frame_sync.routine_msg_map.reader
        @property
        def routine_result(self) -> RoutineResult[R]:
            return frame_sync.routine_result.interface
        @property
        def outer(self) -> OuterContext:
            if not frame_sync.outer_context:
                raise RuntimeError
            return frame_sync.outer_context
        
    interface = _Interface()
    
    return interface

