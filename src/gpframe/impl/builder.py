from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Protocol, TypeVar

import inspect
import logging

from ..api.builder import FrameBuilderType
from ..api.outcome import Outcome

from .routine.base import RoutineExecution
from .routine.synchronous import SyncRoutine
from .routine.asynchronous import AsyncRoutine
from .routine.subprocess import SyncRoutineInSubprocess

from .lifecycle import Circuit
from .lifecycle import PhaseRole, create_phase_manager_role

from .handler.redo import RedoHandlerWrapper
from .handler.redo import RedoHandler

from .handler.exception import ExceptionHandlerWrapper
from .handler.exception import ExceptionHandler

from .message import MessageRegistry, MessageReader, MessageUpdater

from .frame import Frame, create_frame_api
from .context.event import EventContext, create_event_context
from .context.routine import RoutineContext, create_routine_context

from .routine.result import RoutineResultSource

from .handler.event import EventHandlerWrapper
from .handler.event import EventHandler

from .outcome import OutcomeSource

from .handler.terminated import TerminatedHandlerWrapper
from .handler.terminated import TerminatedHandler

class TerminatedError(Exception):
    """Raised when accessing a context resource after frame termination.

    This error is thrown if a ``SynchronizedMapReader``/``SynchronizedMapUpdater``
    (or similar context-managed resource) is accessed after the frame has
    already terminated. It prevents use of stale or invalid state once
    the frame lifecycle has ended.
    """

R = TypeVar("R")
R2 = TypeVar("R2")

Routine = Callable[[RoutineContext], R] | Callable[[RoutineContext], Awaitable[R]]
RoutineCaller = Callable[[asyncio.AbstractEventLoop], tuple[Any, Exception | asyncio.CancelledError | None]]

ALL_EVENTS = (
    'on_open',
    'on_start',
    'on_end',
    'on_cancel',
    'on_close'
)

@dataclass(slots = True)
class _BaseState(Generic[R]):
    frame_name: str
    logger: logging.Logger

    routine: Routine[R]

    phase_role: PhaseRole

    event_handlers: dict[str, EventHandlerWrapper]
    redo_handler: RedoHandlerWrapper
    exception_handler: ExceptionHandlerWrapper
    terminated_callback: TerminatedHandlerWrapper
    
    environments: dict
    requests: dict

    routine_timeout: float | None
    cleanup_timeout: float | None

    consume_routine_result: asyncio.Event

@dataclass(slots = True)
class _FrameSynchronization(Generic[R]):
    is_derived: bool
    routine_execution: RoutineExecution[R]
    environment_map: MessageRegistry
    request_map: MessageRegistry
    event_msg_map: MessageRegistry
    routine_msg_map: MessageRegistry
    routine_result: RoutineResultSource

@dataclass(slots = True)
class _Contexts:
    ectx: EventContext
    rctx: RoutineContext


