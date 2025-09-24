from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

import logging

from multiprocessing.managers import SyncManager

from contextlib import contextmanager

from gpframe.contracts.protocols import gproot, frame, routine

from gpframe._impl.frame.future import run_circuit_in_thread, wrap_to_interface

from gpframe._impl.routine.subprocess import IPCRoutineExecution
from gpframe._impl.routine.subprocess import SyncRoutineInSubprocess

from gpframe._impl.frame.frame_base import (
    _FrameBaseState,
)

from gpframe._impl.frame.root_base import (
    _RootFrameBaseRole,
    _RootFrameBaseState,
    create_root_frame_base_role
)

from gpframe._impl.context import create_root_event_context, create_ipc_root_routine_context

@dataclass(slots = True)
class _IPCRootFrameState:
    logger: logging.Logger

    event_context: gproot.event.Context
    routine_context: gproot.ipc.routine.Context

    routine_execution: IPCRoutineExecution

@dataclass(slots = True)
class _RootFrameRole:
    root_frame_base_role: _RootFrameBaseRole
    state: _IPCRootFrameState
    updater: _RootFrameUpdater
    interface_type: type[frame.IPCRootFrame]


class _RootFrameUpdater:
    def create_state(
            self,
            logger: logging.Logger,
            routine: Callable,
            ml_sync_manager: SyncManager,
            frame_base_state: _FrameBaseState,
            root_frame_base_state: _RootFrameBaseState
        ) -> _IPCRootFrameState:
        
        sub_frames = {}

        def dummy_sub_frame_start_fn(frame_name: str):
            raise RuntimeError
        
        event_context = create_root_event_context(
            frame_base_state.frame_name,
            logger,
            root_frame_base_state.environment_message,
            root_frame_base_state.request_message,
            frame_base_state.event_message,
            frame_base_state.routine_message,
            frame_base_state.routine_result,
            root_frame_base_state.inter_frame_message,
            root_frame_base_state.ipc_message,
            dummy_sub_frame_start_fn
        )

        routine_context = create_ipc_root_routine_context(
            frame_base_state.frame_name,
            logger.name,
            root_frame_base_state.ipc_message
        )

        routine_execution = SyncRoutineInSubprocess(
            ml_sync_manager.Lock(),
            ml_sync_manager.Queue(),
            ml_sync_manager.Queue()
        )

        return _IPCRootFrameState(
            logger,
            event_context,
            routine_context,
            routine_execution,
        )

def create_ipc_root_frame_role(frame_name: str, routine: routine.ipc.Root, *, logger: logging.Logger):
    root_frame_base_role = create_root_frame_base_role(frame_name, logger)
    
    frame_base_state = root_frame_base_role.frame_base_role.state
    root_base_state = root_frame_base_role.state

    updater = _RootFrameUpdater()

    state = updater.create_state(
        logger,
        routine,
        root_base_state.ml_sync_manager,
        frame_base_state,
        root_base_state
    )

    class _Interface(frame.IPCRootFrame, root_frame_base_role.interface_type):
        def stop_routine(self, kill: bool = False) -> None:
            state.routine_execution.request_stop_routine(kill)
        
        @contextmanager
        def start(self):
            def fn():
                frame_future = run_circuit_in_thread(
                    frame_base_state,
                    state.event_context,
                    state.routine_context,
                    state.routine_execution,
                    routine,
                )
                return wrap_to_interface(frame_future)
            try:
                yield frame_base_state.phase_role.interface.to_started(fn)
            finally:
                root_frame_base_role.cleanup_fn()
    
    return _RootFrameRole(
        root_frame_base_role = root_frame_base_role,
        state = state,
        updater = updater,
        interface_type = _Interface
    )


def create_ipc_frame(frame_name: str, routine: routine.ipc.Root, *, logger: logging.Logger | None = None) -> frame.IPCRootFrame:
    logger = logger if logger else logging.getLogger("gpframe")
    role = create_ipc_root_frame_role(frame_name, routine, logger = logger)
    return role.interface_type()
