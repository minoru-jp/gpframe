from __future__ import annotations

from dataclasses import dataclass

import threading
from typing import Callable

from gpframe.contracts.protocols import _FrameBase

from gpframe.exceptions import FrameTerminatedError

from gpframe._impl.phase import _Role as PhaseRole, create_phase_manager_role

from gpframe._impl.handler.event import EventHandlerWrapper
from gpframe._impl.handler.redo import RedoHandlerWrapper
from gpframe._impl.handler.exception import ExceptionHandlerWrapper

from gpframe._impl.message.message import MessageRegistry
from gpframe._impl.routine.result import RoutineResultSource

ALL_EVENTS = (
    'on_open',
    'on_start',
    'on_end',
    'on_cancel',
    'on_close'
)

@dataclass(slots = True)
class _FrameBaseState:
    frame_name: str

    intra_frame_lock: threading.Lock

    phase_role: PhaseRole

    phase_validtor: Callable[[], None]

    event_handlers: dict[str, EventHandlerWrapper]
    redo_handler: RedoHandlerWrapper
    exception_handler: ExceptionHandlerWrapper

    event_message: MessageRegistry
    routine_message: MessageRegistry

    routine_result: RoutineResultSource

    routine_timeout: float | None
    cleanup_timeout: float | None


@dataclass(slots = True)
class _FrameBaseRole:
    updater: _FrameBaseUpdater
    state: _FrameBaseState
    interface_type: type[_FrameBase]


class _FrameBaseUpdater:
    __slots__ = ()
    def create_state(self, frame_name: str) -> _FrameBaseState:
        intra_frame_lock = threading.Lock()
        
        phase_role = create_phase_manager_role()
        
        def phase_validator():
            def fn():
                raise FrameTerminatedError
            phase_role.interface.if_terminated(fn)

        return _FrameBaseState(
            frame_name = frame_name,
            intra_frame_lock = intra_frame_lock,
            phase_role = phase_role,
            phase_validtor = phase_validator,
            event_handlers = {
                event_name : EventHandlerWrapper(event_name)
                for event_name in ALL_EVENTS
            },
            redo_handler = RedoHandlerWrapper(),
            exception_handler = ExceptionHandlerWrapper(),
            event_message = MessageRegistry(intra_frame_lock, dict(), phase_validator),
            routine_message = MessageRegistry(intra_frame_lock, dict(), phase_validator),
            routine_result = RoutineResultSource(intra_frame_lock, phase_validator),
            routine_timeout = None,
            cleanup_timeout = None,
        )


def create_frame_base_role(frame_name: str) -> _FrameBaseRole:

    updater = _FrameBaseUpdater()

    state = updater.create_state(frame_name)

    class _Interface(_FrameBase):
        __slots__ = ()
        def set_routine_timeout(self, timeout: float | None) -> None:
            def fn():
                state.routine_timeout = timeout
            state.phase_role.interface.on_load(fn)
        
        def set_cleanup_timeout(self, timeout: float | None) -> None:
            def fn():
                state.cleanup_timeout = timeout
            state.phase_role.interface.on_load(fn)
    
    return _FrameBaseRole(
        updater = updater,
        state = state,
        interface_type = _Interface
    )


