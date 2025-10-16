from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import Callable, cast


import logging
import threading
import multiprocessing
from multiprocessing.managers import SyncManager

from gpframe.contracts.api import handler, _RootFrameBase

from gpframe._impl.message.message import MessageRegistry
from gpframe._impl.message.reflector import MessageReflector


from gpframe._impl.frame.frame_base import (
    _FrameBaseRole,
    _FrameBaseState,
    create_frame_base_role
)

@dataclass(slots = True)
class _RootFrameBaseState:
    ml_sync_manager: SyncManager
    inter_frame_lock: threading.Lock
    ipc_lock: threading.Lock

    environments: dict

    environment_message: MessageRegistry
    request_message: MessageRegistry
    inter_frame_message: MessageReflector
    ipc_message: MessageReflector

@dataclass(slots = True)
class _RootFrameBaseRole:
    frame_base_role: _FrameBaseRole
    state: _RootFrameBaseState
    updater: _RootFrameBaseUpdater
    interface_type: type[_RootFrameBase]
    cleanup_fn: Callable[[], None]


class _RootFrameBaseUpdater:
    def create_state(self, frame_base_state: _FrameBaseState, logger: logging.Logger) -> _RootFrameBaseState:
        inter_frame_lock = threading.Lock()
        ml_sync_manager = multiprocessing.Manager()
        ipc_lock = ml_sync_manager.Lock()
        
        environments = {}

        environment_message = MessageRegistry(
            inter_frame_lock,
            environments,
            frame_base_state.phase_validtor
        )

        # Do not set a phase_validator for request_message.
        # This is because only the driver updates this message.
        # Other messages may not need a phase validator either.
        request_message = MessageRegistry(
            inter_frame_lock,
            {},
            # frame_base_state.phase_validtor
            lambda: None
        )

        namespace = f"{frame_base_state.frame_name}."
        inter_frame_message = MessageReflector(
            namespace,
            MessageRegistry(
                inter_frame_lock,
                {},
                frame_base_state.phase_validtor
            )
        )
        ipc_message = MessageReflector(
            namespace,
            MessageRegistry(
                ipc_lock,
                ml_sync_manager.dict(),
                frame_base_state.phase_validtor
            )
        )

        return _RootFrameBaseState(
            ml_sync_manager = ml_sync_manager,
            inter_frame_lock = inter_frame_lock,
            ipc_lock = ipc_lock,
            environments = environments,
            environment_message = environment_message,
            request_message = request_message,
            inter_frame_message = inter_frame_message,
            ipc_message = ipc_message
        )

def create_root_frame_base_role(frame_name: str, logger: logging.Logger):
    frame_base_role = create_frame_base_role(frame_name)
    
    frame_base_state = frame_base_role.state

    updater = _RootFrameBaseUpdater()

    state = updater.create_state(frame_base_state, logger)

    class _Interface(_RootFrameBase, frame_base_role.interface_type):
        __slots__ = ()
        def set_environments(self, environments: dict) -> None:
            def fn():
                state.environments.update(environments)
            frame_base_state.phase_role.interface.on_load(fn)

        def set_on_exception(self, handler: handler.root.ExceptionHandler) -> None:
            def fn():
                frame_base_state.exception_handler.set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_redo(self, handler: handler.root.RedoHandler):
            def fn():
                frame_base_state.redo_handler.set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_open(self, handler: handler.root.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_open"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_start(self, handler: handler.root.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_start"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_end(self, handler: handler.root.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_end"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_cancel(self, handler: handler.root.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_cancel"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
        
        def set_on_close(self, handler: handler.root.EventHandler) -> None:
            def fn():
                frame_base_state.event_handlers["on_close"].set_handler(handler)
            frame_base_state.phase_role.interface.on_load(fn)
    
    def cleanup() -> None:
        try:
            state.ml_sync_manager.shutdown()
        except Exception as e:
            pass # TODO: logging about exception
    
    return _RootFrameBaseRole(
        frame_base_role = frame_base_role,
        state = state,
        updater = updater,
        interface_type = _Interface,
        cleanup_fn = cleanup
    )

