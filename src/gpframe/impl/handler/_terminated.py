

import asyncio
import inspect
import threading
from typing import Awaitable, Callable, Union, cast

from ...api.outcome import Outcome

from .errors import FrameHandlerError

TerminatedHandler = Union[
    Callable[[Outcome], None],
    Callable[[Outcome], Awaitable[None]]
]

TerminatedHandlerAsync = Callable[[Outcome], Awaitable[None]]

class TerminatedHandlerWrapper:
    __slots__ = ('_caller',)
    def __init__(self):
        self._caller: TerminatedHandlerAsync | None  = None
    
    async def __call__(self, outcome: Outcome) -> None:
        if self._caller is not None:
            try:
                await self._caller(outcome)
            except Exception as e:
                raise FrameHandlerError('terminated callback', e)
        
    def set_handler(self, handler: TerminatedHandler):
        if inspect.iscoroutinefunction(handler):
            self._caller = handler
        else:
            async def sync_caller(outcome: Outcome) -> None:
                await asyncio.to_thread(handler, outcome)
            self._caller = sync_caller

