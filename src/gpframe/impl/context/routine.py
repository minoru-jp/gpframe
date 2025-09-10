from __future__ import annotations

from typing import TYPE_CHECKING

from ...api.contexts import RoutineContext

if TYPE_CHECKING:
    from ..message import MessageUpdater, MessageReader

def create_routine_context(
        frame_name: str,
        logger_name: str,
        routine_in_subprocess: bool,
        environment_reader: MessageReader,
        request_reader: MessageReader,
        event_msg_reader: MessageReader,
        routine_msg_updater: MessageUpdater,
) -> RoutineContext:
    
    class _Interface(RoutineContext):
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger_name(self) -> str:
            return logger_name
        @property
        def routine_in_subprocess(self) -> bool:
            return routine_in_subprocess
        @property
        def environment(self) -> MessageReader:
            return environment_reader
        @property
        def request(self) -> MessageReader:
            return request_reader
        @property
        def event_message(self) -> MessageReader:
            return event_msg_reader
        @property
        def routine_message(self) -> MessageUpdater:
            return routine_msg_updater
        def __reduce__(self):
            return (
                create_routine_context,
                (frame_name,
                 logger_name,
                 routine_in_subprocess,
                 environment_reader,
                 request_reader,
                 event_msg_reader,
                 routine_msg_updater)
            )
        
    interface = _Interface()
    
    return interface



