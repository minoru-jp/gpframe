import asyncio
import inspect
import logging
import threading
from typing import Awaitable, Callable, TypeVar, Union, cast

from ..context.event import EventContext

R = TypeVar("R")

class ExceptionHandlerError(Exception):
    # Exceptions raised by the exception handler are not expected
    # to be handled by the framework, and therefore do not inherit
    # from FrameHandlerError.
    def __init__(self, e: Exception):
        super().__init__(repr(e))
        self.target = e


class Throw(Exception):
    """
    Container for rethrowing exceptions from an exception handler.

    Normally, exceptions raised inside a handler are converted into
    ExceptionHandlerError. Wrapping the target exception in Throw and
    raising it bypasses this conversion, propagating the original
    exception as-is.

    Typical usage:
        - Propagate a CancelledError that occurred in a routine so that
          it is delivered to the frame without being converted.

    Attributes:
        target (Exception): The exception to propagate.
    """
    def __init__(self, target: Exception):
        self.target = target


ExceptionHandler = Union[
    Callable[[EventContext[R], BaseException], bool],
    Callable[[EventContext[R], BaseException], Awaitable[bool]]
    ]

ExceptioHandlerAsync = Callable[[EventContext[R], BaseException], Awaitable[bool]]

def _log_exception(ctx: EventContext[R], exc: BaseException):
    ctx.logger.exception(
        f"Frame[{ctx.frame_name}]: "
        f"{type(exc).__name__}"
    )

async def _default_handler(ctx: EventContext[R], exc: BaseException) -> bool:
    _log_exception(ctx, exc)
    return False

class ExceptionHandlerWrapper:
    __slots__ = ('_caller',)
    def __init__(self):
        self._caller: ExceptioHandlerAsync = _default_handler
    
    async def __call__(self, ctx: EventContext[R], exc: BaseException) -> bool:
        try:
            consumed = await self._caller(ctx, exc)
        except Throw as e:
            try:
                target = e.target
                if target.__traceback__ is None:
                    raise target.with_traceback(e.__traceback__)
                raise target
            except Exception as e:
                raise ExceptionHandlerError(e)
        except Exception as e:
            raise ExceptionHandlerError(e)
        return consumed
        
    def set_handler(self, handler: ExceptionHandler):
        if inspect.iscoroutinefunction(handler):
            self._caller = handler
        else:
            async def sync_caller(message: EventContext, exc: BaseException) -> bool:
                return cast(bool, await asyncio.to_thread(handler, message, exc))
            self._caller = sync_caller
