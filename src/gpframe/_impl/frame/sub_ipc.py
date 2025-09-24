from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import logging

from multiprocessing.managers import SyncManager


from gpframe.contracts.protocols import FrameFuture, gpsub, frame, handler, routine

from gpframe._impl.frame.future import FrameFutureImpl, run_circuit_in_thread

from gpframe._impl.message.message import MessageRegistry
from gpframe._impl.message.reflector import MessageReflector

from gpframe._impl.routine.base import IPCRoutineExecution
from gpframe._impl.routine.subprocess import SyncRoutineInSubprocess

from gpframe._impl.frame.frame_base import (
    _FrameBaseRole,
    _FrameBaseState,
    create_frame_base_role
)

from gpframe._impl.context import create_sub_event_context, create_ipc_sub_routine_context



@dataclass(slots = True)
class _IPCSubFrameState:
    event_context: gpsub.event.Context
    routine_context: gpsub.ipc.routine.Context

    routine_execution: IPCRoutineExecution

class _SubFrameUpdater:
    __slots__ = ()
    @staticmethod
    def create_state(
        frame_base_state: _FrameBaseState,
        logger: logging.Logger,
        routine: routine.ipc.Sub,
        ml_sync_manager: SyncManager,
        environment_message: MessageRegistry,
        request_message: MessageRegistry,
        inter_frame_message: MessageReflector,
        ipc_message: MessageReflector
    ) -> _IPCSubFrameState:
        event_context = create_sub_event_context(
            frame_base_state.frame_name,
            logger,
            environment_message,
            request_message,
            frame_base_state.event_message,
            frame_base_state.routine_message,
            frame_base_state.routine_result,
            inter_frame_message,
            ipc_message            
        )
        routine_context = create_ipc_sub_routine_context(
            frame_base_state.frame_name,
            logger.name,
            ipc_message,
        )
        
        routine_execution = SyncRoutineInSubprocess(
            ml_sync_manager.Lock(),
            ml_sync_manager.Queue(),
            ml_sync_manager.Queue(),
        )

        return _IPCSubFrameState(
            event_context,
            routine_context,
            routine_execution
        )

@dataclass(slots = True)
class _IPCSubFrameRole:
    frame_base_role: _FrameBaseRole
    state: _IPCSubFrameState
    interface_type: type[frame.SubFrame]
    start_fn: Callable[[], FrameFuture]

def create_ipc_sub_frame_role(
        frame_name: str,
        logger: logging.Logger,
        routine: routine.ipc.Sub,
        ml_sync_manager: SyncManager,
        environment_message: MessageRegistry,
        request_message: MessageRegistry,
        inter_frame_message: MessageReflector,
        ipc_message: MessageReflector
) -> _IPCSubFrameRole:
    frame_base_role = create_frame_base_role(frame_name)

    frame_base_state = frame_base_role.state

    state = _SubFrameUpdater.create_state(
        frame_base_state,
        logger,
        routine,
        ml_sync_manager,
        environment_message,
        request_message,
        inter_frame_message,
        ipc_message
    )

    def start() -> FrameFutureImpl:
        def fn():
            frame_future = run_circuit_in_thread(
                frame_base_state,
                state.event_context,
                state.routine_context,
                state.routine_execution,
                routine,
            )
            return frame_future
        return frame_base_state.phase_role.interface.to_started(fn)

    class _Interface(frame.SubFrame, frame_base_role.interface_type):
        __slots__ = ()
        def set_on_redo(self, handler: handler.sub.RedoHandler):
            def fn():
                frame_base_state.redo_handler.set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_exception(self, handler: handler.sub.ExceptionHandler) -> None:
            def fn():
                frame_base_state.exception_handler.set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_open(self, handler: handler.sub.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_open"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_start(self, handler: handler.sub.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_start"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_end(self, handler: handler.sub.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_end"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_cancel(self, handler: handler.sub.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_cancel"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_close(self, handler: handler.sub.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_close"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)

        def stop_routine(self, kill: bool = False) -> None:
            state.routine_execution.request_stop_routine(kill)



    return _IPCSubFrameRole(
        frame_base_role = frame_base_role,
        state = state,
        interface_type = _Interface,
        start_fn = start
    )
