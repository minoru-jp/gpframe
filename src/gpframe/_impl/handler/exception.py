from __future__ import annotations

import inspect

class ExceptionHandlerWrapper:
    __slots__ = ('caller',)
    def __init__(self):
        self.caller = None
    
    async def __call__(self, ctx, exc) -> bool:
        if self.caller is not None:
            consumed = await self.caller(ctx, exc)
            return consumed
        return False
        
    def set_handler(self, handler):
        if inspect.iscoroutinefunction(handler):
            async def async_caller(ctx, exc):
                return await handler(ctx, exc)
            self.caller = async_caller
        else:
            async def sync_caller(ctx, exc) -> bool:
                return handler(ctx, exc)
            self.caller = sync_caller
