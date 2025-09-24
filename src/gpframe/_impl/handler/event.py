from __future__ import annotations

import inspect

class EventHandlerWrapper:
    def __init__(self, event_name: str):
        self.event_name = event_name
        self.caller = None
    
    async def __call__(self, ctx):
        if self.caller is not None:
            return await self.caller(ctx)
                
    def set_handler(self, handler):
        if inspect.iscoroutinefunction(handler):
            async def async_caller(ctx):
                return await handler(ctx)
            self.caller = async_caller
        else:
            async def sync_caller(ctx):
                return handler(ctx)
            self.caller = sync_caller