class _Updater:
    __slots__ = ()
    def create_base_state(self, routine: Routine[R]) -> _BaseState[R]:
        return _BaseState(
            frame_name = "noname",
            logger = logging.getLogger("gpframe"),
            routine = routine,
            phase_role = create_phase_manager_role(),
            event_handlers = {
                event_name : EventHandlerWrapper(event_name)
                for event_name in ALL_EVENTS
            },
            redo_handler = RedoHandlerWrapper(),
            exception_handler = ExceptionHandlerWrapper(),
            terminated_callback = TerminatedHandlerWrapper(),
            environments = {},
            requests = {},
            routine_timeout = None,
            cleanup_timeout = None,
            consume_routine_result = asyncio.Event()
        )
    
    def create_routine_synchronization(
            self,
            frame_name: str,
            logger: logging.Logger,
            routine: Routine,
            phase_role: PhaseRole,
            environments: dict,
            requests: dict,
            as_subprocess: bool,
            options: dict,
            share: Callable[[], _FrameSynchronization] | None) -> _FrameSynchronization:
        def validate_accessable_phase():
            def fn():
                raise TerminatedError
            phase_role.interface.if_terminated(fn)
    
        shared_frame_sync = share() if share else None

        shared_routine_exe = shared_frame_sync.routine_execution if shared_frame_sync else None
        if inspect.iscoroutinefunction(routine):
            if as_subprocess:
                raise TypeError("async function can not be subprocess.")
            routine_execution = AsyncRoutine(frame_name, logger, options, shared_routine_exe)
        else:
            if as_subprocess:
                routine_execution = SyncRoutineInSubprocess(frame_name, logger, options, shared_routine_exe)
            else:
                routine_execution = SyncRoutine(frame_name, logger, options, shared_routine_exe)
        
        if shared_frame_sync:
            environment_map = shared_frame_sync.environment_map
            request_map = shared_frame_sync.request_map
            event_msg_map = shared_frame_sync.event_msg_map
            routine_msg_map = shared_frame_sync.routine_msg_map
            routine_result = RoutineResultSource(
                shared_frame_sync.routine_execution.get_shared_lock(),
                validate_accessable_phase
            )
        else:
            lock = routine_execution.get_shared_lock()
            map_factory = routine_execution.get_shared_map_factory()

            environment_map = MessageRegistry(lock, map_factory(environments), validate_accessable_phase)
            request_map = MessageRegistry(lock, map_factory(requests), validate_accessable_phase)
            event_msg_map = MessageRegistry(lock, map_factory(), validate_accessable_phase)
            routine_msg_map = MessageRegistry(lock, map_factory(), validate_accessable_phase)
            routine_result = RoutineResultSource(lock, validate_accessable_phase)

        return _FrameSynchronization(
            is_derived = share is not None,
            routine_execution = routine_execution,
            environment_map = environment_map,
            request_map = request_map,
            event_msg_map = event_msg_map,
            routine_msg_map = routine_msg_map,
            routine_result = routine_result,
        )

    
    def create_contexts(self, state: _BaseState, frame_sync: _FrameSynchronization) -> _Contexts:

        env_reader = frame_sync.environment_map.reader

        req_reader = frame_sync.request_map.reader
        
        req_reader = frame_sync.request_map.reader
        emsg_reader = frame_sync.event_msg_map.reader
        rmsg_updater = frame_sync.routine_msg_map.updater
        
        as_subprocess = isinstance(frame_sync.routine_execution, SyncRoutineInSubprocess)
        
        ectx = create_event_context(
            state,
            frame_sync
        )
        
        rctx = create_routine_context(
            state.frame_name,
            state.logger.name,
            as_subprocess,
            env_reader,
            req_reader,
            emsg_reader,
            rmsg_updater)
        
        return _Contexts(
            ectx = ectx,
            rctx = rctx
        )
    
    def create_circuit(
            self,
            base_state: _BaseState,
            updater: _Updater,
            routine_sync: _FrameSynchronization,
            contexts: _Contexts
        ) -> Circuit:
        return Circuit(
                base_state,
                updater,
                routine_sync,
                contexts
            )
    
    def create_outcome_source(
            self,
            routine_sync: _FrameSynchronization,
        ) -> OutcomeSource:
        requests = routine_sync.request_map.copy_map_without_usage_state_check()
        event_msg = routine_sync.event_msg_map.copy_map_without_usage_state_check()
        routine_msg = routine_sync.routine_msg_map.copy_map_without_usage_state_check()

        return OutcomeSource(
            requests,
            event_msg,
            routine_msg)

    def cleanup_maps(self, routine_sync: _FrameSynchronization) -> None:
        routine_sync.environment_map.clear_map_unsafe()
        routine_sync.request_map.clear_map_unsafe()
        routine_sync.event_msg_map.clear_map_unsafe()
        routine_sync.routine_msg_map.clear_map_unsafe()
        routine_sync.routine_result.clear_routine_result_unsafe()
        routine_sync.routine_result.clear_routine_error_unsafe()
    

@dataclass(slots = True)
class _Role(Generic[R]):
    state: _BaseState[R]
    core: _Updater
    interface: FrameBuilderType[R]


