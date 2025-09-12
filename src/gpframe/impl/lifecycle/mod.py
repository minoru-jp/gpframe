from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Coroutine

from ..routine.result import NO_VALUE
from ..handler.errors import HandledError
from ..outcome import Outcome


if TYPE_CHECKING:
    from .. import builder


class Circuit:
    __slots__ = ("base_state", "updater", "routine_sync", "contexts")

    def __init__(
            self,
            base_state: builder._BaseState,
            updater: builder._Updater,
            routine_sync: builder._FrameSynchronization,
            contexts: builder._Contexts):
        self.base_state = base_state
        self.updater = updater
        self.routine_sync = routine_sync
        self.contexts = contexts

    
    async def coroutine(self) -> Coroutine[Any, Any, None]:

        base_state = self.base_state
        updater = self.updater
        routine_sync = self.routine_sync
        ectx = self.contexts.ectx
        rctx = self.contexts.rctx
        redo = False
        
        try:
            try:
                await base_state.event_handlers["on_open"](ectx)
            except HandledError as e:
                if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                    raise

            while True:
                try:
                    await base_state.event_handlers["on_start"](ectx)
                except HandledError as e:
                    if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                        raise
                
                try:
                    routine_sync.routine_execution.load_routine(
                        base_state.frame_name,
                        base_state.logger,
                        base_state.routine,
                        rctx)
                except HandledError as e:
                    if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                        raise
                
                
                result = NO_VALUE
                rexc: Exception | None = None
                try:
                    wait_routine_result = routine_sync.routine_execution.get_wait_routine_result_fn()
                    tuple_or_coro = wait_routine_result(
                        base_state.frame_name,
                        base_state.logger,
                        base_state.routine_timeout
                    )
                    if inspect.iscoroutine(tuple_or_coro):
                        result, rexc = await tuple_or_coro
                    elif isinstance(tuple_or_coro, tuple):
                        result, rexc = tuple_or_coro
                    else:
                        raise RuntimeError
                except HandledError as e:
                    if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                        raise
                

                if isinstance(rexc, asyncio.CancelledError):
                    if not await asyncio.shield(base_state.exception_handler(ectx, rexc)):
                        raise
                    else:
                        rexc = None
                
                if rexc:
                    if not await asyncio.shield(base_state.exception_handler(ectx, rexc)):
                        raise
                
                routine_sync.routine_result.set(result, rexc)
                
                try:
                    await base_state.event_handlers["on_end"](ectx)
                except HandledError as e:
                    if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                        raise
                
                try:
                    redo = await base_state.redo_handler(ectx)
                except HandledError as e:
                    if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                        raise

                if not redo:
                    break

        except asyncio.CancelledError as e:
            try:
                await asyncio.shield(base_state.event_handlers["on_cancel"](ectx))
            except HandledError as e:
                if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                    raise
        finally:
            try:
                await asyncio.shield(base_state.event_handlers["on_close"](ectx))
            except HandledError as e:
                if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                    raise


            outcome: Outcome | None = None
            def atomic_with_terminating():
                nonlocal outcome
                outcome = updater.create_outcome_source(routine_sync).interface
                if not routine_sync.is_derived:
                    updater.cleanup_maps(routine_sync)
                routine_sync.routine_execution.cleanup(
                    base_state.frame_name,
                    base_state.logger,
                    base_state.cleanup_timeout)
            base_state.phase_role.interface.to_terminated(atomic_with_terminating)

            if outcome is None:
                raise RuntimeError("BUG: outcome is None")
            
            base_state = self.base_state # for type inference support
            try:
                await asyncio.shield(base_state.terminated_callback(outcome))
            except HandledError as e:
                if not await asyncio.shield(base_state.exception_handler(ectx, e)):
                    raise

