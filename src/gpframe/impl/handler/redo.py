import asyncio
import inspect
import threading
from typing import Awaitable, Callable, TypeVar, Union, cast

from ..context.event import EventContext

from .errors import FrameHandlerError

R = TypeVar("R")

RedoHandler = Union[Callable[[EventContext[R]], bool], Callable[[EventContext[R]], Awaitable[bool]]]

RedoHandlerAsync = Callable[[EventContext[R]], Awaitable[bool]]

class RedoHandlerWrapper:
    __slots__ = ('_caller',)
    def __init__(self):
        self._caller: RedoHandlerAsync | None = None
    
    async def __call__(self, ctx: EventContext[R]) -> bool:
        if self._caller is not None:
            try:
                result = await self._caller(ctx)
            except Exception as e:
                raise FrameHandlerError('redo', e)
            if not isinstance(result, bool):
                return False
            return result
        return False
        
    def set_handler(self, handler: RedoHandler):
        if inspect.iscoroutinefunction(handler):
            self._caller = handler
        else:
            async def sync_caller(message: EventContext) -> bool:
                return cast(bool, await asyncio.to_thread(handler, message))
            self._caller = sync_caller
