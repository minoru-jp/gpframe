from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from ...api.contexts import OuterContext

if TYPE_CHECKING:
    from ..message import  MessageReader

def create_outer_context(
        frame_name: str,
        routine_in_subprocess: bool,
        environment_reader: MessageReader,
        request_reader: MessageReader,
        event_msg_reader: MessageReader,
        routine_msg_reader: MessageReader,
) -> OuterContext:
    
    class _Interface(OuterContext):
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
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
        def routine_message(self) -> MessageReader:
            return routine_msg_reader
        
        def __reduce__(self):
            return (
                create_outer_context,
                    (frame_name,
                    routine_in_subprocess,
                    environment_reader,
                    request_reader,
                    event_msg_reader,
                    routine_msg_reader
                )
            )
        
    interface = _Interface()
    
    return interface