def create_builder_role(routine: Routine[R], share: Callable[[], _FrameSynchronization] | None = None) -> _Role[R]:

    if not callable(routine):
        raise TypeError("routine must be a callable")

    updater = _Updater()

    base_state = updater.create_base_state(routine)

    routine_sync: _FrameSynchronization | None = None

    contexts: _Contexts | None = None

    circuit: Circuit | None = None



    class _Interface(FrameBuilderType):
        __slots__ = ()
        def set_name(self, name: str) -> None:
            def fn():
                base_state.frame_name = name
            base_state.phase_role.interface.on_load(fn)
    
        def set_logger(self, logger: logging.Logger):
            def fn():
                base_state.logger = logger
            base_state.phase_role.interface.on_load(fn)

        def set_environments(self, environments: dict):
            def fn():
                base_state.environments = dict(environments)
            base_state.phase_role.interface.on_load(fn)
        
        def set_requests(self, requests: dict):
            def fn():
                base_state.requests = dict(requests)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_exception(self, handler: ExceptionHandler[R]):
            def fn():
                base_state.exception_handler.set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_terminated(self, handler: TerminatedHandler):
            def fn():
                base_state.terminated_callback.set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_redo(self, handler: RedoHandler[R]):
            def fn():
                base_state.redo_handler.set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_open(self, handler: EventHandler[R]) -> None:
            def fn():
                base_state.event_handlers["on_open"].set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_start(self, handler: EventHandler[R]) -> None:
            def fn():
                base_state.event_handlers["on_start"].set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_end(self, handler:EventHandler[R]) -> None:
            def fn():
                base_state.event_handlers["on_end"].set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_cancel(self, handler: EventHandler[R]) -> None:
            def fn():
                base_state.event_handlers["on_cancel"].set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_on_close(self, handler: EventHandler[R]) -> None:
            def fn():
                base_state.event_handlers["on_close"].set_handler(handler)
            base_state.phase_role.interface.on_load(fn)
        
        def set_routine_timeout(self, timeout: float | None) -> None:
            def fn():
                base_state.routine_timeout = timeout
            base_state.phase_role.interface.on_load(fn)
        
        def set_cleanup_timeout(self, timeout: float | None) -> None:
            def fn():
                base_state.cleanup_timeout = timeout
            base_state.phase_role.interface.on_load(fn)
        
    
        def create_shared_builder(self, routine: Routine[R2]) -> FrameBuilderType[R2]:
            def frame_sync_getter() -> _FrameSynchronization:
                def fn():
                    if routine_sync is None:
                        raise RuntimeError("BUG: routine_sync is still None")
                    return routine_sync
                return base_state.phase_role.interface.on_load(fn)
            
            role = create_builder_role(routine, frame_sync_getter)
            return role.interface
        
        def get_frame(self, **options) -> Frame:
            nonlocal routine_sync, contexts, circuit
            
            def fn():
                nonlocal routine_sync, contexts, circuit

                as_subprocess = options["as_subprocess"] if "as_subprocess" in options else False

                routine_sync = updater.create_routine_synchronization(
                    base_state.frame_name,
                    base_state.logger,
                    base_state.routine,
                    base_state.phase_role,
                    base_state.environments,
                    base_state.requests,
                    as_subprocess,
                    options,
                    share
                )

                contexts = updater.create_contexts(
                    base_state,
                    routine_sync
                )

                circuit = updater.create_circuit(
                    base_state,
                    updater,
                    routine_sync,
                    contexts
                )
            
            base_state.phase_role.interface.to_frame_dispatched(fn)
            if routine_sync is None:
                raise RuntimeError("BUG: routine_sync is None")
            
            def start() -> asyncio.Task:
                def fn():
                    assert circuit
                    coro = circuit.coroutine
                    task = asyncio.create_task(coro())
                    return task
            
                return base_state.phase_role.interface.to_started(fn)

            return create_frame_api(base_state, routine_sync, start)
            
    interface = _Interface()
    
    return _Role(state = base_state, core = updater, interface = interface)


