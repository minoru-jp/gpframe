from __future__ import annotations

import asyncio
import inspect

from gpframe._impl.frame.frame_base import _FrameBaseState as FrameBaseState
from gpframe._impl.routine.result import _NO_VALUE

async def circuit(
        base: FrameBaseState,
        ectx,
        rctx,
        routine_execution,
        routine,
) -> None:
    event_handlers = base.event_handlers
    exception_handler = base.exception_handler
    redo_handler = base.redo_handler
    try:
        try:
            await base.event_handlers["on_open"](ectx)
        except BaseException as e:
            if not await asyncio.shield(exception_handler(ectx, e)):
                raise

        while True:
            try:
                await event_handlers["on_start"](ectx)
            except BaseException as e:
                if not await asyncio.shield(exception_handler(ectx, e)):
                    raise
            
            try:
                routine_execution.load_routine(
                    routine,
                    rctx)
            except BaseException as e:
                if not await asyncio.shield(exception_handler(ectx, e)):
                    raise
            
            
            result = _NO_VALUE
            rexc: Exception | None = None
            try:
                wait_routine_result = routine_execution.get_wait_routine_result_fn()
                tuple_or_coro = wait_routine_result(
                    base.routine_timeout
                )
                if inspect.iscoroutine(tuple_or_coro):
                    result, rexc = await tuple_or_coro
                elif isinstance(tuple_or_coro, tuple):
                    result, rexc = tuple_or_coro
                else:
                    raise RuntimeError
            except BaseException as e:
                if not await asyncio.shield(exception_handler(ectx, e)):
                    raise
            

            if isinstance(rexc, asyncio.CancelledError):
                if not await asyncio.shield(exception_handler(ectx, rexc)):
                    raise
                else:
                    rexc = None
            
            if rexc:
                if not await asyncio.shield(exception_handler(ectx, rexc)):
                    raise
            
            base.routine_result.set(result, rexc)
            
            try:
                await event_handlers["on_end"](ectx)
            except BaseException as e:
                if not await asyncio.shield(exception_handler(ectx, e)):
                    raise
            
            try:
                redo = await redo_handler(ectx)
            except BaseException as e:
                if not await asyncio.shield(exception_handler(ectx, e)):
                    raise

            if not redo:
                break

    except asyncio.CancelledError as e:
        try:
            await asyncio.shield(event_handlers["on_cancel"](ectx))
        except BaseException as e:
            if not await asyncio.shield(exception_handler(ectx, e)):
                raise
    finally:
        try:
            await asyncio.shield(event_handlers["on_close"](ectx))
        except BaseException as e:
            if not await asyncio.shield(exception_handler(ectx, e)):
                raise

        


