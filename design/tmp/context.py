from __future__ import annotations

from logging import Logger
from typing import Any, Callable

from gpframe.contracts.api import SubFrameFuture, gproot, gpsub, message, routine

MessageReader = message.MessageReader
MessageUpdater = message.MessageUpdater

RoutineResult = routine.Result

from gpframe._impl.message.message import MessageRegistry
from gpframe._impl.message.reflector import MessageReflector

from gpframe._impl.routine.result import RoutineResultSource

def create_intra_process_context(
        frame_name: str,
        logger: Logger,
        environment: MessageRegistry[Any],
        request: MessageRegistry[Any],
        event_msg: MessageRegistry[Any],
        routine_msg: MessageRegistry[Any],
        routine_result: RoutineResultSource,
        inter_frame_msg: MessageReflector,
        ipc_msg: MessageReflector,
        sub_frame_start_fn: Callable[[str], SubFrameFuture]
) -> gproot.routine.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger(self) -> Logger:
            return logger
        
        @property
        def environment(self) -> MessageReader[Any]:
            return environment.reader
        @property
        def request(self) -> MessageReader[Any]:
            return request.reader
        
        @property
        def local(self) -> MessageUpdater[Any]:
            ...
        
        @property
        def common(self) -> MessageUpdater[str]:
            return inter_frame_msg.updater

        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        
        def start_sub_frame(self, frame_name: str) -> SubFrameFuture:
            return sub_frame_start_fn(frame_name)
        
    interface = _Interface()
    
    return interface


def create_ipc_context(
        frame_name: str,
        logger_name: str,
        ipc_msg: MessageReflector,
) -> gproot.ipc.routine.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger_name(self) -> str:
            return logger_name

        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        
        def __reduce__(self):
            return (
                create_ipc_root_routine_context,
                (
                    frame_name,
                    logger_name,
                    ipc_msg,
                )
            )
        
    interface = _Interface()
    
    return interface


def create_root_routine_context(
        frame_name: str,
        logger: Logger,
        environment: MessageRegistry[Any],
        request: MessageRegistry[Any],
        event_msg: MessageRegistry[Any],
        routine_msg: MessageRegistry[Any],
        routine_result: RoutineResultSource,
        inter_frame_msg: MessageReflector,
        ipc_msg: MessageReflector,
        sub_frame_start_fn: Callable[[str], SubFrameFuture]
) -> gproot.routine.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger(self) -> Logger:
            return logger
        @property
        def environment(self) -> MessageReader[Any]:
            return environment.reader
        @property
        def request(self) -> MessageUpdater[Any]:
            return request.updater
        @property
        def event_message(self) -> MessageReader[Any]:
            return event_msg.reader
        @property
        def routine_message(self) -> MessageUpdater[Any]:
            return routine_msg.updater
        @property
        def routine_result(self) -> RoutineResult:
            return routine_result.interface
        @property
        def inter_frame(self) -> MessageUpdater[str]:
            return inter_frame_msg.updater
        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        def start_sub_frame(self, frame_name: str) -> SubFrameFuture:
            return sub_frame_start_fn(frame_name)
        
    interface = _Interface()
    
    return interface


def create_ipc_root_routine_context(
        frame_name: str,
        logger_name: str,
        ipc_msg: MessageReflector,
) -> gproot.ipc.routine.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger_name(self) -> str:
            return logger_name
        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        
        def __reduce__(self):
            return (
                create_ipc_root_routine_context,
                (
                    frame_name,
                    logger_name,
                    ipc_msg,
                )
            )
        
    interface = _Interface()
    
    return interface


def create_sub_routine_context(
        frame_name: str,
        logger: Logger,
        environment: MessageRegistry[Any],
        request: MessageRegistry[Any],
        event_msg: MessageRegistry[Any],
        routine: MessageRegistry[Any],
        routine_result: RoutineResultSource,
        inter_frame_msg: MessageReflector,
        ipc_msg: MessageReflector,
) -> gpsub.routine.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger(self) -> Logger:
            return logger
        @property
        def environment(self) -> MessageReader[Any]:
            return environment.reader
        @property
        def request(self) -> MessageReader[Any]:
            return request.reader
        @property
        def event_message(self) -> MessageReader[Any]:
            return event_msg.reader
        @property
        def routine_message(self) -> MessageUpdater[Any]:
            return routine.updater
        @property
        def routine_result(self) -> RoutineResult:
            return routine_result.interface
        @property
        def inter_frame(self) -> MessageUpdater[str]:
            return inter_frame_msg.updater
        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        
    interface = _Interface()
    
    return interface


def create_ipc_sub_routine_context(
        frame_name: str,
        logger_name: str,
        ipc_msg: MessageReflector,
) -> gpsub.ipc.routine.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger_name(self) -> str:
            return logger_name
        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        
        def __reduce__(self):
            return (
                create_ipc_sub_routine_context,
                (
                    frame_name,
                    logger_name,
                    ipc_msg,
                )
            )
        
    interface = _Interface()
    
    return interface


def create_root_event_context(
        frame_name: str,
        logger: Logger,
        environment: MessageRegistry[Any],
        request: MessageRegistry[Any],
        event_msg: MessageRegistry[Any],
        routine: MessageRegistry[Any],
        routine_result: RoutineResultSource,
        inter_frame_msg: MessageReflector,
        ipc_msg: MessageReflector,
        sub_frame_start_fn: Callable[[str], SubFrameFuture]
) -> gproot.event.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger(self) -> Logger:
            return logger
        @property
        def environment(self) -> MessageReader[Any]:
            return environment.reader
        @property
        def request(self) -> MessageReader[Any]:
            return request.reader
        @property
        def event_message(self) -> MessageUpdater[Any]:
            return event_msg.updater
        @property
        def routine_message(self) -> MessageReader[Any]:
            return routine.reader
        @property
        def routine_result(self) -> RoutineResult:
            return routine_result.interface
        @property
        def inter_frame(self) -> MessageUpdater[str]:
            return inter_frame_msg.updater
        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        def start_sub_frame(self, frame_name: str) -> SubFrameFuture:
            return sub_frame_start_fn(frame_name)
        
    interface = _Interface()
    
    return interface

def create_sub_event_context(
        frame_name: str,
        logger: Logger,
        environment: MessageRegistry[Any],
        request: MessageRegistry[Any],
        event_msg: MessageRegistry[Any],
        routine: MessageRegistry[Any],
        routine_result: RoutineResultSource,
        inter_frame_msg: MessageReflector,
        ipc_msg: MessageReflector,
) -> gpsub.event.Context:
    
    class _Interface:
        __slots__ = ()
        @property
        def frame_name(self) -> str:
            return frame_name
        @property
        def logger(self) -> Logger:
            return logger
        @property
        def environment(self) -> MessageReader[Any]:
            return environment.reader
        @property
        def request(self) -> MessageReader[Any]:
            return request.reader
        @property
        def event_message(self) -> MessageUpdater[Any]:
            return event_msg.updater
        @property
        def routine_message(self) -> MessageReader[Any]:
            return routine.reader
        @property
        def routine_result(self) -> RoutineResult:
            return routine_result.interface
        @property
        def inter_frame(self) -> MessageUpdater[str]:
            return inter_frame_msg.updater
        @property
        def ipc(self) -> MessageUpdater[str]:
            return ipc_msg.updater
        
    interface = _Interface()
    
    return interface


