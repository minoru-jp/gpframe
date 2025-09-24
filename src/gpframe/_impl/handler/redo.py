
import inspect

class RedoHandlerWrapper:
    __slots__ = ('caller',)
    def __init__(self):
        self.caller = None
    
    async def __call__(self, ctx) -> bool:
        if self.caller is not None:
            return await self.caller(ctx)
        return False
    
    def set_handler(self, handler):
        if inspect.iscoroutinefunction(handler):
            async def async_handler(ctx):
                return await handler(ctx)
            self.caller = async_handler
        else:
            async def sync_caller(ctx) -> bool:
                return handler(ctx)
            self.caller = sync_caller
